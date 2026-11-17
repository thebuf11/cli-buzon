# Pruebas de `buzon`

Hay **242 pruebas** con `pytest`. Ninguna sale a la red ni usa una cuenta real:
- el correo lo simulan clientes falsos (`ClienteFalso`, `ClienteDemo`);
- la IA la simulan proveedores falsos que heredan de la clase abstracta `ProveedorIA`, o un `urlopen` falso;
- cada prueba empieza sin las variables de entorno del alumno (`tests/conftest.py`).

Se ejecutan en GitHub Actions en **Ubuntu, Windows y macOS** con cada push a `main` y cada PR
(`.github/workflows/tests.yml`).

```bash
uv run pytest            # todas (-q ya va en pyproject.toml)
uv run pytest -v         # con el nombre de cada prueba
uv run pytest -k simul  # solo las que tienen «simul» en el nombre (simular, simulado…)
```

## Qué prueba cada fichero

| Fichero | Pruebas | Qué cubre |
|---|---:|---|
| `test_config.py` | 28 | `acciones.json`: JSON roto, erratas con sugerencia, campos que un tipo no usa, claves repetidas |
| `test_cli.py` | 10 | Las órdenes de punta a punta con `CliRunner`, sus códigos de salida e `init` |
| `test_motor.py` | 4 | El motor con un cliente falso: ejecuta y cierra la conexión |
| `test_revisar.py` | 28 | La revisión interactiva: `v N`, `b 1,3-5`, renumerar y confirmar |
| `test_confirmar.py` | 14 | `[s/N]` en español y qué pasa si no hay teclado (tubería, script o chat) |
| `test_correo.py` | 8 | Leer remitente, asunto, fecha y la marca ⭐ de un correo |
| `test_limpieza_texto.py` | 4 | El texto del correo al verlo: HTML, líneas vacías y caracteres de control |
| `test_imap.py` | 13 | Cliente IMAP: sin red, credenciales malas, conexión perdida a medias |
| `test_gmail_api.py` | 19 | API de Gmail: token caducado, cuota agotada, errores HTTP |
| `test_resumen_ia.py` | 16 | Resumen con IA: recorte del texto, presupuesto del prompt y la acción |
| `test_clasificar_ia.py` | 38 | `limpiar-prescindibles`: que nunca se borre un ⭐, numeración mala de la IA, `comprobar-ia` |
| `test_ia_centro.py` | 31 | IA del centro: URL base, certificado y un mensaje por cada fallo (401, 429, sin red…) |
| `test_demo.py` | 14 | Modo demo: todas las órdenes sin Gmail; lo borrado solo cambia en memoria |
| `test_diseno.py` | 15 | Clases abstractas, registro de acciones, `--simular` sin IA y `--demo` sin `init` |

## El camino feliz

`test_demo.py::test_flujo_completo_en_demo_contestando_no` ejecuta `buzon --demo`
como lo haría el profesor:
1. Enseña los correos de las últimas 24 h y el resumen. Sin IA, avisa en su lugar.
2. Enseña la bandeja de spam.
3. Pregunta si la vacía. Se contesta «n», así que termina con código 0 y el
   mensaje «No se ha borrado nada».

`test_resumen_ia.py::test_resumen_resume_todos_los_correos_con_su_texto` comprueba
que el resumen recibe el **texto** de los correos y no solo los asuntos.

## Tres casos feos, explicados

### 1. No hay red (o no estás en el centro)

- **Prueba:** `test_ia_centro.py::test_comprobar_ia_sin_red_sale_con_4_y_lo_explica`.
- **Qué hace:** pone `CENTRO_IA_URL=https://10.255.255.1/v1` y sustituye `urlopen`
  por uno que lanza `URLError(TimeoutError)`, que es lo que hace urllib cuando no
  puede conectar.
- **Qué comprueba:**
  - la salida es el **código 4**;
  - el mensaje dice «¿estás en la red del centro (o tienes conexión)?»;
  - también dice que las acciones sin IA siguen funcionando.
- **Qué la pondría en rojo:**
  - que `comprobar_ia` (en `cli.py`) saliera con `typer.Exit(1)`;
  - que `_error_conexion` (en `ia.py`) dejara de distinguir la falta de red;
  - que alguien quitara el `except SinRedError` y saliera un traceback.

### 2. `acciones.json` con una errata

- **Prueba:** `test_cli.py::test_validar_errata_sale_con_3_y_sugiere`.
- **Qué hace:** escribe `"carpta": "spam"` en lugar de `"carpeta"` y ejecuta `buzon validar`.
- **Qué comprueba:** la salida es el **código 3** (configuración inválida) y el
  mensaje sugiere «¿Quisiste decir «carpeta»?».
- **Por qué importa:** sin esa validación, la acción ignoraría el campo y
  listaría la bandeja de entrada (la carpeta por defecto) en lugar del spam, y
  nadie notaría la errata.
- **Qué la pondría en rojo:** quitar `_comprobar_campos` de `config.py`, o
  devolver otro código distinto de 3.

### 3. Lo que Gmail marca como importante nunca se borra

- **Prueba:** `test_clasificar_ia.py::test_lo_importante_para_gmail_nunca_se_borra`.
- **Qué hace:** una IA falsa dice que un correo con ⭐ es «prescindible», y se
  ejecuta con `--si`, es decir, sin preguntar.
- **Qué comprueba:** ese correo **no** se mueve a la papelera.
- **Por qué importa:** un modelo pequeño se equivoca, y aquí el error borraría
  un correo importante.
- **Qué la pondría en rojo:** quitar el bucle «red de seguridad» de
  `AccionClasificarIA.ejecutar` en `acciones.py`. Aunque alguien lo quitara,
  además saltaría la aserción `assert not any(c.importante …)` que va justo
  antes de mover.

Otros casos feos que también tienen su prueba:
- certificado que falta o no corresponde (`test_ia_centro.py`);
- clave pegada con comillas «“ ”» o con un salto de línea;
- credenciales de Gmail malas, sin mostrar la contraseña (`test_imap.py`);
- orden interactiva sin teclado (`test_confirmar.py`).

## Cómo se simula lo que no se puede usar en un test

| Real | En los tests | Por qué |
|---|---|---|
| Gmail (IMAP o API) | `ClienteFalso` (`test_motor.py`) o `ClienteDemo` | Sin red, sin cuenta y sin borrar nada real |
| IA del centro | Hijas de la clase abstracta `ProveedorIA`: `ProveedorFalso` (fixture en `conftest.py`, responde por `completar`) e `IAFalsa` (en los tests de acciones, responde por `resumir` o `clasificar`) | Respuestas fijas y sin gastar tokens. Las acciones solo usan la interfaz de `ProveedorIA`, así que da igual quién responda |
| Servidor HTTP | `urlopen` sustituido con `monkeypatch` | Para provocar 401, 429, timeout o certificado malo cuando queramos |
| Teclado | `CliRunner(input="n\n")` o `confirmar` sustituido | Para contestar las preguntas `[s/N]` |
| Tu `.env` | `conftest.py` borra `GMAIL_*`, `CENTRO_IA_*` y `BUZON_*` en cada prueba | Para que una prueba nunca llame a tu IA ni use tu cuenta |
