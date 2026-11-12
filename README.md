# buzon · CLI de Gmail

Herramienta de terminal que, con **una sola orden**, te dice qué correos
importantes has recibido en las **últimas 24 horas**, te enseña el **spam** y,
si dices que sí, mueve toda la bandeja de spam a la papelera de Gmail.

Hecha para el Proyecto 2 (CLI) del módulo de programación: Python 3.12 +
Typer + uv, con las acciones definidas en `acciones.json` (no en el código).

## Qué hace

```text
$ buzon
Importantes · últimas 24 h
┌──────────┬──────────────────┬──────────────────────────────────┐
│ Hora     │ Remitente        │ Asunto                           │
├──────────┼──────────────────┼──────────────────────────────────┤
│ 09/11 10 │ Ana Torres       │ Reunión de tutores               │
└──────────┴──────────────────┴──────────────────────────────────┘
╭─ Resumen con IA ─────────────────────────────────────────────╮
│ Tienes una reunión de tutores el martes a las 17:00.          │
╰──────────────────────────────────────────────────────────────╯

Spam: 37 mensajes
...
¿Eliminar TODA la bandeja de spam (37 mensajes)? [s/N]:
```

Órdenes disponibles:

| Orden | Qué hace |
|-------|----------|
| `buzon` | Flujo completo: resumen 24 h + spam + confirmación |
| `buzon version` | Versión instalada |
| `buzon revisar [CARPETA] [--horas N] [--simular]` | **Revisión interactiva**: lista numerada, ver y borrar correos uno a uno |
| `buzon listar [CARPETA] [--horas N]` | Tabla de una carpeta (`INBOX`, `spam`, `papelera` o nombre IMAP) |
| `buzon acciones` | Lista las acciones de `acciones.json` |
| `buzon validar` | Comprueba `acciones.json` y dice qué campo falla |
| `buzon comprobar-ia` | Dice si la IA está configurada y responde |
| `buzon init` | Crea `acciones.json` y `.env` en tu carpeta de usuario |
| `buzon ejecutar NOMBRE [--simular] [--si]` | Ejecuta una acción |
| `buzon --config RUTA ...` | Usa otro fichero de acciones |

Códigos de salida: **0** bien · **1** fallo al ejecutar · **2** error de uso
(Typer) · **3** configuración inválida.

## Requisitos

