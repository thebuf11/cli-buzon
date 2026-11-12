"""Cliente IMAP en los casos feos: sin red, credenciales malas, conexión perdida.

No hay red ni cuenta real: se sustituye ``imaplib.IMAP4_SSL`` por un servidor falso.
"""

import imaplib
import json

import pytest
from typer.testing import CliRunner

from buzon import imap_client
from buzon.cli import app
from buzon.errores import AccionNoValida, CredencialesError, SinRedError
from buzon.imap_client import ClienteIMAP

PASSWORD = "abcdefghijklmnop"


class ServidorFalso:
    """Imita lo justo de ``imaplib.IMAP4_SSL``; cada fallo se activa con un argumento."""

    def __init__(self, login_falla=False, select_falla=False, search_falla_con=None, logout_falla=False):
        self.login_falla = login_falla
        self.select_falla = select_falla
        self.search_falla_con = search_falla_con
        self.logout_falla = logout_falla
        self.llamadas = []

    def login(self, usuario, password):
        self.llamadas.append("login")
        if self.login_falla:
            raise imaplib.IMAP4.error(b"[AUTHENTICATIONFAILED] Invalid credentials (Failure)")
        return "OK", [b"Logged in"]

    def select(self, carpeta, readonly=False):
        return ("NO", [b"Unknown Mailbox"]) if self.select_falla else ("OK", [b"3"])

    def uid(self, orden, *argumentos):
        if self.search_falla_con is not None:
            raise self.search_falla_con
        return "OK", [b""]

    def logout(self):
        self.llamadas.append("logout")
        if self.logout_falla:
            raise OSError("socket cerrado")
        return "BYE", [b""]


def conectar_con(monkeypatch, servidor=None, error=None):
    def fabrica(host, puerto, timeout=None):
        if error is not None:
            raise error
        return servidor

    monkeypatch.setattr(imap_client.imaplib, "IMAP4_SSL", fabrica)
    return ClienteIMAP("imap.gmail.com", 993, "alumno@ejemplo.com", PASSWORD, timeout=1).conectar()


@pytest.mark.parametrize(
    "error",
    [
        ConnectionRefusedError("conexión rechazada"),
        TimeoutError("timed out"),  # red del centro que bloquea el 993
        OSError(11001, "getaddrinfo failed"),  # sin DNS / sin red
    ],
)
def test_sin_red_da_un_error_humano(monkeypatch, error):
    with pytest.raises(SinRedError, match=r"No se pudo conectar con imap\.gmail\.com:993"):
        conectar_con(monkeypatch, error=error)


def test_credenciales_malas_explican_que_revisar_sin_mostrar_la_contrasena(monkeypatch):
    with pytest.raises(CredencialesError) as info:
        conectar_con(monkeypatch, ServidorFalso(login_falla=True))
    mensaje = str(info.value)
    assert "GMAIL_APP_PASSWORD" in mensaje
    assert "IMAP" in mensaje
    assert PASSWORD not in mensaje


def test_carpeta_inexistente(monkeypatch):
    cliente = conectar_con(monkeypatch, ServidorFalso(select_falla=True))
    with pytest.raises(AccionNoValida, match="No se pudo abrir la carpeta «\\[Gmail\\]/Spamm»"):
        cliente.listar("[Gmail]/Spamm")


@pytest.mark.parametrize(
    "error",
    [imaplib.IMAP4.abort("socket error: EOF"), ConnectionResetError("reset"), TimeoutError("timed out")],
)
def test_conexion_perdida_a_mitad(monkeypatch, error):
    cliente = conectar_con(monkeypatch, ServidorFalso(search_falla_con=error))
    with pytest.raises(SinRedError, match="Se perdió la conexión"):
        cliente.listar("INBOX")


def test_cerrar_no_falla_aunque_la_conexion_ya_este_rota(monkeypatch):
    servidor = ServidorFalso(logout_falla=True)
    cliente = conectar_con(monkeypatch, servidor)
    cliente.cerrar()  # no lanza nada
    cliente.cerrar()  # ni la segunda vez
    assert servidor.llamadas == ["login", "logout"]


def test_usar_el_cliente_sin_conectar_es_un_error_controlado():
    cliente = ClienteIMAP("imap.gmail.com", 993, "a@b.c", PASSWORD)
    with pytest.raises(SinRedError, match="no está abierta"):
        cliente.listar("INBOX")


# ── la CLI de punta a punta: mensaje y código 1, nunca traceback ──

runner = CliRunner()


@pytest.fixture
def config_imap(tmp_path):
    ruta = tmp_path / "acciones.json"
    ruta.write_text(
        json.dumps(
            {
                "version": 1,
                "cuenta": {"proveedor": "imap"},
                "acciones": [{"nombre": "listar-spam", "descripcion": "S", "tipo": "listar", "carpeta": "spam"}],
            }
        ),
        encoding="utf-8",
    )
    return str(ruta)


def salida(resultado):
    return " ".join((resultado.output + (getattr(resultado, "stderr", "") or "")).split())


def test_cli_sin_credenciales(config_imap):
    resultado = runner.invoke(app, ["--config", config_imap, "ejecutar", "listar-spam"])
    assert resultado.exit_code == 1
    assert "Faltan credenciales" in salida(resultado)
    assert "Traceback" not in salida(resultado)


def test_cli_credenciales_malas(config_imap, monkeypatch):
    monkeypatch.setenv("GMAIL_USUARIO", "alumno@ejemplo.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", PASSWORD)
    monkeypatch.setattr(imap_client.imaplib, "IMAP4_SSL", lambda *a, **k: ServidorFalso(login_falla=True))
    resultado = runner.invoke(app, ["--config", config_imap, "ejecutar", "listar-spam"])
    assert resultado.exit_code == 1
    assert "Gmail rechazó las credenciales" in salida(resultado)
    assert PASSWORD not in salida(resultado)


def test_cli_sin_red(config_imap, monkeypatch):
    monkeypatch.setenv("GMAIL_USUARIO", "alumno@ejemplo.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", PASSWORD)

    def sin_red(*argumentos, **opciones):
        raise TimeoutError("timed out")

    monkeypatch.setattr(imap_client.imaplib, "IMAP4_SSL", sin_red)
    resultado = runner.invoke(app, ["--config", config_imap, "listar", "spam"])
    assert resultado.exit_code == 1
    assert "No se pudo conectar con imap.gmail.com:993" in salida(resultado)
    assert "Traceback" not in salida(resultado)
