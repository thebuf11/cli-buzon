"""Diseño: clases abstractas, registro de acciones, aserciones y --simular sin IA."""

import json

import pytest
from typer.testing import CliRunner

from buzon import ia
from buzon.acciones import ACCIONES, AccionBase
from buzon.cli import app
from buzon.config import TIPOS_VALIDOS
from buzon.ia import ProveedorCentro, ProveedorIA
from buzon.imap_client import Correo

runner = CliRunner()


def correo(uid, asunto, importante=False):
    return Correo(uid=uid, remitente="Ana <ana@x.es>", asunto=asunto, fecha=None, importante=importante)


# ── Clases abstractas ────────────────────────────────────────────────


def test_proveedor_ia_es_abstracto():
    with pytest.raises(TypeError):
        ProveedorIA()


def test_accion_base_es_abstracta():
    with pytest.raises(TypeError):
        AccionBase(None, None)


def test_resumir_vive_en_la_base_y_solo_usa_completar(proveedor_falso):
    falso = proveedor_falso("## 🔴 Urgente\n- Examen en el aula B12")
    assert falso.resumir([correo("1", "Cambio de aula")], 24, {"1": "Aula B12"}).startswith("## 🔴")
    enviado = falso.recibido[0][1]["content"]
    assert "Cambio de aula" in enviado and "Aula B12" in enviado


def test_clasificar_con_la_base_no_mezcla_correos(proveedor_falso):
    falso = proveedor_falso('[{"n": 1, "categoria": "prescindible", "motivo": "publicidad"}]')
    resultado = falso.clasificar([correo("a", "Oferta"), correo("b", "Reunión")])
    assert resultado["a"].categoria == "prescindible"
    assert resultado["b"].categoria == "leer"  # no lo mencionó: no se toca


def test_la_clave_no_es_un_atributo_publico():
    proveedor = ProveedorCentro("https://h/v1", "sk-secreta", "m")
    assert not hasattr(proveedor, "clave")
    assert proveedor.clave_definida is True


def test_construir_endpoint_es_estatico():
    assert ProveedorCentro.construir_endpoint("https://h/v1/") == "https://h/v1/chat/completions"


# ── Registro de acciones ─────────────────────────────────────────────


def test_cada_tipo_valido_tiene_su_clase_y_al_reves():
    # Si alguien añade un tipo a config.py y olvida la clase (o al revés), falla aquí.
    assert set(ACCIONES) == TIPOS_VALIDOS
    assert all(issubclass(clase, AccionBase) for clase in ACCIONES.values())


# ── --simular no llama al modelo ─────────────────────────────────────


@pytest.fixture
def config_ia(tmp_path):
    acciones = [
        {"nombre": "resumen-24h", "descripcion": "Resumen", "tipo": "resumen-ia"},
        {"nombre": "guardar", "descripcion": "Guardar", "tipo": "exportar", "destino": str(tmp_path / "res")},
    ]
    ruta = tmp_path / "acciones.json"
    ruta.write_text(json.dumps({"version": 1, "acciones": acciones}), encoding="utf-8")
    return ruta


@pytest.fixture
def sin_llamadas(monkeypatch):
    """Cualquier petición a la IA hace fallar el test."""

    def urlopen(*args, **kwargs):
        pytest.fail("--simular no debe llamar a la IA")

    monkeypatch.setattr(ia.urllib.request, "urlopen", urlopen)


def test_resumen_simulado_dice_que_enviaria_sin_llamar(config_ia, monkeypatch, sin_llamadas):
    monkeypatch.setenv("CENTRO_IA_URL", "https://ia.simarro/llmapi/v1")
    resultado = runner.invoke(app, ["--demo", "--config", str(config_ia), "ejecutar", "resumen-24h", "--simular"])
    salida = " ".join(resultado.output.split())
    assert resultado.exit_code == 0, resultado.output
    assert "no se ha llamado a la IA" in salida
    assert "ia.simarro" in salida and "tokens" in salida


def test_resumen_simulado_sin_ia_lo_dice(config_ia, sin_llamadas):
    resultado = runner.invoke(app, ["--demo", "--config", str(config_ia), "ejecutar", "resumen-24h", "--simular"])
    assert resultado.exit_code == 0
    assert "sin IA no se enviaría nada" in " ".join(resultado.output.split())


def test_exportar_simulado_no_escribe_ni_llama(config_ia, monkeypatch, sin_llamadas, tmp_path):
    monkeypatch.setenv("CENTRO_IA_URL", "https://ia.simarro/llmapi/v1")
    resultado = runner.invoke(app, ["--demo", "--config", str(config_ia), "ejecutar", "guardar", "--simular"])
    assert resultado.exit_code == 0, resultado.output
    assert "se escribiría" in " ".join(resultado.output.split())
    assert not (tmp_path / "res").exists()


# ── --demo sin buzon init ────────────────────────────────────────────


def test_demo_sin_acciones_json_usa_las_de_ejemplo(tmp_path, monkeypatch):
    # Sin --config: buscar_configuracion devuelve una ruta que no existe.
    no_existe = tmp_path / "nada" / "acciones.json"
    monkeypatch.setattr("buzon.cli.buscar_configuracion", lambda explicita=None: no_existe)
    resultado = runner.invoke(app, ["--demo", "ejecutar", "listar-spam"])
    assert resultado.exit_code == 0, resultado.output
    assert "acciones de ejemplo" in " ".join(resultado.output.split())
    assert "HAS GANADO" in resultado.output


def test_sin_demo_y_sin_acciones_json_sigue_siendo_error_3(tmp_path):
    resultado = runner.invoke(app, ["--config", str(tmp_path / "nada.json"), "acciones"])
    assert resultado.exit_code == 3


def test_demo_con_config_mal_escrito_es_error_3(tmp_path):
    # Con --config el usuario pidió ese fichero: no se cambia en silencio por el de ejemplo.
    resultado = runner.invoke(app, ["--demo", "--config", str(tmp_path / "mis-acciones.jsn"), "acciones"])
    assert resultado.exit_code == 3


def test_simular_cuenta_como_maximo_los_correos_que_caben(tmp_path, monkeypatch, sin_llamadas):
    from buzon.acciones import AccionResumenIA
    from buzon.ia import MAX_CORREOS_RESUMEN

    class Motor:
        def __init__(self):
            import io

            from rich.console import Console

            self.salida = io.StringIO()
            self.consola = Console(file=self.salida, width=300)
            self.config = None

        def cliente(self):
            return self

        def leer_texto(self, carpeta, uid):
            return ""

    monkeypatch.setattr(ProveedorIA, "desde_entorno", classmethod(lambda cls, c: ProveedorCentro("https://ia.simarro/v1", "", "m")))
    motor = Motor()
    accion = AccionResumenIA.__new__(AccionResumenIA)
    accion.definicion, accion.motor = None, motor
    correos = [correo(str(n), f"Asunto {n}") for n in range(MAX_CORREOS_RESUMEN + 20)]
    accion._simular_envio("INBOX", correos, 24)
    assert f"Se enviarían {MAX_CORREOS_RESUMEN} correos" in motor.salida.getvalue()
    assert "ia.simarro" in motor.salida.getvalue()


def test_errores_de_clasificacion_tambien_son_ia_no_disponible():
    from buzon.errores import IANoDisponible
    from buzon.ia import interpretar_clasificacion

    with pytest.raises(IANoDisponible):
        interpretar_clasificacion("no es JSON", 3)
