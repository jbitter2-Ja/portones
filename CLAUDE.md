# CLAUDE.md

Guidance for AI assistants working in this repository.

## What this project is

**Portones** ("Sistema apertura portones" / gate-opening system) is a tiny
mobile-first **PWA** that lets a household and its neighbors open electric gates
from their phone. Each gate is controlled by a GSM/cellular gate opener: calling
a specific phone number triggers the gate to open. The app is just a set of
nicely styled buttons that are `tel:` links to those numbers.

The UI is in **Spanish** — keep all user-facing strings in Spanish.

## Architecture

There is no framework, no build step, no dependencies. Each page is a single
**self-contained HTML file**: HTML + inline `<style>` + inline `<script>`, with
the PWA manifest and service worker embedded as base64 `data:` URIs (so the app
needs no extra files and works as flat static hosting).

### Pages

| File | Title | Audience | Gates exposed |
|------|-------|----------|---------------|
| `index.html` | Control de Portones | Household (full access) | Entrada Calle, Salida Calle, Interior Casa (3) |
| `vecinos.html` | Portones Acceso Vecinos | Neighbors (limited) | Entrada Calle, Salida Calle (2) |

`vecinos.html` is the restricted variant: same look and code, but it omits the
"Interior Casa" gate. The two files are intentionally near-duplicates.

### Gate phone numbers (the actual control mechanism)

Each gate is a `<a href="tel:+...">` button. The displayed `.button-number` must
always match the `href` number.

- **Entrada Calle** — `+56959584138`
- **Salida Calle** — `+56959711216`
- **Interior Casa** — `+56975250145` (household only, `index.html` only)

These are Chilean (+56) mobile numbers. Treat them as the app's real
configuration: changing a number changes which gate/opener is triggered.

### PWA pieces (per file)

- **Manifest**: `<link rel="manifest" href="data:application/json;base64,...">`
  in `<head>` — defines name, theme color (`#1a1a2e`), icons (inline SVG).
- **Service worker**: registered from an inline base64 `data:application/javascript`
  URI in the `<script>`. It's a minimal cache-first worker (install/activate/fetch).
- **Install prompt**: handles `beforeinstallprompt` to show a custom "Instalar"
  button.
- **Haptics**: `navigator.vibrate(50)` on each gate-button tap.

## Conventions

- **Self-contained files only.** Do not split out CSS/JS into separate files or
  add external script/style dependencies — the design goal is zero extra assets.
- **Keep the two pages in sync.** When you change shared styling, layout, or the
  PWA/service-worker logic, apply the same change to both `index.html` and
  `vecinos.html`. Remember `vecinos.html` must stay limited to the two street
  gates (no "Interior Casa").
- **Spanish UI text.**
- **Number consistency.** A gate button's visible number and its `tel:` href must
  always agree.
- **Visual language** (shared): dark gradient background (`#1a1a2e`→`#16213e`),
  mint/green accent (`#4af6a6`), glassmorphism cards (`backdrop-filter: blur`),
  yellow accent (`#ffd93d`) used for the household-only "Interior Casa" button.
- Editing the embedded manifest or service worker means decoding the base64,
  editing the JSON/JS, and re-encoding it back into the `data:` URI.

## Running / testing locally

It's static — open the file directly or serve the folder:

```bash
python3 -m http.server 8000   # then visit http://localhost:8000/
```

Note: PWA install and the service worker require **HTTPS or `localhost`** to be
active; over a raw `file://` open the buttons work but PWA features won't.

## Deployment / CI

- Hosted via **GitHub Pages**, built with **Jekyll**.
- CI: `.github/workflows/jekyll-docker.yml` builds the site with the
  `jekyll/builder` Docker image on push/PR to `main`. There are no Jekyll source
  files (no `_config.yml`/layouts) — Jekyll just passes the static HTML through.
- No test suite, no linter, no package manager.

## Git workflow notes

- Default branch is `main`.
- Per the active task, development happens on the
  `claude/claude-md-docs-rydf63` branch; push there, and don't open a PR unless
  explicitly asked.
