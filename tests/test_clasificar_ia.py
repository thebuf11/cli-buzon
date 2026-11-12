"""clasificar-ia y comprobar-ia, sin red ni cuenta real."""

import io
import json
from datetime import datetime, timedelta, timezone

import pytest
import typer
from rich.console import Console
from typer.testing import CliRunner

from buzon import ia
from buzon.cli import app
from buzon.config import cargar_configuracion
from buzon.errores import SinRedError
from buzon.ia import Clasificacion, ProveedorIA, interpretar_clasificacion
from buzon.imap_client import Correo
from buzon.motor import Motor

AHORA = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)


def correo(uid, asunto, horas_atras=1, importante=False):
    return Correo(uid, f"Remitente {uid} <r{uid}@ejemplo.com>", asunto, AHORA - timedelta(hours=horas_atras), importante)


# ── interpretar la respuesta de la IA ─────────────────────────


def test_interpreta_lista_aunque_tenga_texto_alrededor():
    respuesta = (
        "Claro, aquí tienes:\n"
        '[{"n": 1, "categoria": "prescindible", "motivo": "publicidad"},'
        ' {"n": 2, "categoria": "Importante", "motivo": "tutoría"}]\n'
        "Espero que te sirva [de ayuda]."
    )
    resultado = interpretar_clasificacion(respuesta, 2)
    assert resultado == {
        1: Clasificacion("prescindible", "publicidad"),
        2: Clasificacion("importante", "tutoría"),
    }


def test_interpreta_formato_diccionario():
    resultado = interpretar_clasificacion('{"1": "prescindible", "2": {"categoria": "leer"}}', 2)
    assert resultado[1].categoria == "prescindible"
    assert resultado[2].categoria == "leer"


def test_categoria_inventada_y_numeros_fuera_de_rango():
    respuesta = '[{"n": 1, "categoria": "basura"}, {"n": 7, "categoria": "prescindible"}, {"n": "x"}]'
    resultado = interpretar_clasificacion(respuesta, 2)
    assert resultado == {1: Clasificacion("leer", "")}  # lo dudoso nunca se borra


@pytest.mark.parametrize("respuesta", ["No sé clasificar esto.", '[{"n": 1, "categoria": '])
def test_respuesta_sin_json_o_rota(respuesta):
    with pytest.raises(SinRedError, match="JSON"):
        interpretar_clasificacion(respuesta, 1)


class RespuestaFalsa:
    def __init__(self, contenido):
        self.cuerpo = json.dumps({"choices": [{"message": {"content": contenido}}]}).encode("utf-8")

    def read(self):
        return self.cuerpo

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_clasificar_correo_olvidado_queda_como_leer(monkeypatch):
    monkeypatch.setattr(
        ia.urllib.request,
        "urlopen",
        lambda peticion, timeout: RespuestaFalsa('[{"n": 1, "categoria": "prescindible", "motivo": "oferta"}]'),
    )
    proveedor = ProveedorIA("http://localhost/v1/chat/completions", "", "llama3")
    resultado = proveedor.clasificar([correo("a", "Oferta"), correo("b", "Hola")])
    assert resultado["a"].categoria == "prescindible"
    assert resultado["b"].categoria == "leer"


# ── acción clasificar-ia ──────────────────────────────────────


class ClienteFalso:
    def __init__(self, correos, fallan=()):
        self.correos = correos
        self.fallan = set(fallan)
        self.movidos = []

    def listar(self, carpeta, horas=None, ahora=None):
        return list(self.correos)

    def leer_texto(self, carpeta, uid):
        return f"Texto {uid}"

    def mover_uids_a_papelera(self, carpeta, uids, papelera):
        movidos = [uid for uid in uids if uid not in self.fallan]
        self.movidos.extend(movidos)
        return movidos


class IAFalsa:
    def __init__(self, categorias=None, disponible=True):
        self.categorias = categorias or {}
        self.disponible = disponible

    def comprobar(self):
        if not self.disponible:
            raise SinRedError("No hay IA configurada: define IA_API_URL.")

    def clasificar(self, correos, textos=None):
        return {c.uid: Clasificacion(self.categorias.get(c.uid, "leer"), "motivo") for c in correos}


