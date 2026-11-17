"""Pruebas del cliente de la API de Gmail sin red: urlopen se sustituye por un falso."""

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pytest

from buzon.config import Cuenta
from buzon.errores import AccionNoValida, CredencialesError
from buzon.gmail_api import ClienteGmailAPI

FIXTURES = Path(__file__).parent / "fixtures"
AHORA = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)

CUENTA = Cuenta(
    servidor="imap.gmail.com",
    puerto=993,
    usuario_env="GMAIL_USUARIO",
    password_env="GMAIL_APP_PASSWORD",
    carpeta_entrada="INBOX",
    carpeta_spam="[Gmail]/Spam",
    carpeta_papelera="[Gmail]/Trash",
    proveedor="gmail-api",
)


class Respuesta:
    def __init__(self, cuerpo):
        self.cuerpo = cuerpo if isinstance(cuerpo, bytes) else json.dumps(cuerpo).encode()

    def read(self):
        return self.cuerpo

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def error_http(url, codigo):
    return urllib.error.HTTPError(url, codigo, "error", {}, None)


class GmailFalso:
    """Imita las rutas de la API que usa el cliente y registra las peticiones."""

    def __init__(self):
        self.peticiones = []
        self.mensajes = {}
        self.paginas = [["m1", "m2"], ["m3"]]
        self.fallan_trash = set()
        self.codigo_global = None
        self.token_ok = True

    def __call__(self, peticion, timeout=None):
        url = urllib.parse.urlparse(peticion.full_url)
        consulta = urllib.parse.parse_qs(url.query)
        self.peticiones.append((peticion.get_method(), url.path, consulta, peticion.headers))

        if url.netloc == "oauth2.googleapis.com":
            if not self.token_ok:
                raise error_http(peticion.full_url, 400)
            return Respuesta({"access_token": "nuevo", "expires_in": 3600})
        if self.codigo_global:
            raise error_http(peticion.full_url, self.codigo_global)

        ruta = url.path.removeprefix("/gmail/v1/users/me")
        if ruta == "/messages":
            indice = int(consulta.get("pageToken", ["0"])[0])
            datos = {"messages": [{"id": i} for i in self.paginas[indice]]}
            if indice + 1 < len(self.paginas):
                datos["nextPageToken"] = str(indice + 1)
            return Respuesta(datos)
        if ruta == "/labels":
            return Respuesta({"labels": [{"id": "Label_7", "name": "Clase"}]})
        if ruta.endswith("/trash"):
            identificador = ruta.split("/")[2]
            if identificador in self.fallan_trash:
                raise error_http(peticion.full_url, 404)
            return Respuesta(b"{}")
        identificador = ruta.split("/")[2]
        return Respuesta(self.mensajes[identificador])


def metadatos(asunto, fecha, importante=False):
    return {
        "labelIds": ["INBOX"] + (["IMPORTANT"] if importante else []),
        "payload": {
            "headers": [
                {"name": "From", "value": "Ana Torres <ana@example.com>"},
                {"name": "Subject", "value": asunto},
                {"name": "Date", "value": fecha},
            ]
        },
    }


@pytest.fixture
def gmail(monkeypatch):
    falso = GmailFalso()
    monkeypatch.setattr(urllib.request, "urlopen", falso)
    return falso


def crear_cliente(tmp_path, token=None):
    (tmp_path / "credentials.json").write_text(
        json.dumps({"installed": {"client_id": "id", "client_secret": "secreto"}}), encoding="utf-8"
    )
    token = token or {"access_token": "valido", "refresh_token": "r", "expira": time.time() + 3600}
    (tmp_path / "token.json").write_text(json.dumps(token), encoding="utf-8")
    abiertos = []
    cliente = ClienteGmailAPI(CUENTA, tmp_path, abrir_navegador=abiertos.append, avisar=lambda m: None)
    return cliente.conectar(), abiertos


