"""Confirmaciones en español y órdenes sin teclado (tubería, script, chat)."""

import json

import pytest
import typer
from typer.testing import CliRunner

from buzon.cli import app
from buzon.imap_client import Correo
from buzon.motor import Motor
from buzon.salida import confirmar


def responder(monkeypatch, respuestas):
    cola = list(respuestas)
    preguntas = []

    def prompt(texto, **_):
        preguntas.append(texto)
        return cola.pop(0)

    monkeypatch.setattr(typer, "prompt", prompt)
    return preguntas


@pytest.mark.parametrize(
    ("respuesta", "esperado"),
    [("", False), ("n", False), ("No", False), ("s", True), ("sí", True), ("SI", True), ("y", True)],
)
def test_confirmar_respuestas(monkeypatch, respuesta, esperado):
    preguntas = responder(monkeypatch, [respuesta])
    assert confirmar("¿Seguro?") is esperado
    assert preguntas == ["¿Seguro? [s/N]"]


def test_confirmar_respuesta_rara_vuelve_a_preguntar(monkeypatch):
    preguntas = responder(monkeypatch, ["quizá", "s"])
    assert confirmar("¿Seguro?") is True
    assert len(preguntas) == 2  # «quizá» no cuenta como sí


# ── la CLI de verdad, con un cliente de correo falso ──────────


class ClienteFalso:
    def __init__(self):
        self.movidos = []

    def listar(self, carpeta, horas=None, ahora=None):
        return [Correo("1", "a@b.c", "Oferta", None), Correo("2", "a@b.c", "Otra", None)]

    def mover_a_papelera(self, carpeta, uids, papelera):
        self.movidos.extend(uids)
        return len(uids)

    def cerrar(self):
        pass


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    ruta = tmp_path / "acciones.json"
    ruta.write_text(
        json.dumps(
            {
                "version": 1,
                "acciones": [
                    {
                        "nombre": "vaciar-boletines",
                        "descripcion": "Vacía la carpeta de boletines",
                        "tipo": "mover-papelera",
                        "carpeta": "Boletines",
                        "confirmar": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    cliente = ClienteFalso()
    monkeypatch.setattr(Motor, "cliente", lambda self: cliente)
    return str(ruta), cliente


runner = CliRunner()


def salida(resultado):
    texto = resultado.output + (getattr(resultado, "stderr", "") or "")
    return " ".join(texto.split())  # Rich parte las líneas a 80 columnas


def test_ejecutar_sin_teclado_no_borra_y_lo_explica(entorno):
    ruta, cliente = entorno
    # input vacío = fin de la entrada, como en una tubería o un chat.
    resultado = runner.invoke(app, ["--config", ruta, "ejecutar", "vaciar-boletines"], input="")
    assert resultado.exit_code == 1
    assert cliente.movidos == []
    assert "no hay teclado" in salida(resultado)
    assert "--si" in salida(resultado)
    assert "Traceback" not in salida(resultado)


def test_ejecutar_pregunta_por_la_carpeta_real(entorno):
    ruta, cliente = entorno
    resultado = runner.invoke(app, ["--config", ruta, "ejecutar", "vaciar-boletines"], input="s\n")
    assert resultado.exit_code == 0
    assert "¿Mover TODOS los 2 mensajes de «Boletines» a la papelera? [s/N]" in salida(resultado)
    assert "spam" not in salida(resultado).lower()
    assert cliente.movidos == ["1", "2"]


def test_ejecutar_enter_es_no(entorno):
    ruta, cliente = entorno
    resultado = runner.invoke(app, ["--config", ruta, "ejecutar", "vaciar-boletines"], input="\n")
    assert resultado.exit_code == 0
    assert cliente.movidos == []
    assert "Cancelado" in salida(resultado)


def test_ejecutar_con_si_no_pregunta(entorno):
    ruta, cliente = entorno
    resultado = runner.invoke(app, ["--config", ruta, "ejecutar", "vaciar-boletines", "--si"], input="")
    assert resultado.exit_code == 0
    assert cliente.movidos == ["1", "2"]