def preparar(tmp_path, monkeypatch, cliente, ia_falsa, confirmar=True):
    ruta = tmp_path / "acciones.json"
    ruta.write_text(
        json.dumps(
            {
                "version": 1,
                "acciones": [
                    {"nombre": "limpiar-prescindibles", "descripcion": "Limpiar", "tipo": "clasificar-ia"}
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(ProveedorIA, "desde_entorno", classmethod(lambda cls, config: ia_falsa))
    preguntas = []

    def confirmar_falso(texto, default=False):
        preguntas.append(texto)
        return confirmar

    monkeypatch.setattr(typer, "confirm", confirmar_falso)
    salida = io.StringIO()
    consola = Console(file=salida, force_terminal=False, width=160)
    return Motor(cargar_configuracion(ruta), consola, cliente=cliente), salida, preguntas


def correos_de_prueba():
    return [correo("1", "Ofertas"), correo("2", "Tutoría"), correo("3", "Boletín")]


def test_simular_no_mueve_nada(tmp_path, monkeypatch):
    cliente = ClienteFalso(correos_de_prueba())
    motor, salida, preguntas = preparar(tmp_path, monkeypatch, cliente, IAFalsa({"1": "prescindible"}))
    assert motor.ejecutar("limpiar-prescindibles", simular=True) == 0
    assert cliente.movidos == []
    assert preguntas == []
    assert "Simulación" in salida.getvalue()


def test_confirmar_mueve_solo_los_prescindibles(tmp_path, monkeypatch):
    cliente = ClienteFalso(correos_de_prueba())
    ia_falsa = IAFalsa({"1": "prescindible", "2": "importante", "3": "prescindible"})
    motor, _, preguntas = preparar(tmp_path, monkeypatch, cliente, ia_falsa)
    assert motor.ejecutar("limpiar-prescindibles") == 0
    assert sorted(cliente.movidos) == ["1", "3"]
    assert len(preguntas) == 1


def test_cancelar_no_mueve_nada(tmp_path, monkeypatch):
    cliente = ClienteFalso(correos_de_prueba())
    motor, _, _ = preparar(tmp_path, monkeypatch, cliente, IAFalsa({"1": "prescindible"}), confirmar=False)
    assert motor.ejecutar("limpiar-prescindibles") == 0
    assert cliente.movidos == []


def test_lo_importante_para_gmail_nunca_se_borra(tmp_path, monkeypatch):
    cliente = ClienteFalso([correo("1", "Factura", importante=True), correo("2", "Ofertas")])
    ia_falsa = IAFalsa({"1": "prescindible", "2": "prescindible"})
    motor, _, _ = preparar(tmp_path, monkeypatch, cliente, ia_falsa)
    assert motor.ejecutar("limpiar-prescindibles", si=True) == 0
    assert cliente.movidos == ["2"]


def test_sin_ia_no_se_borra_nada(tmp_path, monkeypatch):
    cliente = ClienteFalso(correos_de_prueba())
    motor, salida, _ = preparar(tmp_path, monkeypatch, cliente, IAFalsa(disponible=False))
    assert motor.ejecutar("limpiar-prescindibles", si=True) == 0
    assert cliente.movidos == []
    assert "No se ha borrado nada" in salida.getvalue()


def test_fallo_parcial_al_mover_devuelve_1(tmp_path, monkeypatch):
    cliente = ClienteFalso(correos_de_prueba(), fallan={"3"})
    ia_falsa = IAFalsa({"1": "prescindible", "3": "prescindible"})
    motor, _, _ = preparar(tmp_path, monkeypatch, cliente, ia_falsa)
    assert motor.ejecutar("limpiar-prescindibles", si=True) == 1
    assert cliente.movidos == ["1"]


# ── buzon comprobar-ia ────────────────────────────────────────

runner = CliRunner()


def config_minima(tmp_path):
    ruta = tmp_path / "acciones.json"
    ruta.write_text(
        json.dumps({"version": 1, "acciones": [{"nombre": "spam", "descripcion": "Spam", "tipo": "listar"}]}),
        encoding="utf-8",
    )
    return str(ruta)


@pytest.fixture
def sin_entorno_ia(monkeypatch):
    for variable in ("IA_API_URL", "IA_API_KEY", "IA_MODELO"):
        monkeypatch.delenv(variable, raising=False)


def test_comprobar_ia_sin_configurar_sale_con_1(tmp_path, sin_entorno_ia):
    resultado = runner.invoke(app, ["--config", config_minima(tmp_path), "comprobar-ia"])
    assert resultado.exit_code == 1
    assert "no definida" in resultado.output


def test_comprobar_ia_responde_y_no_muestra_secretos(tmp_path, monkeypatch, sin_entorno_ia):
    monkeypatch.setenv("IA_API_URL", "https://usuario:secreto@ia.ejemplo.com/v1/chat/completions?key=CLAVE123")
    monkeypatch.setenv("IA_API_KEY", "sk-MUYSECRETA")
    monkeypatch.setattr(ia.urllib.request, "urlopen", lambda peticion, timeout: RespuestaFalsa("OK"))

    resultado = runner.invoke(app, ["--config", config_minima(tmp_path), "comprobar-ia"])
    assert resultado.exit_code == 0
    assert "la IA responde" in resultado.output
    for secreto in ("secreto", "CLAVE123", "MUYSECRETA"):
        assert secreto not in resultado.output
    assert "ia.ejemplo.com/v1/chat/completions" in resultado.output