def test_listar_pagina_filtra_por_horas_y_marca_importantes(tmp_path, gmail):
    gmail.mensajes = {
        "m1": metadatos("=?utf-8?q?Reuni=C3=B3n?=", "Tue, 10 Nov 2026 11:00:00 +0000", importante=True),
        "m2": metadatos("Ofertas", "Tue, 10 Nov 2026 09:00:00 +0000"),
        "m3": metadatos("Antiguo", "Sat, 07 Nov 2026 09:00:00 +0000"),
    }
    cliente, abiertos = crear_cliente(tmp_path)
    correos = cliente.listar("INBOX", horas=24, ahora=AHORA)

    assert [c.uid for c in correos] == ["m1", "m2"]  # m3 queda fuera de la ventana
    assert correos[0].asunto == "Reunión"
    assert correos[0].importante and not correos[1].importante
    assert abiertos == []  # con token guardado no abre el navegador

    _, _, consulta, cabeceras = gmail.peticiones[0]
    assert consulta["labelIds"] == ["INBOX"]
    assert consulta["q"] == [f"after:{int(AHORA.timestamp()) - 24 * 3600}"]
    assert cabeceras["Authorization"] == "Bearer valido"


def test_listar_spam_incluye_spam_y_papelera(tmp_path, gmail):
    gmail.paginas = [[]]
    cliente, _ = crear_cliente(tmp_path)
    assert cliente.listar("[Gmail]/Spam", horas=None) == []
    _, _, consulta, _ = gmail.peticiones[0]
    assert consulta["labelIds"] == ["SPAM"]
    assert consulta["includeSpamTrash"] == ["true"]
    assert "q" not in consulta


def test_etiqueta_de_usuario_y_desconocida(tmp_path, gmail):
    gmail.paginas = [[]]
    cliente, _ = crear_cliente(tmp_path)
    cliente.listar("clase", horas=None)
    assert gmail.peticiones[-1][2]["labelIds"] == ["Label_7"]
    with pytest.raises(AccionNoValida):
        cliente.listar("no-existe", horas=None)


def test_leer_texto_decodifica_raw(tmp_path, gmail):
    crudo = (FIXTURES / "correo.eml").read_bytes()
    gmail.mensajes = {"m1": {"raw": base64.urlsafe_b64encode(crudo).decode().rstrip("=")}}
    cliente, _ = crear_cliente(tmp_path)
    assert "reunión de tutores es el martes" in cliente.leer_texto("INBOX", "m1")
    assert gmail.peticiones[-1][2]["format"] == ["raw"]


def test_papelera_con_fallo_parcial(tmp_path, gmail):
    gmail.fallan_trash = {"m2"}
    cliente, _ = crear_cliente(tmp_path)
    assert cliente.mover_uids_a_papelera("INBOX", ["m1", "m2", "m3"], "[Gmail]/Trash") == ["m1", "m3"]
    assert all(metodo == "POST" for metodo, *_ in gmail.peticiones)


def test_401_borra_token_y_da_error_humano(tmp_path, gmail):
    gmail.codigo_global = 401
    cliente, _ = crear_cliente(tmp_path)
    with pytest.raises(CredencialesError, match="iniciar sesión"):
        cliente.listar("INBOX")
    assert not (tmp_path / "token.json").exists()


def test_403_sugiere_activar_la_api(tmp_path, gmail):
    gmail.codigo_global = 403
    cliente, _ = crear_cliente(tmp_path)
    with pytest.raises(CredencialesError, match="API de Gmail"):
        cliente.listar("INBOX")


def test_token_caducado_se_refresca_y_se_guarda(tmp_path, gmail):
    gmail.paginas = [[]]
    cliente, _ = crear_cliente(tmp_path, {"access_token": "viejo", "refresh_token": "r", "expira": 0})
    cliente.listar("INBOX", horas=None)
    assert gmail.peticiones[0][1] == "/token"
    assert gmail.peticiones[1][3]["Authorization"] == "Bearer nuevo"
    guardado = json.loads((tmp_path / "token.json").read_text(encoding="utf-8"))
    assert guardado["access_token"] == "nuevo" and guardado["refresh_token"] == "r"


