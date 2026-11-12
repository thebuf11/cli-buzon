---
name: acciones-json
description: Cómo escribir, modificar y validar acciones en el acciones.json de buzon (tipos, campos permitidos por tipo, reglas de seguridad y cómo comprobarlas). Úsala siempre que haya que añadir o cambiar una acción.
---

# acciones.json de buzon

`acciones.json` define qué sabe hacer `buzon` **sin tocar el código**. Lo lee y
valida `src/buzon/config.py`. Una acción nueva de un tipo que ya existe solo
necesita una entrada en este fichero.

## Estructura

```json
{
  "version": 1,
  "cuenta": { "proveedor": "gmail-api" },
  "ia": { "modelo_por_defecto": "llama3" },
  "acciones": [
    { "nombre": "listar-spam", "descripcion": "Lista el spam", "tipo": "listar", "carpeta": "spam" }
  ]
}
```

- `version` es siempre `1`.
- `cuenta` e `ia` guardan **nombres de variables de entorno**, nunca valores.
  Los secretos viven en `.env`, y ese fichero **no se lee**.
- Las claves que empiezan por `_` son comentarios: `"_nota": "lo uso los lunes"`.

## Campos de cada acción

Campos comunes y obligatorios:

| Campo | Regla |
|---|---|
| `nombre` | minúsculas, números y guiones (`limpiar-spam`). Único. |
| `descripcion` | texto no vacío; es lo que enseña `buzon acciones` |
| `tipo` | uno de la tabla de abajo |

Campos opcionales: **solo los que admite su tipo**. Cualquier otro campo es un
error (código 3).

| `tipo` | Campos admitidos | Qué hace | ¿Borra? |
|---|---|---|---|
| `listar` | `carpeta`, `horas` | tabla de una carpeta | no |
| `resumen-ia` | `carpeta`, `horas` (24) | tabla + resumen con IA del contenido | no |
| `exportar` | `carpeta`, `horas` (24), `destino` (**obligatorio**) | escribe el resumen en Markdown | no |
| `revisar` | `carpeta`, `horas` (24) | lista interactiva para ver y borrar uno a uno | sí, preguntando |
| `clasificar-ia` | `carpeta`, `horas` (24) | la IA etiqueta y propone mover los prescindibles a la papelera | sí, preguntando |
| `mover-papelera` | `carpeta`, `confirmar` | mueve **toda** la carpeta a la papelera | sí |

- `carpeta`: alias `entrada`, `spam`, `papelera` o un nombre IMAP literal
  (`"[Gmail]/Spam"`, `"Boletines"`). Por defecto, `entrada`.
- `horas`: entero ≥ 1. En `listar`, si se omite, se lista todo.
- `destino`: carpeta local; admite `~` (`"~/resumenes"`).
- `confirmar`: `true` o `false`.

## Reglas de seguridad (obligatorias)

1. Toda acción `mover-papelera` lleva `"confirmar": true`. Si no, `buzon validar` avisa.
2. **No pongas `horas` en `mover-papelera`**: da error, porque esa acción mueve
   la carpeta entera y `horas` haría creer otra cosa.
3. Nada borra de forma definitiva: todo va a la papelera de Gmail, que la
   vacía a los 30 días.
4. Cualquier acción que borre se prueba primero con `--simular`.

## Cómo comprobar una acción nueva

```bash
uv run buzon validar                        # código 0 = válido; 3 = indica el campo que falla
uv run buzon acciones                       # aparece en la tabla
uv run buzon ejecutar NOMBRE --simular      # solo si la acción borra; NO quita --simular
```

`buzon ejecutar` sin `--simular` toca el correo real del alumno: **no lo
ejecutes**, déjaselo a él.

## Errores típicos de `validar`

| Mensaje | Causa |
|---|---|
| `acciones[2].hroas: campo desconocido. ¿Quisiste decir «horas»?` | errata en un campo |
| `acciones[3].horas: las acciones de tipo «mover-papelera» no usan este campo` | campo que no corresponde al tipo |
| `acciones[1].nombre: usa minúsculas, números y guiones` | `Limpiar_Spam` en vez de `limpiar-spam` |
| `acciones[0].destino: una acción «exportar» necesita una carpeta de destino` | falta `destino` |
| `JSON mal formado …, línea 12, columna 5` | coma de más o comillas sin cerrar |

## Si hace falta un tipo nuevo

Eso sí exige código, y hay que tocar **las tres** piezas:

1. Una clase `AccionXxx` en `src/buzon/acciones.py`, registrada en `ACCIONES`.
2. Sus campos en `CAMPOS_POR_TIPO` (`src/buzon/config.py`).
3. Tests en `tests/` con un cliente falso, sin red ni cuenta real.

Después, actualiza esta skill y la tabla de tipos del README.
