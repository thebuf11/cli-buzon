"""Modo demo: la CLI entera funciona con correos de ejemplo, sin Gmail ni contraseñas."""

import json
from datetime import datetime, timezone

import pytest
from typer.testing import CliRunner

from buzon.cli import app
from buzon.config import cargar_configuracion
from buzon.demo import ClienteDemo
from buzon.errores import AccionNoValida

runner = CliRunner()

AHORA = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def cuenta(tmp_path):
    ruta = tmp_path / "acciones.json"
    ruta.write_text(
        json.dumps({"version": 1, "acciones": [{"nombre": "x", "descripcion": "x", "tipo": "listar"}]}),
        encoding="utf-8",
    )
    return cargar_configuracion(ruta).cuenta


@pytest.fixture
def config_completa(tmp_path):
    """Las acciones del proyecto, en una carpeta temporal (sin .env real al lado)."""
    acciones = [
        {"nombre": "resumen-24h", "descripcion": "Resumen", "tipo": "resumen-ia", "horas": 24},
        {"nombre": "listar-spam", "descripcion": "Spam", "tipo": "listar", "carpeta": "spam"},
        {
            "nombre": "limpiar-spam",
            "descripcion": "Vaciar spam",
            "tipo": "mover-papelera",
            "carpeta": "spam",
            "confirmar": True,
        },
    ]
    ruta = tmp_path / "acciones.json"
    ruta.write_text(json.dumps({"version": 1, "acciones": acciones}), encoding="utf-8")
    return str(ruta)


def test_hay_correos_en_entrada_y_spam_y_la_papelera_empieza_vacia(cuenta):
    cliente = ClienteDemo(cuenta, ahora=AHORA).conectar()
    assert len(cliente.listar("INBOX", horas=None)) >= 10
    assert len(cliente.listar("[Gmail]/Spam", horas=None)) >= 3
    assert cliente.listar("[Gmail]/Trash", horas=None) == []


def test_la_ventana_de_horas_filtra_desde_ahora(cuenta):
    cliente = ClienteDemo(cuenta, ahora=AHORA).conectar()
    todos = cliente.listar("INBOX", horas=None, ahora=AHORA)
    recientes = cliente.listar("INBOX", horas=24, ahora=AHORA)
    assert 0 < len(recientes) < len(todos)
    assert any(correo.importante for correo in recientes)


def test_leer_texto_devuelve_el_cuerpo(cuenta):
    cliente = ClienteDemo(cuenta, ahora=AHORA).conectar()
    primero = cliente.listar("INBOX", horas=None)[0]
    assert "B12" in cliente.leer_texto("INBOX", primero.uid)


def test_borrar_solo_mueve_en_memoria(cuenta):
    cliente = ClienteDemo(cuenta, ahora=AHORA).conectar()
    spam = cliente.listar("[Gmail]/Spam", horas=None)
    movidos = cliente.mover_uids_a_papelera("[Gmail]/Spam", [spam[0].uid], "[Gmail]/Trash")
    assert movidos == [spam[0].uid]
    assert len(cliente.listar("[Gmail]/Spam", horas=None)) == len(spam) - 1
    assert [c.uid for c in cliente.listar("[Gmail]/Trash", horas=None)] == [spam[0].uid]
    # Un cliente nuevo vuelve a tenerlo todo: nada se guarda.
    assert len(ClienteDemo(cuenta).conectar().listar("[Gmail]/Spam", horas=None)) == len(spam)


def test_carpeta_desconocida_da_un_error_controlado(cuenta):
    cliente = ClienteDemo(cuenta).conectar()
    with pytest.raises(AccionNoValida, match="modo demo"):
        cliente.listar("Boletines")