def test_refresco_rechazado_pide_volver_a_entrar(tmp_path, gmail):
    gmail.token_ok = False
    cliente, _ = crear_cliente(tmp_path, {"access_token": "viejo", "refresh_token": "r", "expira": 0})
    with pytest.raises(CredencialesError, match="caducado") as error:
        cliente.listar("INBOX")
    mensaje = str(error.value)
    assert "7 días" in mensaje and "token.json" in mensaje and "vuelve a ejecutar" in mensaje
    assert not (tmp_path / "token.json").exists()


def test_sin_credentials_json_explica_que_hacer(tmp_path):
    cliente = ClienteGmailAPI(CUENTA, tmp_path)
    with pytest.raises(CredencialesError, match="README"):
        cliente.conectar()


def test_credentials_json_invalido(tmp_path):
    (tmp_path / "credentials.json").write_text("{}", encoding="utf-8")
    with pytest.raises(CredencialesError, match="no es un fichero de cliente OAuth"):
        ClienteGmailAPI(CUENTA, tmp_path).conectar()


def navegador_que_acepta(codigo="abc", cambiar_estado=False, error=None):
    """Simula al usuario dando permiso: llama a la redirección local desde otro hilo."""
    import http.client
    import threading

    def abrir(url):
        consulta = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
        destino = urllib.parse.urlparse(consulta["redirect_uri"])
        parametros = {"state": "otro" if cambiar_estado else consulta["state"]}
        parametros.update({"error": error} if error else {"code": codigo})
        abrir.consulta = consulta

        def visitar():
            conexion = http.client.HTTPConnection(destino.hostname, destino.port, timeout=5)
            conexion.request("GET", "/?" + urllib.parse.urlencode(parametros))
            conexion.getresponse().read()
            conexion.close()

        threading.Thread(target=visitar, daemon=True).start()

    return abrir


def test_primer_inicio_de_sesion_guarda_token(tmp_path, monkeypatch):
    peticiones = []

    def token_falso(peticion, timeout=None):
        peticiones.append(dict(urllib.parse.parse_qsl(peticion.data.decode())))
        return Respuesta({"access_token": "a", "refresh_token": "r", "expires_in": 3600})

    monkeypatch.setattr(urllib.request, "urlopen", token_falso)
    (tmp_path / "credentials.json").write_text(
        json.dumps({"installed": {"client_id": "id", "client_secret": "s"}}), encoding="utf-8"
    )
    navegador = navegador_que_acepta()
    ClienteGmailAPI(CUENTA, tmp_path, abrir_navegador=navegador, avisar=lambda m: None).conectar()

    assert navegador.consulta["code_challenge_method"] == "S256"
    assert navegador.consulta["redirect_uri"].startswith("http://127.0.0.1:")
    assert peticiones[0]["code"] == "abc"
    assert peticiones[0]["grant_type"] == "authorization_code"
    assert "code_verifier" in peticiones[0]
    assert json.loads((tmp_path / "token.json").read_text(encoding="utf-8"))["refresh_token"] == "r"


@pytest.mark.parametrize(("opciones", "mensaje"), [({"error": "access_denied"}, "no dio permiso"),
                                                    ({"cambiar_estado": True}, "intento de inicio de sesión anterior")])
def test_inicio_de_sesion_rechazado(tmp_path, monkeypatch, opciones, mensaje):
    # Una respuesta con otro «state» no corta la espera: se descarta y se sigue esperando
    # hasta el límite, que aquí se acorta para que la prueba sea rápida.
    monkeypatch.setattr("buzon.gmail_api.ESPERA_LOGIN", 2)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("no debe pedir token"))
    (tmp_path / "credentials.json").write_text(
        json.dumps({"installed": {"client_id": "id"}}), encoding="utf-8"
    )
    cliente = ClienteGmailAPI(CUENTA, tmp_path, abrir_navegador=navegador_que_acepta(**opciones),
                              avisar=lambda m: None)
    with pytest.raises(CredencialesError, match=mensaje):
        cliente.conectar()
    assert not (tmp_path / "token.json").exists()


