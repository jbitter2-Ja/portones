#!/usr/bin/env python3
"""Control remoto web para Android TV / Google TV (p. ej. Box Gtd TV 4K, SEI700GTD).

Habla el protocolo oficial "Android TV Remote v2" (puertos 6466/6467) mediante la
librería androidtvremote2 y expone una interfaz web para usar desde el celular.

Uso:  python server.py [--port 8080] [--host 0.0.0.0] [--tv 192.168.1.50]
"""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import logging
import re
import socket
from pathlib import Path

from androidtvremote2 import (
    AndroidTVRemote,
    CannotConnect,
    ConnectionClosed,
    InvalidAuth,
)

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
CONFIG = DATA / "config.json"
CERT = DATA / "cert.pem"
KEY = DATA / "key.pem"
INDEX = BASE / "static" / "index.html"
CLIENT_NAME = "Control Web"
SERVICE = "_androidtvremote2._tcp.local."
KEY_RE = re.compile(r"^[A-Z0-9_]{1,40}$")
DIRECTIONS = {"SHORT", "START_LONG", "END_LONG"}
MAX_BODY = 16 * 1024

log = logging.getLogger("tv-remote")


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


class TV:
    """Mantiene la conexión con el televisor y su estado."""

    def __init__(self) -> None:
        self.remote: AndroidTVRemote | None = None
        self.host: str | None = None
        self.name: str | None = None
        self.state = "unconfigured"  # unconfigured | pairing | connecting | connected | needs_pairing
        self._task: asyncio.Task | None = None

    # -- persistencia -------------------------------------------------------
    def load(self) -> None:
        try:
            cfg = json.loads(CONFIG.read_text())
            self.host, self.name = cfg.get("host"), cfg.get("name")
        except (OSError, ValueError):
            pass

    def save(self) -> None:
        DATA.mkdir(exist_ok=True)
        CONFIG.write_text(json.dumps({"host": self.host, "name": self.name}))

    # -- ciclo de vida ------------------------------------------------------
    def _reset(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None
        if self.remote:
            self.remote.disconnect()
            self.remote = None

    async def _new_remote(self, host: str) -> AndroidTVRemote:
        DATA.mkdir(exist_ok=True)
        remote = AndroidTVRemote(CLIENT_NAME, str(CERT), str(KEY), host)
        await remote.async_generate_cert_if_missing()
        return remote

    def start(self) -> None:
        """Conecta (y reintenta) con el televisor ya configurado."""
        if not self.host:
            return
        self._reset()
        self.state = "connecting"
        self._task = asyncio.create_task(self._connect_loop(self.host))

    async def _connect_loop(self, host: str) -> None:
        remote = await self._new_remote(host)
        self.remote = remote
        while True:
            try:
                await remote.async_connect()
                break
            except InvalidAuth:
                self._invalid_auth()
                return
            except (CannotConnect, ConnectionClosed):
                await asyncio.sleep(5)
        self.state = "connected"
        remote.add_is_available_updated_callback(self._on_available)
        remote.keep_reconnecting(self._invalid_auth)
        log.info("Conectado a %s (%s)", self.name or "TV", host)

    def _on_available(self, available: bool) -> None:
        if self.state in ("connected", "connecting"):
            self.state = "connected" if available else "connecting"

    def _invalid_auth(self) -> None:
        log.warning("El televisor rechazó el certificado: hay que vincular de nuevo")
        self.state = "needs_pairing"

    # -- vinculación --------------------------------------------------------
    async def pair_start(self, host: str) -> None:
        self._reset()
        remote = await self._new_remote(host)
        try:
            name, _mac = await remote.async_get_name_and_mac()
            await remote.async_start_pairing()
        except (CannotConnect, ConnectionClosed) as exc:
            remote.disconnect()
            self.start()  # vuelve al televisor anterior, si lo había
            raise ApiError(
                f"No pude conectar con {host}. Revisa la IP, que el TV esté "
                "encendido y que ambos estén en la misma red WiFi.",
                502,
            ) from exc
        self.remote, self.host, self.name, self.state = remote, host, name, "pairing"

    async def pair_finish(self, code: str) -> None:
        if self.state != "pairing" or not self.remote:
            raise ApiError("No hay una vinculación en curso.", 409)
        try:
            await self.remote.async_finish_pairing(code)
        except InvalidAuth as exc:
            await self._restart_pairing()
            raise ApiError("Código incorrecto. Ingresa el nuevo código que muestra el TV.") from exc
        except ConnectionClosed as exc:
            await self._restart_pairing()
            raise ApiError("La vinculación se canceló o expiró. Ingresa el nuevo código.") from exc
        self.save()
        self.start()

    async def _restart_pairing(self) -> None:
        try:
            await self.remote.async_start_pairing()
        except (CannotConnect, ConnectionClosed) as exc:
            raise ApiError("Se perdió la conexión con el TV. Empieza de nuevo.", 502) from exc

    def forget(self) -> None:
        self._reset()
        self.host = self.name = None
        self.state = "unconfigured"
        CONFIG.unlink(missing_ok=True)

    # -- comandos -----------------------------------------------------------
    def _ready(self) -> AndroidTVRemote:
        if self.state != "connected" or not self.remote:
            raise ApiError("Sin conexión con el TV.", 503)
        return self.remote

    def key(self, key: str, direction: str = "SHORT") -> None:
        if not KEY_RE.match(key) or direction not in DIRECTIONS:
            raise ApiError("Tecla no válida.")
        try:
            self._ready().send_key_command(key, direction)
        except ValueError as exc:
            raise ApiError(f"Tecla desconocida: {key}") from exc
        except ConnectionClosed as exc:
            raise ApiError("Sin conexión con el TV.", 503) from exc

    def text(self, text: str) -> None:
        if not text or len(text) > 500:
            raise ApiError("Texto vacío o demasiado largo.")
        try:
            self._ready().send_text(text)
        except ConnectionClosed as exc:
            raise ApiError("Sin conexión con el TV.", 503) from exc

    def app(self, link: str) -> None:
        if not link or len(link) > 300 or any(c.isspace() for c in link):
            raise ApiError("App no válida.")
        try:
            self._ready().send_launch_app_command(link)
        except ConnectionClosed as exc:
            raise ApiError("Sin conexión con el TV.", 503) from exc

    def status(self) -> dict:
        out = {"state": self.state, "host": self.host, "name": self.name}
        r = self.remote
        if r and self.state == "connected":
            out.update(is_on=r.is_on, app=r.current_app, volume=r.volume_info)
        return out


async def discover(timeout: float = 3.0) -> list[dict]:
    """Busca televisores Android TV en la red local por mDNS."""
    try:
        from zeroconf import ServiceStateChange
        from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf
    except ImportError as exc:
        raise ApiError("Búsqueda no disponible (falta 'zeroconf'). Ingresa la IP a mano.", 501) from exc

    names: set[str] = set()

    def on_change(zeroconf, service_type, name, state_change) -> None:
        if state_change is not ServiceStateChange.Removed:
            names.add(name)

    found = []
    async with AsyncZeroconf() as azc:
        browser = AsyncServiceBrowser(azc.zeroconf, SERVICE, handlers=[on_change])
        await asyncio.sleep(timeout)
        await browser.async_cancel()
        for name in sorted(names):
            info = AsyncServiceInfo(SERVICE, name)
            if await info.async_request(azc.zeroconf, 1500):
                addrs = info.parsed_addresses()
                ipv4 = [a for a in addrs if ":" not in a]
                if ipv4 or addrs:
                    found.append({"name": name.removesuffix("." + SERVICE), "host": (ipv4 or addrs)[0]})
    return found


# ---------------------------------------------------------------------------
# Servidor HTTP mínimo (solo biblioteca estándar)
# ---------------------------------------------------------------------------
tv = TV()


def valid_host(value: object) -> str:
    host = str(value or "").strip()
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if not re.fullmatch(r"[A-Za-z0-9.-]{1,253}", host):
            raise ApiError("Dirección IP no válida.") from None
    return host


async def route(method: str, path: str, body: dict) -> dict:
    if method == "GET" and path == "/api/status":
        return tv.status()
    if method == "GET" and path == "/api/discover":
        return {"devices": await discover()}
    if method != "POST":
        raise ApiError("No encontrado.", 404)
    if path in ("/api/key", "/api/app", "/api/text"):
        detail = body.get("key") or body.get("app") or "(texto)"
        log.info("%s %s  [TV: %s]", path.rsplit("/", 1)[-1], detail, tv.state)
    if path == "/api/pair/start":
        await tv.pair_start(valid_host(body.get("host")))
    elif path == "/api/pair/finish":
        await tv.pair_finish(str(body.get("code", "")).strip())
    elif path == "/api/key":
        tv.key(str(body.get("key", "")), str(body.get("direction", "SHORT")))
    elif path == "/api/text":
        tv.text(str(body.get("text", "")))
    elif path == "/api/app":
        tv.app(str(body.get("app", "")))
    elif path == "/api/forget":
        tv.forget()
    else:
        raise ApiError("No encontrado.", 404)
    return tv.status()


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    status, ctype, payload = 500, "application/json", b"{}"
    try:
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 10)
        lines = head.decode("latin-1").split("\r\n")
        method, target, _ = lines[0].split(" ", 2)
        headers = {k.strip().lower(): v.strip() for k, _, v in (l.partition(":") for l in lines[1:] if l)}
        length = int(headers.get("content-length", 0))
        if length > MAX_BODY:
            raise ApiError("Petición demasiado grande.", 413)
        raw = await asyncio.wait_for(reader.readexactly(length), 10) if length else b""
        path = target.split("?", 1)[0]

        if method == "GET" and path in ("/", "/index.html"):
            status, ctype, payload = 200, "text/html; charset=utf-8", INDEX.read_bytes()
        else:
            # Exigir JSON en los POST evita que otra web dispare comandos (CSRF).
            if method == "POST" and "application/json" not in headers.get("content-type", ""):
                raise ApiError("Content-Type debe ser application/json.", 415)
            body = json.loads(raw) if raw else {}
            if not isinstance(body, dict):
                raise ApiError("JSON no válido.")
            result = await route(method, path, body)
            status, payload = 200, json.dumps(result).encode()
    except ApiError as exc:
        status, payload = exc.status, json.dumps({"error": str(exc)}).encode()
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, asyncio.TimeoutError, ConnectionError):
        writer.close()
        return
    except ValueError:
        status, payload = 400, json.dumps({"error": "Petición no válida."}).encode()
    except Exception:  # noqa: BLE001 - nunca botar el servidor por una petición
        log.exception("Error inesperado")
        status, payload = 500, json.dumps({"error": "Error interno del servidor."}).encode()

    try:
        writer.write(
            f"HTTP/1.1 {status} X\r\nContent-Type: {ctype}\r\nContent-Length: {len(payload)}\r\n"
            "Cache-Control: no-store\r\nConnection: close\r\n\r\n".encode() + payload
        )
        await writer.drain()
    except ConnectionError:
        pass
    finally:
        writer.close()


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


async def main() -> None:
    parser = argparse.ArgumentParser(description="Control remoto web para Android TV")
    parser.add_argument("--host", default="0.0.0.0", help="interfaz donde escuchar (por defecto, toda la red local)")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--tv", help="IP del televisor (opcional; también se puede elegir desde la web)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    tv.load()
    if args.tv and args.tv != tv.host:
        tv.host, tv.name = valid_host(args.tv), None
    if tv.host and CERT.exists():
        tv.start()

    server = await asyncio.start_server(handle, args.host, args.port)
    shown = lan_ip() if args.host == "0.0.0.0" else args.host
    log.info("Control remoto listo. Abre en el celular:  http://%s:%d", shown, args.port)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
