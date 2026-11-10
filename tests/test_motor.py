import io
import json

import pytest
from rich.console import Console

from buzon.config import cargar_configuracion
from buzon.errores import AccionNoValida
from buzon.imap_client import Correo
from buzon.motor import Motor


class ClienteFalso:
    """Imita a ClienteIMAP sin red ni cuenta real."""

    def __init__(self, correos):
        self.correos = correos
        self.movidos = []
        self.cerrado = False

    def listar(self, carpeta, horas=None, ahora=None):
        return list(self.correos)

    def mover_a_papelera(self, carpeta, uids, papelera):
        self.movidos.extend(uids)
        return len(uids)

    def cerrar(self):
        self.cerrado = True


def crear_config(tmp_path):
    datos = {
        "version": 1,
        "acciones": [
            {"nombre": "listar-spam", "descripcion": "Spam", "tipo": "listar", "carpeta": "spam"},
            {
                "nombre": "limpiar-spam",
                "descripcion": "Limpiar",
                "tipo": "mover-papelera",
                "carpeta": "spam",
                "confirmar": True,
            },
        ],
    }
    ruta = tmp_path / "acciones.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    return cargar_configuracion(ruta)


def consola_silenciosa():
    return Console(file=io.StringIO(), force_terminal=False, width=120)


def test_simular_no_mueve_nada(tmp_path):
    cliente = ClienteFalso([Correo("1", "a@b.c", "Oferta", None)])
    motor = Motor(crear_config(tmp_path), consola_silenciosa(), cliente=cliente)
    assert motor.ejecutar("limpiar-spam", simular=True) == 0
    assert cliente.movidos == []


def test_limpiar_con_si_mueve_todo(tmp_path):
    cliente = ClienteFalso(
        [Correo("1", "a@b.c", "Oferta", None), Correo("2", "a@b.c", "Otra", None)]
    )
    motor = Motor(crear_config(tmp_path), consola_silenciosa(), cliente=cliente)
    assert motor.ejecutar("limpiar-spam", si=True) == 0
    assert cliente.movidos == ["1", "2"]


def test_listar_no_modifica_nada(tmp_path):
    cliente = ClienteFalso([])
    motor = Motor(crear_config(tmp_path), consola_silenciosa(), cliente=cliente)
    assert motor.ejecutar("listar-spam") == 0
    assert cliente.movidos == []


def test_accion_inexistente(tmp_path):
    motor = Motor(crear_config(tmp_path), consola_silenciosa(), cliente=ClienteFalso([]))
    with pytest.raises(AccionNoValida):
        motor.ejecutar("no-existe")
