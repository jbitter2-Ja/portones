# Control remoto para Android TV (Box Gtd TV 4K · SEI700GTD)

Control remoto web para usar desde el celular. El Box Gtd TV 4K (SEI Robotics
SEI700GTD) es un Android TV certificado, por lo que se controla con el protocolo
oficial **Android TV Remote v2** (el mismo que usa la app Google TV), sin
instalar nada en el televisor ni activar opciones de desarrollador.

```
Celular (navegador) ──HTTP──► server.py ──TLS 6466/6467──► TV
```

Un navegador no puede hablar ese protocolo directamente (TLS con certificado de
cliente), por eso hace falta `server.py` corriendo en un equipo de la misma red
WiFi que el TV: un PC, una Raspberry Pi o el mismo celular con Termux.

## Instalación

Requiere Python 3.10 o superior.

```bash
cd tv-remote
pip install -r requirements.txt
python server.py
```

El servidor imprime la dirección a abrir en el celular, por ejemplo
`http://192.168.1.20:8080`. Luego "Agregar a pantalla de inicio" en el navegador
para tenerlo como app.

### En el mismo celular (Termux)

```bash
pkg install python python-cryptography git
git clone -b ccr-92c67ea7-8sjjsk https://github.com/jbitter2-ja/portones && cd portones/tv-remote
pip install -r requirements.txt
python server.py --port 8765   # y abrir http://localhost:8765
```

## Vinculación (una sola vez)

1. Pulsa **Buscar televisores** o escribe la IP del TV
   (en el TV: Ajustes → Red e Internet → tu red).
2. El TV muestra un código de 6 caracteres; ingrésalo en la web.

El certificado queda guardado en `data/`, así que no se vuelve a pedir.

## Funciones

- Cruceta, OK, Atrás, Inicio, Menú, Ajustes, Entrada, Encendido
- Volumen, silencio, canales, Guía, Info y controles de reproducción
- Mantener presionado: repite (cruceta, volumen, canal) o pulsación larga (OK, Inicio)
- Escribir texto en el TV desde el teclado del celular
- Botones de acceso directo como los del control físico: Gtd TV, Netflix,
  YouTube y Prime Video, además de Todas las apps y TV en vivo
- El botón **Gtd TV** abre GTD SmartTV (`tv.gtd.atv`); si el Box muestra su
  ficha de Play Store, el servidor pulsa "Abrir" automáticamente
- Más accesos a apps; **＋ App actual** guarda la app abierta en el TV
  (mantén presionado un acceso propio para quitarlo)

## Opciones

```
python server.py --port 8080 --host 0.0.0.0 --tv 192.168.1.50
```

## Notas

- Conviene fijar la IP del TV en el router (reserva DHCP) para que no cambie.
- El servidor no tiene contraseña: cualquiera en tu red WiFi puede usar el
  control. No lo expongas a Internet.
- Si el TV está en reposo profundo puede no responder por red; enciéndelo una
  vez con el control físico.
