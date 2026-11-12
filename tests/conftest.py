"""Configuración común de los tests: ninguno debe tocar secretos ni servicios reales."""

import os

import pytest

VARIABLES_REALES = (
    "BUZON_CONFIG",
    "GMAIL_USUARIO",
    "GMAIL_APP_PASSWORD",
    "IA_API_URL",
    "IA_API_KEY",
    "IA_MODELO",
)


@pytest.fixture(autouse=True)
def entorno_aislado(monkeypatch):
    """Cada test empieza sin las variables del alumno y deja el entorno como estaba.

    ``cargar_env`` usa ``os.environ.setdefault``, que monkeypatch no deshace:
    sin esto, un test que cargase un .env dejaría credenciales o IA_API_URL
    para los siguientes, y uno de ellos podría llamar a la IA de verdad.
    """
    for variable in VARIABLES_REALES:
        monkeypatch.delenv(variable, raising=False)
    copia = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(copia)