def test_validar_acepta_el_proveedor_demo(tmp_path):
    ruta = tmp_path / "acciones.json"
    ruta.write_text(
        json.dumps(
            {
                "version": 1,
                "cuenta": {"proveedor": "demo"},
                "acciones": [{"nombre": "x", "descripcion": "x", "tipo": "listar"}],
            }
        ),
        encoding="utf-8",
    )
    resultado = runner.invoke(app, ["--config", str(ruta), "validar"])
    assert resultado.exit_code == 0
    assert "modo demo" in resultado.output


def test_cli_listar_con_demo_no_pide_credenciales(config_completa):
    resultado = runner.invoke(app, ["--demo", "--config", config_completa, "listar", "spam", "--horas", "0"])
    assert resultado.exit_code == 0, resultado.output
    assert "Modo demo" in resultado.output
    assert "HAS GANADO" in resultado.output


def test_buzon_demo_por_variable_de_entorno(config_completa, monkeypatch):
    monkeypatch.setenv("BUZON_DEMO", "1")
    resultado = runner.invoke(app, ["--config", config_completa, "listar", "entrada"])
    assert resultado.exit_code == 0, resultado.output
    assert "Modo demo" in resultado.output


def test_limpiar_spam_simulado_en_demo(config_completa):
    resultado = runner.invoke(app, ["--demo", "--config", config_completa, "ejecutar", "limpiar-spam", "--simular"])
    salida = " ".join(resultado.output.split())
    assert resultado.exit_code == 0, resultado.output
    assert "Modo demo" in salida
    assert "HAS GANADO" in salida  # enseña lo que movería…
    assert "OK:" not in salida  # …pero no lo mueve


def test_limpiar_spam_con_si_en_demo_mueve_solo_en_memoria(config_completa):
    resultado = runner.invoke(app, ["--demo", "--config", config_completa, "ejecutar", "limpiar-spam", "--si"])
    assert resultado.exit_code == 0, resultado.output
    # La siguiente orden vuelve a ver todo el spam: no se guardó nada.
    otra = runner.invoke(app, ["--demo", "--config", config_completa, "listar", "spam", "--horas", "0"])
    assert "HAS GANADO" in otra.output


def test_proveedor_demo_en_acciones_json_funciona_por_el_motor(tmp_path):
    import io

    from rich.console import Console

    from buzon.motor import Motor

    ruta = tmp_path / "acciones.json"
    ruta.write_text(
        json.dumps(
            {
                "version": 1,
                "cuenta": {"proveedor": "demo"},
                "acciones": [{"nombre": "spam", "descripcion": "x", "tipo": "listar", "carpeta": "spam"}],
            }
        ),
        encoding="utf-8",
    )
    salida = io.StringIO()
    with Motor(cargar_configuracion(ruta), Console(file=salida, width=160)) as motor:
        assert isinstance(motor.cliente(), ClienteDemo)
        assert motor.ejecutar("spam") == 0
    assert "HAS GANADO" in salida.getvalue()


def test_demo_json_roto_da_error_controlado(monkeypatch, cuenta):
    from buzon.errores import ConfigError

    monkeypatch.setattr(ClienteDemo, "_leer_plantilla", staticmethod(lambda: {"entrada": [{"asunto": "sin remitente"}]}))
    with pytest.raises(ConfigError, match="remitente"):
        ClienteDemo(cuenta).conectar()


def test_resumen_en_demo_sin_ia_avisa_y_no_revienta(config_completa):
    resultado = runner.invoke(app, ["--demo", "--config", config_completa, "ejecutar", "resumen-24h"])
    assert resultado.exit_code == 0, resultado.output
    assert "Reunión de tutores" in resultado.output  # la tabla sale aunque no haya IA
    assert "CENTRO_IA_URL" in resultado.output + (getattr(resultado, "stderr", "") or "")


def test_flujo_completo_en_demo_contestando_no(config_completa):
    resultado = runner.invoke(app, ["--demo", "--config", config_completa], input="n\n")
    assert resultado.exit_code == 0, resultado.output
    assert "No se ha borrado nada" in resultado.output
