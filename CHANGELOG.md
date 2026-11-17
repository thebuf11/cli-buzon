# Changelog

Todos los cambios importantes de `buzon`. Formato basado en
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y versiones con
[SemVer](https://semver.org/lang/es/).

Se generó a partir de `git log --reverse --format="%h %s"` y se corrigió a
mano: se agruparon los commits por tema y se reescribieron para quien usa la
herramienta, no para quien la programa.

## [1.2.1] - 2026-11-17

### Corregido

- **Mensaje de sesión de Google caducada:** antes decía «Google rechazó la sesión
  guardada o el cliente OAuth», sin explicar qué pasaba. Ahora distingue dos casos:
  - **sesión caducada:** en modo «Prueba» pasa a los 7 días. Explica que ya se
    borró `token.json` y que basta con volver a ejecutar la orden;
  - **cliente OAuth rechazado:** dice cómo descargar `credentials.json` de nuevo.
- El README explica la caducidad de 7 días y qué pide Google para publicar la app.

## [1.2.0] - 2026-11-17

### Añadido

- **`--simular` en `resumen-24h` y `guardar-resumen` ya no llama a la IA:**
  dice cuántos correos, caracteres y tokens se enviarían, a qué modelo y a qué
  servidor (ADR 0003). `limpiar-prescindibles --simular` sigue preguntando a la
  IA para enseñar qué propondría, pero nunca mueve nada.
- **`buzon --demo` funciona sin `buzon init`:** si no hay `acciones.json`, usa
  las acciones de ejemplo del paquete. Así se puede probar nada más instalar.
  Con un `--config` que no existe sigue saliendo con código 3.
- `docs/pruebas.md` (qué prueba cada fichero, el camino feliz y tres casos feos
  explicados) y `docs/defensa.md` (respuestas a las preguntas de la defensa).
- Resumen de la spec en 10 líneas al principio del README.

### Cambiado

- **Diseño:**
  - `ProveedorIA` y `AccionBase` son clases abstractas (`ABC`).
  - El HTTP de la IA vive en `ProveedorCentro`, y los proveedores falsos de los
    tests también heredan de `ProveedorIA`.
  - Todos los fallos de la IA, incluida una clasificación que no se entiende,
    son `IANoDisponible`.
  - La clave de la IA es privada (`_clave`).
  - `construir_endpoint` es un método estático.
- **Aserciones de desarrollo** en los puntos que no deben fallar nunca:
  - no se mueve ningún ⭐ a la papelera;
  - la numeración de la IA está en rango;
  - el registro `ACCIONES` cubre todos los tipos válidos.
- `docs/prompts.md`: sesión del 17/11 con los errores del agente y cómo se
  detectaron.

## [1.1.1] - 2026-11-17

### Corregido

- **Modelo por defecto de la IA del centro:** la 1.1.0 usaba
  `qwen3.8-flash-next`, que no existe en el servidor del IES Simarro, y la IA
  respondía 404 aunque la URL y la clave estuvieran bien. Ahora es
  `Qwen38-DualSpark-medium`, el mismo que usa OpenCode. Con `CENTRO_IA_MODELO`
  se puede elegir `-low` (rápido) o `-xhigh` (máxima calidad).
- Los ejemplos de `.env.example`, la plantilla de `buzon init` y el README usan
  la dirección real del centro: `https://ia.simarro/llmapi/v1`.

### Añadido

- Subagente de OpenCode **`probador-demo`** y `scripts/probar-demo.sh`: prueba
  la CLI de punta a punta con `--demo` (16 pruebas) y da un veredicto antes de
  una release. No puede editar ni tocar el correo real.

## [1.1.0] - 2026-11-17

Para que el profesor pueda probarla en el centro, con la IA del centro y sin Gmail.

### Añadido

- **IA del centro (IES Simarro):** se usan las mismas variables que OpenCode
  (`CENTRO_IA_URL`, `CENTRO_IA_KEY`, `CENTRO_IA_MODELO` y `CENTRO_IA_CA`) y el
  modelo `qwen3.8-flash-next` por defecto. Vale la URL base (`…/v1`) o la
  completa.
- **Certificado del centro:** `CENTRO_IA_CA` se carga junto a los certificados
  del sistema. `comprobar-ia` dice si el fichero existe, sin enseñar su contenido.
- **Modo demo:** `buzon --demo …` o `BUZON_DEMO=1` usan una bandeja de ejemplo
  en memoria. Funcionan todas las órdenes, sin cuenta y sin borrar nada real
  (ADR 0004).
- Mensajes concretos para cada fallo de la IA: 401/403 (clave), 404 (URL o
  modelo), 429, certificado, sin red y tiempo agotado.
- Sección «Probarlo en el centro» en el README.

### Cambiado

- `buzon comprobar-ia` sale con **4** si la IA no está disponible (antes, 1).
- **Variables de la IA nuevas.** Si creaste la configuración con
  `buzon init` en la 1.0.0, tu `acciones.json` fija los nombres viejos en el
  bloque `"ia"`. Para pasarte a la IA del centro:
  1. **Borra el bloque `"ia"`** de tu `acciones.json`. Sin él se usan
     `CENTRO_IA_*` y `qwen3.8-flash-next`.
  2. En `.env`, cambia `IA_API_URL` por `CENTRO_IA_URL` (vale la URL base,
     `…/v1`) e `IA_API_KEY` por `CENTRO_IA_KEY`, y añade `CENTRO_IA_CA`.

  `buzon validar` y `comprobar-ia` avisan si siguen los nombres viejos. Si
  prefieres conservarlos, no toques nada: tu IA anterior sigue funcionando.

### Corregido

- Con una URL de IA con un puerto que no es un número (`http://host:abc/v1`),
  `comprobar-ia` acababa con una excepción sin capturar. Ahora explica que la
  URL no es válida. El test anterior no lo detectaba porque CliRunner también
  devuelve 1 en ese caso.

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

[1.2.1]: https://github.com/thebuf11/cli-buzon/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/thebuf11/cli-buzon/compare/v1.1.1...v1.2.0
[1.1.1]: https://github.com/thebuf11/cli-buzon/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/thebuf11/cli-buzon/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/thebuf11/cli-buzon/compare/v0.1.0...v1.0.0
[0.1.0]: https://github.com/thebuf11/cli-buzon/commit/23b0cb2
