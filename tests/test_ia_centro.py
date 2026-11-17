"""IA del centro (IES Simarro): URL base, certificado propio y errores con nombre y apellidos.

Ningún test sale a la red: ``urlopen`` se sustituye por un falso.
"""

import json
import ssl
import urllib.error

import pytest
from typer.testing import CliRunner

from buzon import ia
from buzon.cli import app
from buzon.errores import IANoDisponible, SinRedError
from buzon.ia import ProveedorIA

runner = CliRunner()


class RespuestaFalsa:
    def __init__(self, contenido="OK"):
        self.cuerpo = json.dumps({"choices": [{"message": {"content": contenido}}]}).encode("utf-8")

    def read(self):
        return self.cuerpo

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def capturar(monkeypatch, respuesta=None, error=None):
    """Sustituye urlopen y guarda con qué se le llamó."""
    llamadas = []

    def urlopen(peticion, timeout, **extra):
        llamadas.append({"url": peticion.full_url, "cabeceras": dict(peticion.headers), **extra})
        if error is not None:
            raise error
        return respuesta or RespuestaFalsa()

    monkeypatch.setattr(ia.urllib.request, "urlopen", urlopen)
    return llamadas


# ── URL: la base del centro y la completa valen las dos ──────────────


@pytest.mark.parametrize(
    ("url", "esperada"),
    [
        ("https://ia.centro.es/llmapi/v1", "https://ia.centro.es/llmapi/v1/chat/completions"),
        ("https://ia.centro.es/llmapi/v1/", "https://ia.centro.es/llmapi/v1/chat/completions"),
        ("http://localhost:11434/v1/chat/completions", "http://localhost:11434/v1/chat/completions"),
    ],
)
def test_endpoint_anade_chat_completions_solo_si_falta(url, esperada):
    assert ProveedorIA(url, "", "m").endpoint == esperada


def test_la_peticion_va_al_endpoint_con_la_clave_en_la_cabecera(monkeypatch):
    llamadas = capturar(monkeypatch)
    ProveedorIA("https://ia.centro.es/v1", "clave-personal", "qwen").probar()
    assert llamadas[0]["url"] == "https://ia.centro.es/v1/chat/completions"
    assert llamadas[0]["cabeceras"]["Authorization"] == "Bearer clave-personal"
    assert "context" not in llamadas[0]  # sin CA propia: los certificados del sistema


# ── Certificado de la CA del centro ─────────────────────────────────


def test_ca_que_no_existe_explica_que_falta_y_no_llama_a_la_red(monkeypatch, tmp_path):
    llamadas = capturar(monkeypatch)
    proveedor = ProveedorIA("https://ia.centro.es/v1", "k", "m", ca=str(tmp_path / "no-esta.crt"))
    with pytest.raises(IANoDisponible, match="CENTRO_IA_CA.*no existe"):
        proveedor.probar()
    assert llamadas == []


def test_ca_que_no_es_un_certificado_da_mensaje_claro(monkeypatch, tmp_path):
    capturar(monkeypatch)
    falso = tmp_path / "ca.crt"
    falso.write_text("esto no es un certificado", encoding="utf-8")
    with pytest.raises(IANoDisponible, match="no es un certificado válido"):
        ProveedorIA("https://ia.centro.es/v1", "k", "m", ca=str(falso)).probar()


def test_ca_valida_se_carga_y_se_pasa_a_urlopen(monkeypatch, tmp_path):
    cargados = []

    class ContextoFalso:
        def load_verify_locations(self, cafile):
            cargados.append(cafile)

    contexto = ContextoFalso()
    monkeypatch.setattr(ia.ssl, "create_default_context", lambda: contexto)
    llamadas = capturar(monkeypatch)
    ca = tmp_path / "ca-ies-simarro.crt"
    ca.write_text("-----BEGIN CERTIFICATE-----", encoding="utf-8")

    ProveedorIA("https://ia.centro.es/v1", "k", "m", ca=str(ca)).probar()

    assert cargados == [str(ca)]
    assert llamadas[0]["context"] is contexto


