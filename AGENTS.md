# AGENTS.md · cli-buzon

Reglas para el agente (OpenCode) en este repositorio.

## Stack

- Python 3.12 + Typer + Rich, gestionado con **uv**.
- Código en `src/buzon/`; pruebas en `tests/`.
- Configuración del usuario en `acciones.json`; secretos en `.env`.

## Órdenes del proyecto

```bash
uv sync
uv run buzon --help
uv run pytest
```

## Reglas

- **No hagas commits ni push**: los hace el alumno, pequeños y con mensajes
  que cuenten el proceso.
- **No leas `.env`** ni imprimas secretos en la salida.
- Usa `pathlib` (nunca concatenar rutas con `/`), `encoding="utf-8"` siempre y
  `shutil` en lugar de `shell=True` u `os.system`.
- Toda excepción previsible debe ser una clase de `errores.py` y llegar al
  usuario como mensaje humano, nunca como traceback.
- Antes de tocar una acción destructiva, pruébala con `--simular`.
- Los textos que vienen de correos se escapan antes de pasarlos a Rich.
- No añadas dependencias sin justificarlo: la librería estándar cubre IMAP
  (`imaplib`) y HTTP (`urllib`).
- **No ejecutes `buzon ejecutar`, `buzon revisar` ni el flujo `buzon` sin
  `--simular`**: trabajan sobre el correo real del alumno. `--si` está
  bloqueado en `opencode.json`.

## Herramientas de OpenCode en este repo

| Qué | Dónde | Para qué |
|---|---|---|
| Permisos | `opencode.json` | Editar pregunta. Prohibido leer, editar o nombrar en el shell `.env`, `credentials*.json`, `token*.json` y las claves. Bloqueados encadenar órdenes (`;`, `&&`, `\|`, `>`…), `git diff --no-index`, `--si`, `git commit`, `push` y `reset`. Los bloqueos van al final porque gana la última regla que coincide |
| Skill `acciones-json` | `.opencode/skills/acciones-json/SKILL.md` | Esquema, campos por tipo y reglas de seguridad de `acciones.json`. Cárgala antes de tocar ese fichero |
| Comando `/nueva-accion` | `.opencode/commands/nueva-accion.md` | `/nueva-accion vaciar la carpeta Boletines cada semana` añade y valida la acción |
| Subagente `revisor` | `.opencode/agents/revisor.md` | Revisión de solo lectura antes de cada commit |
| Script | `scripts/revisar.sh` | Lanza el revisor sin abrir la interfaz: `opencode run --agent revisor` |
| MCP `context7` | `opencode.json` → `mcp.servers` | Documentación de librerías. Está desactivado (`"disabled": true`); actívalo solo cuando haga falta |

Antes de proponer un commit, pasa el revisor (`/review` o `scripts/revisar.sh`).
Si cambias los tipos de acción, actualiza también la skill.
