---
description: Añade una acción nueva a acciones.json a partir de una descripción y la valida
agent: build
---

Quiero una acción nueva en `acciones.json` para esto: **$ARGUMENTS**

Sigue estos pasos en orden:

1. Carga la skill `acciones-json` y elige el `tipo` que encaje. Si ninguno
   encaja, **para** y explícame qué tipo nuevo haría falta. No toques el
   código sin preguntarme.
2. Propón la entrada JSON completa, con un `nombre` en minúsculas y guiones que
   no exista ya. Las acciones actuales son estas:

!`uv run buzon acciones`

3. Añádela al final de la lista `acciones` de `acciones.json`. No cambies las
   demás acciones ni las secciones `cuenta` e `ia`.
4. Comprueba que el fichero sigue siendo válido:

   ```bash
   uv run buzon validar
   ```

   Si sale con código 3, corrige el campo que indique y repite.
5. Si la acción puede borrar (`mover-papelera`, `clasificar-ia`, `revisar`),
   asegúrate de que pide confirmación y dime que la pruebe yo con
   `buzon ejecutar NOMBRE --simular`. **No la ejecutes tú**: usa mi correo real.
6. Termina enseñándome el `git diff acciones.json` y un mensaje de commit
   sugerido. **No hagas el commit.**
