# ADR 0002 · API de Gmail como alternativa a IMAP

- **Estado:** aceptado
- **Fecha:** 2026-11-10

## Contexto

En la red del centro, la salida a `imap.gmail.com:993` está bloqueada (TCP sin
respuesta), mientras que `gmail.googleapis.com:443` funciona. Gmail no ofrece
IMAP en ningún otro puerto, así que sin cambios la herramienta no sirve en esa
red. El puerto 993 es el del servidor remoto: no hay conflicto con aplicaciones
locales que escuchen en el 993.

## Decisión

Se añade un segundo cliente, `ClienteGmailAPI` (`gmail_api.py`), que habla con
la API REST de Gmail por HTTPS. Tiene **la misma interfaz** que `ClienteIMAP`
(`listar`, `leer_texto`, `mover_uids_a_papelera`…), así que acciones y motor no
cambian. Se elige con `cuenta.proveedor` en `acciones.json` (`imap` por
defecto, o `gmail-api`).

- Autenticación OAuth 2.0 de app de escritorio con PKCE; servidor de
  redirección en `127.0.0.1` con puerto elegido por el sistema.
- Alcance `gmail.modify`: permite leer y mandar a la papelera, **no** borrar
  definitivamente ni enviar correo (coherente con la spec).
- Solo librería estándar (`urllib`, `http.server`, `hashlib`, `base64`):
  se evita añadir `google-api-python-client` y sus dependencias.

## Consecuencias

**A favor:** funciona en redes que solo dejan salir HTTPS; no necesita la
contraseña de aplicación; el permiso se puede revocar desde la cuenta de Google.

**En contra:** hay que crear un proyecto en Google Cloud una vez; mientras la
app esté «en pruebas», Google muestra un aviso de app no verificada y el
`refresh_token` puede caducar a los 7 días (basta con volver a iniciar sesión).
Hay dos clientes que mantener, cubiertos por pruebas sin red.
