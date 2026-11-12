# Spec · buzon

1. **Para quién:** un estudiante de DAM que revisa su Gmail todos los días.
2. **Problema:** pierde tiempo mirando correo y separando spam a mano.
3. **Órdenes:** `buzon`, `version`, `revisar`, `listar`, `acciones`, `validar`, `ejecutar`.
4. **Acción 1:** `resumen-24h` — resumen con IA del contenido de los correos de las últimas 24 h (urgente · para leer · ignorar).
5. **Acción 2:** `listar-spam` — tabla de la carpeta de spam (funciona sin IA y sin red).
6. **Acción 3:** `limpiar-spam` — mueve todo el spam a la papelera, con confirmación.
7. **Acción 4:** `guardar-resumen` — escribe el resumen del día en `~/resumenes/*.md`.
8. **Acción 5:** `revisar-24h` — lista numerada de las últimas 24 h; ver un correo y mover a la papelera los elegidos, con confirmación.
9. **No hace:** no envía correo, no borra definitivamente, no toca carpetas que no se le indiquen.
10. **Seguridad:** credenciales en `.env` (IMAP) o `credentials.json` + `token.json` (API de Gmail, OAuth), todo fuera de git; `--simular` antes de cualquier cambio.
11. **Conexión:** IMAP (993) o API de Gmail por HTTPS (443) para redes que bloquean el 993; se elige con `cuenta.proveedor`.
12. **Hecho cuando:** se instala con una orden y funciona en Windows, Linux y macOS.
