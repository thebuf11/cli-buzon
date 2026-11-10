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
