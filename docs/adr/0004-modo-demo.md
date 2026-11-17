# ADR 0004 · Modo demo con correos de ejemplo

- **Estado:** aceptado
- **Fecha:** 2026-11-17

## Contexto

El profesor tiene que poder instalar `buzon` y probarlo con la IA del centro.
Pero todas las acciones necesitan un buzón:

- `credentials.json` (cliente OAuth de la API de Gmail) es un secreto y no está
  en el repositorio. Además, la app de Google Cloud está «en pruebas» y solo
  admite a los usuarios de prueba que añade el alumno.
- IMAP necesita la contraseña de aplicación de una cuenta, y en la red del
  centro el puerto 993 está bloqueado (ADR 0002).
- Pedir a quien corrige que use su propio correo es pedirle que dé acceso de
  lectura y borrado a una herramienta que está evaluando.

## Decisión

Se añade un tercer proveedor, `"demo"`, con un cliente `ClienteDemo`
(`src/buzon/demo.py`) que tiene **la misma interfaz** que `ClienteIMAP` y
`ClienteGmailAPI` (`listar`, `leer_texto`, `mover_uids_a_papelera`…). Motor y
acciones no cambian: el motor elige el cliente igual que con los otros dos.

- Los correos salen de `src/buzon/plantillas/demo.json`, que va dentro del
  paquete y por eso funciona instalado desde GitHub. Cada correo guarda
  `hace_horas` en lugar de una fecha fija, para que siempre caiga en la
  ventana de las últimas 24 h.
- Hay de todo para que cada acción tenga algo que hacer: importantes (⭐) con
  fechas y plazos para el resumen, publicidad y boletines para
  `limpiar-prescindibles`, spam, y correos de más de 24 h para `--horas`.
- Lo que se «borra» solo se mueve entre listas en memoria. Al acabar la orden
  no queda nada.
- Se activa con `buzon --demo …` o `BUZON_DEMO=1`, sin tocar `acciones.json`,
  o con `"proveedor": "demo"` si se quiere fijo.
- La IA es la de verdad: el modo demo solo sustituye el buzón.

## Consecuencias

**A favor**

- Cualquiera puede probar todas las órdenes en un minuto, sin cuenta ni
  secretos, incluso en la red del centro.
- Las órdenes destructivas se pueden enseñar sin miedo: `limpiar-spam --si`
  en modo demo no borra nada real.
- Al tener la misma interfaz que los otros clientes, se demuestra que el
  diseño admite cambiar el origen del correo sin tocar acciones ni motor.

**En contra**

- Es otro cliente que mantener: si la interfaz de los clientes cambia, hay que
  cambiar también `ClienteDemo` (los tests de `tests/test_demo.py` lo
  detectan).
- El modo demo no prueba la conexión real con Gmail. Para eso siguen los tests
  de `test_imap.py` y `test_gmail_api.py`.

## Alternativas descartadas

- **Compartir el `credentials.json` del alumno y añadir al profesor como
  usuario de prueba:** reparte un secreto por canales ajenos al repositorio y
  sigue obligando a dar acceso a un correo real.
- **Una cuenta de Gmail de pruebas con la contraseña en el README:** sería un
  secreto publicado, justo lo que prohíbe el proyecto.
- **Leer correos de una carpeta de ficheros `.eml`:** más realista, pero obliga
  a preparar ficheros y no aporta nada para probar las acciones.
