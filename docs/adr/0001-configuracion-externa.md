# ADR 0001 · Configuración externa (`acciones.json`)

- **Estado:** aceptado
- **Fecha:** 2026-11-09

## Contexto

La herramienta tiene que hacer varias tareas sobre el correo (resumir, listar
spam, limpiar spam, exportar). Si cada tarea se escribe como una función fija
en `cli.py`, añadir o cambiar una acción obliga a tocar código, volver a
instalar y volver a probar. Además, datos que cambian según la cuenta —la
carpeta de spam, la ventana de horas, el destino del resumen— quedarían
repartidos por el programa.

## Decisión

Las acciones se describen en un fichero **`acciones.json`** que escribe el
usuario. El programa solo interpreta cuatro tipos (`resumen-ia`, `listar`,
`mover-papelera`, `exportar`) y sus campos. La configuración de la cuenta y de
la IA también vive ahí; los **secretos** no: se leen de variables de entorno
cargadas desde `.env`.

El fichero se valida antes de ejecutar nada (`config.py`). Si algo falla, el
mensaje indica la ruta exacta del campo (`acciones[1].tipo`) y la orden
`buzon validar` sale con código 3.

## Consecuencias

**A favor**

- Añadir una acción nueva no exige tocar el código: se escribe en el JSON.
- Los cambios de cuenta o de carpetas no mezclan datos con lógica.
- El JSON se puede versionar, revisar y compartir sin secretos.
- Es fácil de probar: el motor recibe una configuración ya validada.

**En contra**

- Hay que mantener el esquema y su validación.
- Un JSON mal escrito es un error más que el usuario puede cometer (por eso
  `validar` existe y los mensajes dicen qué campo falla).

## Alternativas descartadas

1. **Acciones escritas en el código:** rápido al principio, pero cada cambio
   requiere editar y reinstalar; imposible de adaptar sin saber Python.
2. **Leer el JSON sin validar:** un campo mal escrito rompería a mitad de una
   operación destructiva, justo lo que queremos evitar.
