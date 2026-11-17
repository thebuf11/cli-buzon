# Prueba cruzada de `buzon` · guía para quien la prueba

¡Gracias por probar mi CLI! Es para la instalación cruzada del Proyecto 2.
Se tarda unos **15 minutos**. **No necesitas tu Gmail**: el modo `--demo` usa
correos de ejemplo y nunca borra nada real.

> **La regla:** sigue **solo** lo que pone aquí y en el README. Si algo no
> funciona o no se entiende, **no lo arregles tú**: apúntalo como *issue*
> (ver el final). Para eso sirve la prueba.

---

## 0. Antes de empezar

- Necesitas **uv**. Compruébalo con `uv --version`. Si no lo tienes:
  - Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
  - Linux / macOS: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Cierra y vuelve a abrir la terminal después de instalar uv.
- Apunta tu sistema operativo y tu terminal (PowerShell, Git Bash, bash…). Te
  lo pediré en los issues.

## 1. Instalar (una sola orden)

```bash
uv tool install git+https://github.com/thebuf11/cli-buzon
buzon --help
buzon version        # debe decir «buzon 1.1.0»
```

- [ ] Se instala sin errores
- [ ] `buzon --help` muestra las órdenes
- [ ] `buzon version` dice 1.1.0

Si te sale «buzon no se reconoce como comando», ejecuta `uv tool update-shell`,
abre otra terminal y vuelve a probar.

## 2. Crear la configuración

```bash
buzon init
buzon validar
```

- [ ] `init` dice dónde ha creado `acciones.json` y `.env`
- [ ] `validar` dice «OK … es válido»

## 3. Probar con correos de ejemplo (`--demo`)

```bash
buzon --demo listar --horas 0           # tabla de la bandeja de entrada de ejemplo
buzon --demo listar spam --horas 0      # el spam de ejemplo
buzon --demo                            # flujo completo; al final contesta «n»
buzon --demo ejecutar limpiar-spam --simular
buzon --demo revisar                    # escribe: v 1  →  b 2  →  s  →  q
```

- [ ] Sale el aviso amarillo «Modo demo: … no se toca ningún correo real»
- [ ] Las tablas se leen bien (tildes, «€», «¡», emojis)
- [ ] `--simular` dice qué haría, pero no hace nada
- [ ] En `revisar`, `v 1` enseña el texto del correo y `b 2` pide confirmación

## 4. La IA del centro

Si estás en el centro y tienes tu clave de la IA (la que usas en OpenCode),
rellena el `.env` que te indicó `buzon init`:

```dotenv
CENTRO_IA_URL=<la misma URL que usas en OpenCode, acabada en /v1>
CENTRO_IA_KEY=<tu clave>
CENTRO_IA_CA=<ruta a ca-ies-simarro.crt>
```

Si ya las tienes exportadas en la terminal para OpenCode, no hace falta
escribirlas en el `.env`. **No me pases tu clave nunca**: ni por chat, ni en el
issue, ni en una captura.

```bash
buzon comprobar-ia
buzon --demo ejecutar resumen-24h
buzon --demo ejecutar limpiar-prescindibles --simular
```

- [ ] `comprobar-ia` dice «OK la IA responde» y **no** enseña tu clave
- [ ] `resumen-24h` da un resumen con bloques urgente / para leer / ignorar
- [ ] `limpiar-prescindibles --simular` propone borrar publicidad y boletines,
      pero **no** los correos con ⭐

## 5. Romperla a propósito

Así compruebo que falla bien, sin trazas de Python (*traceback*).

```bash
# Sin red o con un servidor que no existe: debe explicarlo y salir con código 4
#   PowerShell:  $env:CENTRO_IA_URL="https://10.255.255.1/v1"; buzon comprobar-ia; echo $LASTEXITCODE
#   bash:        CENTRO_IA_URL=https://10.255.255.1/v1 buzon comprobar-ia; echo $?

# Sin IA, el resumen enseña la tabla y avisa (no revienta)
#   PowerShell:  $env:CENTRO_IA_URL=""; buzon --demo ejecutar resumen-24h
#   bash:        CENTRO_IA_URL= buzon --demo ejecutar resumen-24h

# Una acción que no existe
buzon --demo ejecutar no-existe
```

Para la siguiente prueba, abre el `acciones.json` de `buzon init` y cambia
`"horas"` por `"hroas"` en cualquier acción. Después:

```bash
buzon validar        # debe decir «¿Quisiste decir «horas»?» y salir con código 3
```

Deshaz el cambio cuando acabes.

- [ ] Ningún error enseña un *traceback* de Python
- [ ] Cada mensaje dice qué falla y qué hacer

## 6. Tu propia acción

Añade una acción tuya al final de la lista `"acciones"` del `acciones.json`. El
README explica el esquema en «Esquema de `acciones.json`». Por ejemplo:

```json
{
  "nombre": "ver-papelera",
  "descripcion": "Lo que hay en la papelera",
  "tipo": "listar",
  "carpeta": "papelera"
}
```

```bash
buzon validar
buzon acciones
buzon --demo ejecutar ver-papelera --simular
```

- [ ] He añadido una acción sin tocar el código y funciona

## 7. Cuéntame qué ha fallado (issues)

Para cada cosa que no funcione o no se entienda, abre un issue en
<https://github.com/thebuf11/cli-buzon/issues/new> con esto:

```text
Título: <qué falla, en una línea>

Sistema: Windows 11 + PowerShell / Ubuntu + bash / …
Orden que ejecuté: buzon …
Qué esperaba: …
Qué pasó: … (pega el mensaje de error; si tiene tu clave o tu ruta personal, bórrala)
Paso de esta guía: 3
```

Si todo va bien, abre un único issue titulado «Prueba cruzada OK» con las
casillas que hayas marcado y tu sistema. También sirven las sugerencias:
textos confusos, cosas del README que no se entienden…

## 8. Desinstalar

```bash
uv tool uninstall cli-buzon
```

`init` dejó la configuración en tu carpeta de usuario: `%APPDATA%\buzon` en
Windows, `~/.config/buzon` en Linux y `~/Library/Application Support/buzon` en
macOS. Bórrala si quieres. **Ojo:** ahí está el `.env` con tu clave.

¡Gracias! 🙌