- Python 3.12 (uv lo instala si hace falta)
- [uv](https://docs.astral.sh/uv/)
- Una cuenta de Gmail con **IMAP activado** y **contraseña de aplicación**

## Instalación

```bash
git clone https://github.com/thebuf11/cli-buzon.git
cd cli-buzon
uv tool install --editable .
buzon --help
```

También se puede instalar directamente desde GitHub:

```bash
uv tool install git+https://github.com/thebuf11/cli-buzon
```

Desinstalar: `uv tool uninstall cli-buzon`.

Instalado desde GitHub no hay carpeta del proyecto. Crea tu configuración con:

```bash
buzon init        # crea acciones.json y .env en tu carpeta de usuario y explica los pasos
buzon validar
```

La carpeta de usuario es `%APPDATA%\buzon` en Windows, `~/.config/buzon` en
Linux y `~/Library/Application Support/buzon` en macOS. `init` nunca
sobrescribe nada.

Una vez instalado, `buzon` funciona **desde cualquier carpeta**. Busca su
configuración en este orden:

1. `--config RUTA`
2. la variable `BUZON_CONFIG`
3. `./acciones.json` de la carpeta actual
4. el de tu carpeta de usuario (`buzon init`)
5. el `acciones.json` del proyecto (instalación `--editable`)

`.env`, `credentials.json` y `token.json` se leen de la misma carpeta que el
`acciones.json` elegido. Con `--editable`, los cambios en el código se aplican
sin reinstalar.

## Configurar Gmail (una sola vez)

1. **Activa IMAP**: Gmail → Ajustes → *Reenvío y POP/IMAP* → *Habilitar IMAP*.
2. **Activa la verificación en 2 pasos** en tu Cuenta de Google.
3. **Crea una contraseña de aplicación**: Cuenta de Google → Seguridad →
   *Contraseñas de aplicaciones*. Copia los 16 caracteres **sin espacios**.
4. Copia `.env.example` a `.env` y rellena:

```dotenv
GMAIL_USUARIO=tucuenta@gmail.com
GMAIL_APP_PASSWORD=abcdefghijklmnop
```

`.env` está en `.gitignore`: **nunca** se sube al repositorio. No uses tu
contraseña normal de Gmail.

### Usar la API de Gmail (si tu red bloquea el puerto 993)

IMAP usa `imap.gmail.com:993`. Ese **993 es el puerto del servidor de Google**,
no uno de tu ordenador: no choca con otras aplicaciones tuyas, aunque usen ese
número en local. Lo que sí pasa es que algunas redes (centros, empresas)
**bloquean la salida** al 993. Gmail no ofrece IMAP en otro puerto, así que
`buzon` puede usar la **API de Gmail por HTTPS (443)**, que casi nunca está
bloqueada. Se elige en `acciones.json`:

```json
"cuenta": { "proveedor": "gmail-api", ... }
```

(`"imap"` es el valor por defecto). Con la API **no** hacen falta
`GMAIL_USUARIO` ni `GMAIL_APP_PASSWORD`. Configuración (una sola vez):

1. Entra en <https://console.cloud.google.com/> y **crea un proyecto** (por ejemplo «buzon»).
2. *APIs y servicios → Biblioteca* → busca **Gmail API** → **Habilitar**.
3. *APIs y servicios → Pantalla de consentimiento de OAuth* → tipo **Externo**.
   Rellena nombre y correo, y en **Usuarios de prueba** añade tu dirección de Gmail.
4. *APIs y servicios → Credenciales → Crear credenciales → ID de cliente de OAuth*
   → tipo de aplicación **App de escritorio**.
5. **Descarga el JSON** y guárdalo como `credentials.json` **en la misma
   carpeta que tu `acciones.json`**: la del proyecto (`cli-buzon/`) o la de
   `buzon init`.
6. Ejecuta `buzon revisar`: se abre el navegador, eliges tu cuenta y aceptas.
   Como la app está «en pruebas», Google avisa de que no está verificada:
   pulsa *Continuar*. El permiso queda en `token.json` y no se vuelve a pedir.

`credentials.json` y `token.json` están en `.gitignore`: **nunca** se suben.
Para revocar el acceso: borra `token.json` y quita el permiso en
<https://myaccount.google.com/permissions>.

El inicio de sesión abre un servidor temporal en `127.0.0.1` en un **puerto libre
que elige el sistema**, solo durante unos segundos, así que tampoco interfiere
con otras aplicaciones.

### Capa de IA (opcional)

`buzon` funciona sin IA: avisa y sigue mostrando las tablas. Para activar el
resumen, apunta `IA_API_URL` a un servicio compatible con OpenAI
(`POST /v1/chat/completions`), por ejemplo el modelo local del centro:

```dotenv
IA_API_URL=http://localhost:11434/v1/chat/completions
IA_API_KEY=
IA_MODELO=llama3
```

Si no hay red o falta la URL, la CLI **no revienta**: explica el problema y
continúa con las acciones que no necesitan IA.

Para saber si la IA está bien configurada:

```text
$ buzon comprobar-ia
IA_API_URL   http://localhost:11434/v1/chat/completions
IA_MODELO    llama3
IA_API_KEY   no definida
OK la IA responde en 2.3 s: «OK»
```

Sale con **0** si responde y con **1** si no. La clave nunca se muestra, y de
la URL se ocultan el usuario, la contraseña y los parámetros.

Acciones con IA:

| Acción | Qué hace |
|--------|----------|
| `resumen-24h` | Resume el contenido de los correos en tres bloques: urgente, para leer e ignorar |
| `limpiar-prescindibles` | Clasifica cada correo (importante · leer · prescindible) y propone mover a la papelera los prescindibles |

Garantías de `limpiar-prescindibles`:

- Siempre pide confirmación, salvo con `--si`. Pruébalo primero con `--simular`.
- Lo que Gmail marca como importante (⭐) **nunca** se propone para borrar.
- Si la IA duda, devuelve algo raro o no menciona un correo, ese correo
  queda como «leer» y no se toca.
- Sin IA no se borra nada.

## Uso

```bash
# Flujo completo (pregunta antes de tocar el spam)
buzon

# Revisar los correos de las últimas 24 h y borrar los que no interesen
buzon revisar
buzon revisar --simular          # practica sin mover nada
buzon revisar spam --horas 0     # todo el spam, uno a uno

# Ver el spam sin borrar nada
buzon ejecutar listar-spam
buzon ejecutar limpiar-spam --simular

# Borrar el spam sin preguntar (scripts)
buzon ejecutar limpiar-spam --si

# La IA propone qué borrar (publicidad, boletines…)
buzon ejecutar limpiar-prescindibles --simular
buzon ejecutar limpiar-prescindibles

# Guardar el resumen del día en ~/resumenes/resumen-2026-11-09.md
buzon ejecutar guardar-resumen

# Otro fichero de acciones
buzon --config ~/mis-acciones.json acciones
```

> **Seguridad:** `limpiar-spam` no borra de verdad: mueve los mensajes a la
> papelera de Gmail, que los elimina a los 30 días (es lo mismo que hace el
> botón «Eliminar mensajes de spam» de la web). Prueba siempre primero con
> `--simular`.

### Revisión interactiva (`buzon revisar`)

```text
$ buzon revisar
entrada · últimas 24 h
┌───┬─────────────┬────────────────┬──────────────────────────┐
│ # │ Hora        │ Remitente      │ Asunto                   │
├───┼─────────────┼────────────────┼──────────────────────────┤
│ 1 │ 10/11 11:02 │ Tienda Online  │ Ofertas del Black Friday │
│ 2 │ 10/11 10:15 │ Boletín        │ Noticias de la semana    │
│ 3 │ 10/11 09:00 │ Ana Torres     │ ⭐ Reunión de tutores     │
└───┴─────────────┴────────────────┴──────────────────────────┘
v N ver correo · b 1,3,5-7 borrar · b * borrar todos · l listar · q salir
buzon: v 3
buzon: b 1-2
¿Mover 2 correo(s) a la papelera? [s/N]: s
OK: 2 correo(s) movidos a la papelera.
```

- Los correos salen del **más nuevo al más antiguo**; ⭐ = importante para Gmail.
- `v N` descarga el texto del correo **sin marcarlo como leído** (si solo hay HTML, se limpia).
- `b` acepta números sueltos, listas y rangos (`b 1,4,6-9`) y **siempre pide confirmación**.
- Tras borrar, la lista se vuelve a numerar.
- Si tu Gmail está en español, la papelera se llama `[Gmail]/Papelera`: la CLI
  la detecta sola aunque `acciones.json` diga `[Gmail]/Trash`.
- **Red:** IMAP usa el puerto **993**. Algunas redes (centros educativos,
  empresas) lo bloquean; si ves «No se pudo conectar con imap.gmail.com:993»,
  usa `"proveedor": "gmail-api"` (ver «Usar la API de Gmail»).

## Esquema de `acciones.json`

```jsonc
{
  "version": 1,
  "cuenta": {
    "servidor": "imap.gmail.com",
    "puerto": 993,
    "usuario_env": "GMAIL_USUARIO",       // nombre de la variable, no el valor
    "password_env": "GMAIL_APP_PASSWORD",
    "carpeta_entrada": "INBOX",
    "carpeta_spam": "[Gmail]/Spam",
    "carpeta_papelera": "[Gmail]/Trash",
    "proveedor": "imap",                  // o "gmail-api" (HTTPS 443)
    "credenciales_api": "credentials.json",
    "token_api": "token.json"
  },
  "ia": {
    "url_env": "IA_API_URL",
    "clave_env": "IA_API_KEY",
    "modelo_env": "IA_MODELO",
    "modelo_por_defecto": "llama3"
  },
  "acciones": [
    {
      "nombre": "resumen-24h",              // minúsculas y guiones, único
      "descripcion": "Resume con IA el contenido de los correos de las últimas 24 horas",
      "tipo": "resumen-ia",
      "horas": 24
    }
  ]
}
```

Tipos de acción:

| `tipo` | Campos | Qué hace |
|--------|--------|----------|
| `resumen-ia` | `horas` (24) | Tabla de la ventana + resumen con IA del texto de los correos (urgente · para leer · ignorar) |
| `listar` | `carpeta`, `horas` (opcional; sin él, todo) | Tabla de una carpeta |
| `mover-papelera` | `carpeta`, `confirmar` | Mueve la carpeta a la papelera |
| `exportar` | `horas`, `destino` | Escribe un Markdown con el resumen |
| `revisar` | `carpeta`, `horas` (24) | Lista numerada interactiva: ver y borrar correos elegidos |
| `clasificar-ia` | `carpeta`, `horas` (24) | La IA clasifica los correos y propone mover a la papelera los prescindibles |

`carpeta` acepta los alias `entrada`, `spam` y `papelera`, o un nombre IMAP
literal. Añadir una acción nueva **no exige tocar el código**: se escribe en
`acciones.json` y se ejecuta con `buzon ejecutar NOMBRE`.

`buzon validar` es estricto, para que un descuido no pase en silencio:

- Un campo con errata (`"hroas"`) es un error (código 3) con sugerencia:
  «¿Quisiste decir «horas»?».
- Un campo que el tipo no usa también es un error. Por ejemplo, `horas` en
  `mover-papelera`, que mueve **toda** la carpeta, no solo las últimas horas.
- Las claves que empiezan por `_` se ignoran y sirven de comentario
  (JSON no tiene comentarios): `"_nota": "lo uso los lunes"`.
- Si una acción `mover-papelera` no tiene `"confirmar": true`, `validar` avisa.

## Secretos y GitHub

Estos ficheros dan acceso a tu Gmail y **nunca** se suben al repositorio:

| Fichero | Qué contiene |
|---------|--------------|
| `.env` | Contraseña de aplicación de Gmail y claves de la IA |
| `credentials.json` | Cliente OAuth de Google Cloud |
| `token.json` | Tu sesión de Gmail (permite leer y borrar correo) |
| `resumenes/` | Remitentes y asuntos de tus correos |

Dos protecciones:

1. `.gitignore` los ignora, incluidas variantes (`client_secret_*.json`,
   `token*.json`, `.env.*`…). Solo se sube `.env.example`, sin valores.
2. Un *hook* `pre-commit` (`.githooks/pre-commit`) **bloquea el commit** si
   alguno se cuela con `git add -f` o si el contenido parece una clave o un
   token de Google. Se activa una vez en cada clon:

```bash
git config core.hooksPath .githooks
```

Comprueba qué se va a subir antes del primer commit:

```bash
git status --short            # lo que se subirá
git status --short --ignored  # lo ignorado aparece con «!!»
```

Si alguna vez se sube un secreto por error, borrarlo del repositorio **no
basta**: revoca el acceso en <https://myaccount.google.com/permissions>, borra
`token.json`, crea un cliente OAuth nuevo en Google Cloud y cambia la
contraseña de aplicación.

## Desarrollo

```bash
uv sync                 # crea .venv e instala dependencias
uv run buzon --help
uv run pytest           # pruebas sin red ni cuenta real
```

### Con OpenCode

El repositorio trae la configuración del agente. `AGENTS.md` tiene las reglas
y la tabla de herramientas.

- `opencode.json`: permisos. Editar pregunta antes; el agente no puede leer
  `.env` ni las credenciales de Google y no puede hacer `git commit` ni `push`.
- `/nueva-accion <qué quieres>`: añade una acción a `acciones.json` usando la
  skill `acciones-json` y la valida con `buzon validar`.
- `scripts/revisar.sh`: revisión de solo lectura con el subagente `revisor`
  antes de cada commit.

```bash
scripts/revisar.sh            # cambios sin commitear
scripts/revisar.sh HEAD~3     # los últimos 3 commits
```

En Windows, ejecútalo desde Git Bash.

Estructura:

```
src/buzon/
├── cli.py          # interfaz Typer: órdenes, opciones, códigos de salida
├── config.py       # lee y VALIDA acciones.json y .env
├── motor.py        # Motor: ejecuta una acción sobre su carpeta
├── acciones.py     # clases Listar, ResumenIA, ClasificarIA, MoverPapelera, Exportar, Revisar
├── imap_client.py  # conexión IMAP + parser de correos (stdlib)
├── gmail_api.py    # alternativa: API REST de Gmail por HTTPS + OAuth (stdlib)
├── ia.py           # cliente HTTP compatible con OpenAI: prompts, presupuesto, clasificación
├── salida.py       # tablas Rich (texto de correo escapado) y confirmar() [s/N]
├── errores.py      # excepciones propias
└── plantillas/     # acciones.json y .env que copia «buzon init»
```

Documentación del diseño:

- `docs/spec.md`: qué hace y qué no hace la herramienta.
- `docs/adr/`: decisiones de diseño.
  - 0001: configuración externa.
  - 0002: API de Gmail.
  - 0003: capa de IA.
- `docs/prompts.md`: cómo se ha usado la IA para programar y qué prompts envía la CLI.

## Limitaciones conocidas

- El resumen con IA lee el texto de hasta 30 correos (importantes y recientes
  primero), recortado y sin el hilo citado; el resto entra solo con remitente y
  asunto. Como mucho entran 60 correos en el resumen y 35 en
  `limpiar-prescindibles`. Ese texto se envía al servicio de `IA_API_URL`: usa
  el modelo local del centro si no quieres que salga de la red.
- Un modelo pequeño puede clasificar mal. Por eso la clasificación siempre se
  enseña antes de pedir confirmación, y con `--si` no hay nadie que la revise.
- «Importante» depende de la marca `\Important` de Gmail. Si Gmail no ha
  marcado nada, se muestran todos los correos de la ventana.
- Gmail puede tardar un poco en reflejar en IMAP los cambios hechos en la web.

## Roadmap

- [x] Configuración en la carpeta de usuario y `buzon init` (instalación desde GitHub)
- [x] Validación estricta de `acciones.json` con sugerencias
- [x] Resumen con IA del contenido de los correos, `clasificar-ia` y `comprobar-ia`
- [x] Modo sin red o sin IA en todas las acciones (con tests)
- [x] Confirmaciones `[s/N]` y errores sin traceback, también sin teclado
- [x] Configuración de OpenCode: permisos, skill, `/nueva-accion` y subagente revisor
- [x] Revisión de código y corrección de sus hallazgos (ver `docs/prompts.md`)
- [ ] Tests del cliente IMAP sin red y con credenciales malas (ya los tiene la API de Gmail)
- [ ] GitHub Actions en Ubuntu, Windows y macOS
- [ ] Release v1.0 con changelog