def test_peticiones_sueltas_no_cortan_el_inicio_de_sesion(tmp_path, monkeypatch):
    """Un /favicon.ico antes de la redirección real no debe estropear el login."""
    import http.client
    import threading

    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda *a, **k: Respuesta({"access_token": "a", "refresh_token": "r", "expires_in": 3600}),
    )
    (tmp_path / "credentials.json").write_text(
        json.dumps({"installed": {"client_id": "id"}}), encoding="utf-8"
    )

    def abrir(url):
        consulta = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
        destino = urllib.parse.urlparse(consulta["redirect_uri"])

        def visitar():
            for ruta in ("/favicon.ico", "/?" + urllib.parse.urlencode({"code": "c", "state": consulta["state"]})):
                conexion = http.client.HTTPConnection(destino.hostname, destino.port, timeout=5)
                conexion.request("GET", ruta)
                conexion.getresponse().read()
                conexion.close()

        threading.Thread(target=visitar, daemon=True).start()

    ClienteGmailAPI(CUENTA, tmp_path, abrir_navegador=abrir, avisar=lambda m: None).conectar()
    assert (tmp_path / "token.json").exists()


def test_fallo_temporal_al_refrescar_conserva_la_sesion(tmp_path, monkeypatch):
    from buzon.errores import SinRedError

    def caido(peticion, timeout=None):
        raise error_http(peticion.full_url, 503)

    cliente, _ = crear_cliente(tmp_path, {"access_token": "viejo", "refresh_token": "r", "expira": 0})
    monkeypatch.setattr(urllib.request, "urlopen", caido)
    with pytest.raises(SinRedError):
        cliente.listar("INBOX")
    assert (tmp_path / "token.json").exists()


def test_respuesta_de_token_sin_access_token(tmp_path, monkeypatch):
    from buzon.errores import SinRedError

    cliente, _ = crear_cliente(tmp_path, {"access_token": "viejo", "refresh_token": "r", "expira": 0})
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: Respuesta({"expires_in": "x"}))
    with pytest.raises(SinRedError, match="access_token"):
        cliente.listar("INBOX")


def test_cabeceras_utf8_y_saltos_de_linea(tmp_path, gmail):
    gmail.paginas = [["m1"]]
    datos = metadatos("Café\r\n\r\nBcc: x", "Tue, 10 Nov 2026 11:00:00 +0000")
    datos["payload"]["headers"][0]["value"] = "José <jose@example.com>"
    gmail.mensajes = {"m1": datos}
    cliente, _ = crear_cliente(tmp_path)
    correo = cliente.listar("INBOX", horas=None)[0]
    assert correo.remitente == "José <jose@example.com>"
    assert correo.asunto == "Café Bcc: x"
    assert correo.fecha is not None  # la fecha no se pierde por el salto de línea


def test_mensaje_borrado_durante_el_listado_se_omite(tmp_path, gmail):
    gmail.paginas = [["m1", "m2"]]
    gmail.mensajes = {"m2": metadatos("Sigue aquí", "Tue, 10 Nov 2026 11:00:00 +0000")}

    original = gmail.__call__

    def con_404(peticion, timeout=None):
        if peticion.full_url.split("?")[0].endswith("/messages/m1"):
            raise error_http(peticion.full_url, 404)
        return original(peticion, timeout)

    import urllib.request as ur
    ur.urlopen = con_404  # el fixture lo restaura al terminar
    cliente, _ = crear_cliente(tmp_path)
    assert [c.uid for c in cliente.listar("INBOX", horas=None)] == ["m2"]


def test_cliente_oauth_rechazado_al_iniciar_sesion_explica_credentials(tmp_path, monkeypatch):
    # El navegador da el código, pero Google rechaza el cliente al canjearlo (400 invalid_client).
    def rechazar(*args, **kwargs):
        raise urllib.error.HTTPError("https://oauth2.googleapis.com/token", 400, "invalid_client", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", rechazar)
    (tmp_path / "credentials.json").write_text(
        json.dumps({"installed": {"client_id": "id", "client_secret": "s"}}), encoding="utf-8"
    )
    cliente = ClienteGmailAPI(CUENTA, tmp_path, abrir_navegador=navegador_que_acepta(),
                              avisar=lambda m: None)
    with pytest.raises(CredencialesError, match="cliente OAuth de credentials.json") as error:
        cliente.conectar()
    assert "Descárgalo de nuevo" in str(error.value)
    assert not (tmp_path / "token.json").exists()
