# Spec · buzon

1. **Para quién:** un estudiante de DAM que revisa su Gmail todos los días.
2. **Problema:** pierde tiempo mirando correo y separando spam y publicidad a mano.
3. **Órdenes:** `buzon` (flujo completo), `version`, `init`, `acciones`, `validar`, `comprobar-ia`, `listar`, `revisar`, `ejecutar`.
4. **Acción 1:** `resumen-24h`: resumen con IA del contenido de los correos de las últimas 24 h (urgente · para leer · ignorar).
5. **Acción 2:** `listar-spam`: tabla de la carpeta de spam (funciona sin IA).
6. **Acción 3:** `limpiar-spam`: mueve todo el spam a la papelera, con confirmación.
7. **Acción 4:** `guardar-resumen`: escribe el resumen del día en `~/resumenes/*.md`.
8. **Acción 5:** `revisar-24h`: lista numerada de las últimas 24 h; se puede ver un correo y mover a la papelera los elegidos, con confirmación.
9. **Acción 6:** `limpiar-prescindibles`: la IA clasifica los correos y propone mover a la papelera la publicidad y los boletines; lo marcado con ⭐ nunca se borra.
10. **No hace:** no envía correo, no borra definitivamente (todo va a la papelera de Gmail), no toca carpetas que no se le indiquen y la IA nunca borra sin confirmación.
11. **Seguridad:** credenciales en `.env` (IMAP) o en `credentials.json` + `token.json` (API de Gmail, OAuth), todo fuera de git y protegido por un hook `pre-commit`; `--simular` antes de cualquier cambio.
12. **Conexión:** IMAP (993) o API de Gmail por HTTPS (443) para redes que bloquean el 993; se elige con `cuenta.proveedor`. IA: cualquier servicio compatible con OpenAI (ADR 0003).
13. **Sin red o sin IA:** la CLI explica el problema en una línea y sigue con las acciones que no la necesitan.
14. **Hecho cuando:** se instala con una orden (`uv tool install git+…`), `buzon init` deja una configuración válida y los tests pasan en Windows, Linux y macOS.
