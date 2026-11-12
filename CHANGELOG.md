# Changelog

Todos los cambios importantes de `buzon`. Formato basado en
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y versiones con
[SemVer](https://semver.org/lang/es/).

Se generó a partir de `git log --reverse --format="%h %s"` y se corrigió a
mano: se agruparon los commits por tema y se reescribieron para quien usa la
herramienta, no para quien la programa.

## [1.0.0] - 2026-11-12

Primera versión para la entrega del Proyecto 2.

### Añadido

- **Resumen con IA del contenido** de los correos de las últimas 24 h, en tres
  bloques: 🔴 urgente o con plazo, 📌 para leer y 🗑️ puedes ignorarlo. Lee el
  texto de los correos, no solo el asunto (`6b064da`).
- **`limpiar-prescindibles`** (tipo `clasificar-ia`): la IA etiqueta cada
  correo como importante, leer o prescindible, y propone mover a la papelera
  los prescindibles (`034eed0`, `1c9e755`).
- **`buzon comprobar-ia`**: dice si la IA está configurada y responde, sin
  mostrar la clave (`034eed0`).
- **`buzon init`** y búsqueda de la configuración en la carpeta de usuario
  (`%APPDATA%\buzon`, `~/.config/buzon`): funciona instalado desde GitHub
  (`c4186af`).
- **Validación estricta de `acciones.json`**: una errata da
  «¿Quisiste decir «horas»?», un campo que el tipo no usa es un error, las
  claves `_…` son comentarios y una clave repetida es un error (`7be55c3`,
  `f62e95b`).
- Configuración de **OpenCode**: permisos en `opencode.json`, skill
  `acciones-json`, comando `/nueva-accion`, subagente `revisor` de solo
  lectura y `scripts/revisar.sh` (`fd2d7e0`, `72f3e49`, `74b9cc9`).
- **CI** en Ubuntu, Windows y macOS: tests, comprobación de secretos y una
  instalación como la de un compañero (`43e81d5`).
- Tests del cliente IMAP sin red y con credenciales malas (`236e534`).
- Documentación: ADR 0003 (capa de IA), `docs/prompts.md`, spec y README al
  día (`36ff067`, `f3d49b0`, `aeb6d99`).

### Cambiado

- Las confirmaciones son en español, `[s/N]`. Enter es «no» y una respuesta
  rara se vuelve a preguntar (`1f6b1cd`).
- Todas las órdenes gestionan igual los errores: mensaje y código 1, nunca un
  traceback, también sin teclado (tubería, script). En ese caso sugieren la
  opción correcta (`2c6a5f4`, `2d74479`).
- La plantilla de `buzon init` usa IMAP, que solo necesita el `.env`
  (`2d74479`).

### Corregido

- `mover-papelera` preguntaba «¿Eliminar TODA la bandeja de spam?» aunque la
  acción apuntara a otra carpeta (`1f6b1cd`).
- Un correo importante con una etiqueta con paréntesis («Clase (DAM)») perdía
  la marca ⭐ (`c9f6455`).
- Si la IA numeraba mal los correos, la etiqueta se aplicaba al de al lado.
  Ahora se descarta toda la clasificación (`6149fdb`).
- Con muchos correos el prompt no cabía en un modelo local. Ahora entran 60 como
  mucho en el resumen y 35 en la clasificación, con un presupuesto fijo
  (`6149fdb`).
- «El profesor escribió: …» se tomaba por un hilo citado y se borraba del
  resumen (`6149fdb`).

### Seguridad

- `comprobar-ia` mostraba la contraseña de una `IA_API_URL` sin `http://`.
  Ahora solo enseña el servidor y el final de la ruta (`2d74479`).
- `opencode.json` permitía al agente leer `.env` con `git diff --no-index` y
  colar `--si` encadenando órdenes. Las dos vías están cerradas (`2f5f42c`).
- Los delimitadores del prompt se neutralizan dentro del texto de los correos,
  para que un correo no pueda colar instrucciones (`6149fdb`).
- Los tests ya no cargan el `.env` real del alumno (`f62e95b`).

## [0.1.0] - 2026-11-10

Primera versión funcional (`23b0cb2`).

### Añadido

- Órdenes `buzon` (resumen de 24 h + spam + confirmación), `version`,
  `listar`, `acciones`, `validar` y `ejecutar NOMBRE [--simular] [--si]`.
- Acciones en `acciones.json`: `resumen-ia`, `listar`, `mover-papelera`,
  `exportar` y `revisar`.
- `buzon revisar`: lista numerada para ver correos sin marcarlos como leídos y
  moverlos a la papelera uno a uno.
- Proveedor `gmail-api` (HTTPS 443, OAuth con PKCE) para redes que bloquean
  IMAP 993.
- Hook `pre-commit` que bloquea `.env`, `credentials.json` y `token.json`.

[1.0.0]: https://github.com/thebuf11/cli-buzon/compare/v0.1.0...v1.0.0
[0.1.0]: https://github.com/thebuf11/cli-buzon/commit/23b0cb2