def test_ca_con_virgulilla_se_expande(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    proveedor = ProveedorIA("https://x/v1", "k", "m", ca="~/ca.crt")
    assert proveedor.ruta_ca == tmp_path / "ca.crt"


# ── Errores: cada uno dice qué revisar ──────────────────────────────


def error_http(codigo):
    return urllib.error.HTTPError("https://x/v1/chat/completions", codigo, "x", {}, None)


@pytest.mark.parametrize(
    ("error", "mensaje"),
    [
        (error_http(401), "401: la clave no es válida. Revisa CENTRO_IA_KEY"),
        (error_http(429), "429: demasiadas peticiones"),
        (error_http(404), "404: revisa CENTRO_IA_URL"),
        (error_http(503), "tiene un problema"),
        (urllib.error.URLError(ssl.SSLCertVerificationError("certificate verify failed")), "CENTRO_IA_CA"),
        (urllib.error.URLError(ConnectionRefusedError("rechazada")), "red del centro"),
        (urllib.error.URLError(TimeoutError("timed out")), "red del centro"),  # no llegó a conectar
        (TimeoutError("timed out"), "no ha respondido a tiempo"),  # conectó, pero tardó
    ],
)
def test_cada_fallo_tiene_su_mensaje(monkeypatch, error, mensaje):
    capturar(monkeypatch, error=error)
    with pytest.raises(IANoDisponible, match=mensaje):
        ProveedorIA("https://ia.centro.es/v1", "k", "m").probar()


def test_ia_no_disponible_sigue_siendo_sin_red_para_las_acciones():
    # Las acciones capturan SinRedError para seguir sin IA: la nueva excepción no rompe eso.
    assert issubclass(IANoDisponible, SinRedError)
    assert IANoDisponible.codigo_salida == 4


# ── comprobar-ia ────────────────────────────────────────────────────


def config_minima(tmp_path):
    ruta = tmp_path / "acciones.json"
    ruta.write_text(
        json.dumps({"version": 1, "acciones": [{"nombre": "spam", "descripcion": "Spam", "tipo": "listar"}]}),
        encoding="utf-8",
    )
    return str(ruta)


def test_comprobar_ia_muestra_el_certificado_sin_su_contenido(tmp_path, monkeypatch):
    ca = tmp_path / "ca-ies-simarro.crt"
    ca.write_text("CONTENIDO-DEL-CERTIFICADO", encoding="utf-8")
    monkeypatch.setenv("CENTRO_IA_URL", "https://ia.centro.es/llmapi/v1")
    monkeypatch.setenv("CENTRO_IA_KEY", "sk-SECRETA")
    monkeypatch.setenv("CENTRO_IA_CA", str(ca))
    monkeypatch.setattr(ia.ssl, "create_default_context", lambda: type("C", (), {"load_verify_locations": lambda s, cafile: None})())
    capturar(monkeypatch)

    resultado = runner.invoke(app, ["--config", config_minima(tmp_path), "comprobar-ia"])

    assert resultado.exit_code == 0, resultado.output
    assert "ca-ies-simarro.crt" in resultado.output
    assert "(existe)" in resultado.output
    assert "Qwen38-DualSpark-medium" in resultado.output  # modelo por defecto del centro
    for secreto in ("CONTENIDO-DEL-CERTIFICADO", "sk-SECRETA"):
        assert secreto not in resultado.output


def test_comprobar_ia_sin_red_sale_con_4_y_lo_explica(tmp_path, monkeypatch):
    monkeypatch.setenv("CENTRO_IA_URL", "https://10.255.255.1/v1")
    capturar(monkeypatch, error=urllib.error.URLError(TimeoutError("timed out")))

    resultado = runner.invoke(app, ["--config", config_minima(tmp_path), "comprobar-ia"])
    # Rich parte las líneas largas: se compara sin saltos.
    salida = " ".join((resultado.output + (getattr(resultado, "stderr", "") or "")).split())

    assert resultado.exit_code == 4
    assert "red del centro" in salida
    assert "siguen funcionando" in salida


# ── Lo que encontró la revisión de código ───────────────────────────


@pytest.mark.parametrize(
    ("url", "esperada"),
    [
        ("https://h/v1?api-version=2", "https://h/v1/chat/completions?api-version=2"),
        ("https://h/v1/chat/completions?key=X", "https://h/v1/chat/completions?key=X"),
    ],
)
def test_endpoint_respeta_los_parametros_de_la_url(url, esperada):
    assert ProveedorIA(url, "", "m").endpoint == esperada


@pytest.mark.parametrize(
    ("clave", "mensaje"),
    [
        ("“sk-123”", "comillas"),  # pegada con comillas tipográficas
        ("sk-12\n3", "salto de línea"),
        ("sk-12\r3", "salto de línea"),
    ],
)
def test_clave_mal_copiada_lo_dice_sin_mostrarla_ni_llamar_a_la_red(monkeypatch, clave, mensaje):
    llamadas = capturar(monkeypatch)
    with pytest.raises(IANoDisponible, match=mensaje) as error:
        ProveedorIA("https://h/v1", clave, "m").probar()
    assert "sk-12" not in str(error.value)
    assert "CENTRO_IA_KEY" in str(error.value)
    assert llamadas == []


def test_respuesta_que_no_es_utf8_no_culpa_a_la_url(monkeypatch):
    class Latin1(RespuestaFalsa):
        def read(self):
            return "{\"choices\": \"ñ\"}".encode("latin-1")

    capturar(monkeypatch, respuesta=Latin1())
    with pytest.raises(IANoDisponible, match="no es UTF-8"):
        ProveedorIA("https://h/v1", "k", "m").probar()


@pytest.mark.parametrize(
    ("error", "mensaje"),
    [
        (error_http(403), "403: la clave no es válida"),
        (error_http(400), "error HTTP 400"),
        (ia.http.client.InvalidURL("nonnumeric port"), "no es una URL válida"),
        (ia.http.client.IncompleteRead(b""), "cortó la respuesta"),
    ],
)
def test_mas_fallos_con_su_mensaje(monkeypatch, error, mensaje):
    capturar(monkeypatch, error=error)
    with pytest.raises(IANoDisponible, match=mensaje):
        ProveedorIA("https://h/v1", "k", "m").probar()


def test_certificado_que_no_corresponde_cuando_ya_hay_ca(monkeypatch, tmp_path):
    ca = tmp_path / "ca.crt"
    ca.write_text("x", encoding="utf-8")
    monkeypatch.setattr(ia.ssl, "create_default_context", lambda: type("C", (), {"load_verify_locations": lambda s, cafile: None})())
    capturar(monkeypatch, error=urllib.error.URLError(ssl.SSLCertVerificationError("certificate verify failed")))
    with pytest.raises(IANoDisponible, match="no corresponde a este servidor"):
        ProveedorIA("https://h/v1", "k", "m", ca=str(ca)).probar()


def test_acciones_json_de_la_100_avisa_de_las_variables_viejas(tmp_path):
    ruta = tmp_path / "acciones.json"
    ruta.write_text(
        json.dumps(
            {
                "version": 1,
                "ia": {"url_env": "IA_API_URL", "clave_env": "IA_API_KEY", "modelo_env": "IA_MODELO"},
                "acciones": [{"nombre": "x", "descripcion": "x", "tipo": "listar"}],
            }
        ),
        encoding="utf-8",
    )
    resultado = runner.invoke(app, ["--config", str(ruta), "validar"])
    assert resultado.exit_code == 0
    assert "IA_API_URL" in resultado.output and "CENTRO_IA_URL" in resultado.output
