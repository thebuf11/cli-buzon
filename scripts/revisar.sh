#!/bin/sh
# Pide al subagente «revisor» de OpenCode que revise los cambios antes de un commit.
#
#   scripts/revisar.sh              # cambios sin commitear (staged y sin stage)
#   scripts/revisar.sh HEAD~3       # lo que ha cambiado desde HEAD~3
#
# El revisor es de solo lectura (.opencode/agents/revisor.md): solo puede ejecutar
# git diff/status/log/show, los tests y «buzon validar».
set -eu

cd "$(dirname "$0")/.."

if ! command -v opencode >/dev/null 2>&1; then
    echo "ERROR: no se encuentra «opencode». Instálalo: https://opencode.ai" >&2
    exit 1
fi

if [ $# -gt 0 ]; then
    base=$1
    if ! git rev-parse --verify --quiet "$base" >/dev/null; then
        echo "ERROR: «$base» no es un commit válido." >&2
        exit 2
    fi
    alcance="los cambios entre $base y HEAD (usa: git diff $base..HEAD y git log $base..HEAD)"
else
    if git diff --quiet HEAD && [ -z "$(git ls-files --others --exclude-standard)" ]; then
        echo "No hay cambios sin commitear que revisar."
        exit 0
    fi
    alcance="los cambios sin commitear (usa: git status --short y git diff HEAD; incluye los ficheros nuevos)"
fi

exec opencode run --agent revisor --title "revisión $(date +%Y-%m-%d)" \
    "Revisa $alcance siguiendo tu lista de comprobación y responde con tu formato."
