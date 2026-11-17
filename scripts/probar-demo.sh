#!/bin/sh
# Pide al subagente «probador-demo» de OpenCode que pruebe la CLI en modo demo.
#
#   scripts/probar-demo.sh
#
# Úsalo antes de una release o antes de pedir la prueba cruzada a un compañero.
# El probador solo puede ejecutar «buzon --demo …», validar, acciones,
# comprobar-ia y los tests (.opencode/agents/probador-demo.md): nunca toca el
# correo real ni edita ficheros.
set -eu

cd "$(dirname "$0")/.."

if ! command -v opencode >/dev/null 2>&1; then
    echo "ERROR: no se encuentra «opencode». Instálalo: https://opencode.ai" >&2
    exit 1
fi

exec opencode run --agent probador-demo --title "prueba demo $(date +%Y-%m-%d)" \
    "Prueba la CLI siguiendo tu lista de pruebas completa y responde con tu formato."
