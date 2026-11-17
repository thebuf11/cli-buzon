"""Configuración común de los tests: ninguno debe tocar secretos ni servicios reales."""

import os

import pytest

VARIABLES_REALES = (
    "BUZON_CONFIG",
    "GMAIL_USUARIO",
    "GMAIL_APP_PASSWORD",
    "BUZON_DEMO",
    "CENTRO_IA_URL",
    "CENTRO_IA_KEY",
    "CENTRO_IA_MODELO",
    # OpenCode usa las mismas variables: si el alumno las exporta en su terminal,
    # un test podría llamar a la IA del centro de verdad.
    "CENTRO_IA_CA",
)


@pytest.fixture(autouse=True)
def entorno_aislado(monkeypatch):
    """Cada test empieza sin las variables del alumno y deja el entorno como estaba.

    ``cargar_env`` usa ``os.environ.setdefault``, que monkeypatch no deshace:
    sin esto, un test que cargase un .env dejaría credenciales o CENTRO_IA_URL
    para los siguientes, y uno de ellos podría llamar a la IA de verdad.
    """
    for variable in VARIABLES_REALES:
        monkeypatch.delenv(variable, raising=False)
    copia = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(copia)


@pytest.fixture
def proveedor_falso():
    """Un ProveedorIA de verdad (subclase de la ABC) que responde lo que digas, sin red.

    Uso: ``ia = proveedor_falso("## Resumen…")``; ``ia.recibido`` guarda los mensajes.
    """
    from buzon.ia import ProveedorIA

    class ProveedorFalso(ProveedorIA):
        modelo = "falso"

        def __init__(self, respuesta: str = "OK") -> None:
            self.respuesta = respuesta
            self.recibido: list = []

        def completar(self, mensajes, temperatura=0.2, timeout=None):
            self.recibido.append(mensajes)
            return self.respuesta

    return ProveedorFalso
