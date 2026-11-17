"""Cliente de la API REST de Gmail (HTTPS, puerto 443), solo con la librería estándar.

Es la alternativa a IMAP para redes que bloquean el puerto 993. Tiene la misma
interfaz que :class:`buzon.imap_client.ClienteIMAP`, así que el motor y las
acciones no saben cuál de los dos están usando.

Autenticación: OAuth 2.0 para aplicaciones de escritorio con PKCE. La primera
vez se abre el navegador; después se reutiliza ``token.json`` y se refresca solo.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import http.client
import json
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from email.header import Header
from email.utils import formataddr, parseaddr
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from .config import Cuenta
from .errores import AccionNoValida, BuzonError, CredencialesError, SinRedError
from .imap_client import Correo, _parsear_correo, extraer_texto, filtrar_por_horas

API = "https://gmail.googleapis.com/gmail/v1/users/me"
URL_AUTORIZAR = "https://accounts.google.com/o/oauth2/v2/auth"
URL_TOKEN = "https://oauth2.googleapis.com/token"
ALCANCE = "https://www.googleapis.com/auth/gmail.modify"
ETIQUETAS_SISTEMA = {"INBOX", "SPAM", "TRASH", "IMPORTANT", "STARRED", "SENT", "DRAFT", "UNREAD"}
ESPERA_LOGIN = 300  # segundos para completar el inicio de sesión en el navegador


def _b64url(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).decode("ascii").rstrip("=")


def _avisar(mensaje: str) -> None:
    print(mensaje, file=sys.stderr)


def _es_limite_de_uso(exc: urllib.error.HTTPError) -> bool:
    """Un 403 de Gmail puede ser falta de permisos o simplemente límite de uso."""
    try:
        cuerpo = exc.read().decode("utf-8", "replace")
    except (OSError, AttributeError, ValueError, http.client.HTTPException):
        return False
    return "ratelimitexceeded" in cuerpo.lower()


def _cabecera(nombre: str, valor: str) -> str:
    """Rearma una línea de cabecera segura: sin saltos de línea y con no-ASCII codificado (RFC 2047)."""
    valor = " ".join(valor.split())
    if not valor.isascii():
        if nombre == "From":
            # Solo se codifica el nombre visible; la dirección se deja tal cual.
            visible, direccion = parseaddr(valor)
            valor = formataddr((visible, direccion), charset="utf-8") if direccion else valor
        if not valor.isascii():
            valor = Header(valor, "utf-8").encode()
    return f"{nombre}: {valor}\r\n"


SESION_CADUCADA = (
    "Tu sesión con Google ha caducado o se ha revocado. Es normal: si la app de Google Cloud "
    "está en modo «Prueba», Google la caduca a los 7 días. He borrado {token}: vuelve a "
    "ejecutar la orden y se abrirá el navegador para dar permiso otra vez."
)
CLIENTE_RECHAZADO = (
    "Google rechazó el cliente OAuth de {credenciales} (¿lo borraste o le cambiaste el secreto "
    "en Google Cloud?). Descárgalo de nuevo: Google Cloud → Google Auth Platform → Clientes → "
    "Descargar, y guárdalo como {credenciales}."
)


class _TokenRechazado(CredencialesError):
    """Google respondió 400/401 al pedir un token; quien llama sabe explicar por qué."""


class _ReceptorCodigo(BaseHTTPRequestHandler):
    """Recibe la redirección de Google en http://127.0.0.1:<puerto>/?code=..."""

    def do_GET(self) -> None:  # noqa: N802 (nombre impuesto por http.server)
        consulta = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))
        if "code" not in consulta and "error" not in consulta:
            # /favicon.ico, precargas…: no son la redirección de Google; se sigue esperando.
            self.send_response(404)
            self.end_headers()
            return

        servidor = self.server
        if "error" not in consulta and not secrets.compare_digest(
            consulta.get("state", ""), servidor.estado  # type: ignore[attr-defined]
        ):
            # Respuesta de otro intento (pestaña antigua, URL copiada de otra ejecución…):
            # no se acepta, pero se sigue esperando la buena.
            servidor.descartadas += 1  # type: ignore[attr-defined]
            self._pagina(
                400,
                "buzon: esta respuesta es de un intento anterior.",
                "Cierra esta pestaña y usa la que abrió la última ejecución de buzon.",
            )
            return

        servidor.resultado = consulta  # type: ignore[attr-defined]
        if "error" in consulta:
            self._pagina(200, "buzon: no se dio permiso.", "No se ha tocado nada. Puedes cerrar esta pestaña.")
        else:
            self._pagina(200, "buzon: listo.", "Ya puedes cerrar esta pestaña y volver a la terminal.")

    def _pagina(self, codigo: int, titulo: str, texto: str) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(f"<h2>{titulo}</h2><p>{texto}</p>".encode())

    def log_message(self, *args: object) -> None:  # silencia el log por consola
        pass


class ClienteGmailAPI:
    """Habla con la API de Gmail. Se usa como context manager, igual que ClienteIMAP."""

    def __init__(
        self,
        cuenta: Cuenta,
        base: Path,
        timeout: float = 30.0,
        abrir_navegador: Callable[[str], object] = webbrowser.open,
        avisar: Callable[[str], None] = _avisar,
    ) -> None:
        self.cuenta = cuenta
        self.ruta_credenciales = (Path(base) / cuenta.credenciales_api).expanduser()
        self.ruta_token = (Path(base) / cuenta.token_api).expanduser()
        self.timeout = timeout
        self._abrir_navegador = abrir_navegador
        self._avisar = avisar
        self._cliente_oauth: dict | None = None
        self._token: dict | None = None
        self._etiquetas_usuario: dict[str, str] | None = None

    # ------------------------------------------------------------------ conexión

    def __enter__(self) -> ClienteGmailAPI:
        return self.conectar()

    def __exit__(self, *exc: object) -> bool:
        self.cerrar()
        return False

    def conectar(self) -> ClienteGmailAPI:
        self._cliente_oauth = self._leer_credenciales()
        self._token = self._leer_token()
        if self._token is None:
            self._token = self._iniciar_sesion()
            self._guardar_token()
        return self

    def cerrar(self) -> None:
        """La API es HTTP sin estado: no hay conexión que cerrar."""

    def _leer_credenciales(self) -> dict:
        if not self.ruta_credenciales.exists():
            raise CredencialesError(
                f"No encuentro «{self.ruta_credenciales.name}». Para usar la API de Gmail crea un "
                "cliente OAuth de tipo «App de escritorio» en Google Cloud y descárgalo ahí "
                "(pasos en el README, sección «Usar la API de Gmail»)."
            )
        try:
            datos = json.loads(self.ruta_credenciales.read_text(encoding="utf-8"))
            cliente = datos.get("installed") or datos.get("web") or {}
            return {"client_id": cliente["client_id"], "client_secret": cliente.get("client_secret", "")}
        except (OSError, json.JSONDecodeError, KeyError, AttributeError) as exc:
            raise CredencialesError(
                f"«{self.ruta_credenciales.name}» no es un fichero de cliente OAuth válido. "
                "Descárgalo de nuevo desde Google Cloud (Credenciales → ID de cliente OAuth)."
            ) from exc

    def _leer_token(self) -> dict | None:
        if not self.ruta_token.exists():
            return None
        try:
            token = json.loads(self.ruta_token.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(token, dict) or "refresh_token" not in token:
            return None
        return token

    def _guardar_token(self) -> None:
        try:
            self.ruta_token.write_text(json.dumps(self._token, indent=2), encoding="utf-8")
        except OSError as exc:
            raise BuzonError(f"No se pudo guardar «{self.ruta_token}»: {exc.strerror or exc}") from exc

    def _borrar_token(self) -> None:
        self._token = None
        try:
            self.ruta_token.unlink(missing_ok=True)
        except OSError:
            pass

    def _iniciar_sesion(self) -> dict:
        """Flujo OAuth de escritorio: navegador + servidor local en un puerto libre."""
        assert self._cliente_oauth is not None
        verificador = secrets.token_urlsafe(64)
        desafio = _b64url(hashlib.sha256(verificador.encode("ascii")).digest())
        estado = secrets.token_urlsafe(16)

        # Puerto 0 = el sistema elige uno libre: no choca con otras aplicaciones.
        try:
            servidor = HTTPServer(("127.0.0.1", 0), _ReceptorCodigo)
        except OSError as exc:
            raise CredencialesError(
                f"No se pudo abrir el servidor local para iniciar sesión: {exc.strerror or exc}"
            ) from exc
        servidor.resultado = None  # type: ignore[attr-defined]
        servidor.estado = estado  # type: ignore[attr-defined]
        servidor.descartadas = 0  # type: ignore[attr-defined]
        servidor.timeout = 1
        redireccion = f"http://127.0.0.1:{servidor.server_address[1]}"
        url = URL_AUTORIZAR + "?" + urllib.parse.urlencode(
            {
                "client_id": self._cliente_oauth["client_id"],
                "redirect_uri": redireccion,
                "response_type": "code",
                "scope": ALCANCE,
                "code_challenge": desafio,
                "code_challenge_method": "S256",
                "state": estado,
                "access_type": "offline",
                "prompt": "consent",
            }
        )
        self._avisar("Abriendo el navegador para que des permiso a buzon sobre tu Gmail…")
        self._avisar(f"Si no se abre, copia esta dirección en el navegador:\n{url}")
        try:
            self._abrir_navegador(url)
        except webbrowser.Error:
            pass  # el usuario tiene la URL impresa arriba

        limite = time.monotonic() + ESPERA_LOGIN
        try:
            while servidor.resultado is None and time.monotonic() < limite:  # type: ignore[attr-defined]
                servidor.handle_request()
        finally:
            servidor.server_close()

        resultado = servidor.resultado  # type: ignore[attr-defined]
        if resultado is None:
            if servidor.descartadas:  # type: ignore[attr-defined]
                raise CredencialesError(
                    "Llegaron respuestas de un intento de inicio de sesión anterior, pero no la de este. "
                    "Cierra las pestañas de Google antiguas y vuelve a ejecutar la orden."
                )
            raise CredencialesError("No se completó el inicio de sesión en el navegador a tiempo (5 min).")
        if "error" in resultado:
            raise CredencialesError(f"Google no dio permiso ({resultado['error']}). No se ha tocado nada.")

        try:
            token = self._pedir_token(
                {
                    "grant_type": "authorization_code",
                    "code": resultado["code"],
                    "redirect_uri": redireccion,
                    "code_verifier": verificador,
                }
            )
        except _TokenRechazado as exc:
            raise CredencialesError(
                CLIENTE_RECHAZADO.format(credenciales=self.ruta_credenciales.name)
            ) from exc
        if "refresh_token" not in token:
            raise CredencialesError("Google no devolvió un refresh_token. Vuelve a intentarlo.")
        self._avisar("Sesión iniciada. El permiso queda guardado en " + self.ruta_token.name + ".")
        return token

    def _pedir_token(self, campos: dict) -> dict:
        assert self._cliente_oauth is not None
        cuerpo = urllib.parse.urlencode({**campos, **self._cliente_oauth}).encode("ascii")
        peticion = urllib.request.Request(
            URL_TOKEN,
            data=cuerpo,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(peticion, timeout=self.timeout) as respuesta:
                datos = json.loads(respuesta.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in {400, 401}:  # invalid_grant, cliente borrado, sesión revocada…
                raise _TokenRechazado(
                    "Google rechazó la sesión guardada o el cliente OAuth. Vuelve a ejecutar la orden "
                    "para iniciar sesión de nuevo."
                ) from exc
            raise SinRedError(f"Google respondió con error HTTP {exc.code}. Inténtalo más tarde.") from exc
        except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
            raise SinRedError("No se pudo contactar con Google (oauth2.googleapis.com).") from exc
        except ValueError as exc:  # JSON o UTF-8 inválidos
            raise SinRedError("Google devolvió una respuesta ilegible.") from exc

        if not isinstance(datos, dict) or not datos.get("access_token"):
            raise SinRedError("Google devolvió una respuesta sin access_token. Inténtalo de nuevo.")
        try:
            duracion = int(datos.get("expires_in", 3600))
        except (TypeError, ValueError):
            duracion = 3600
        datos["expira"] = time.time() + duracion
        return datos

    def _access_token(self) -> str:
        if self._token is None:
            raise CredencialesError("No hay sesión con Google: la conexión no está abierta.")
        if self._token.get("expira", 0) - 60 < time.time():
            try:
                nuevo = self._pedir_token(
                    {"grant_type": "refresh_token", "refresh_token": self._token["refresh_token"]}
                )
            except _TokenRechazado as exc:
                self._borrar_token()
                raise CredencialesError(SESION_CADUCADA.format(token=self.ruta_token.name)) from exc
            except CredencialesError:
                self._borrar_token()
                raise
            nuevo.setdefault("refresh_token", self._token["refresh_token"])
            self._token = nuevo
            self._guardar_token()
        return self._token["access_token"]

    # ------------------------------------------------------------------- HTTP

    def _peticion(self, metodo: str, ruta: str, parametros: dict | None = None) -> dict:
        url = API + ruta
        if parametros:
            url += "?" + urllib.parse.urlencode(parametros, doseq=True)
        peticion = urllib.request.Request(
            url,
            data=b"" if metodo == "POST" else None,
            headers={"Authorization": f"Bearer {self._access_token()}"},
            method=metodo,
        )
        try:
            with urllib.request.urlopen(peticion, timeout=self.timeout) as respuesta:
                texto = respuesta.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                self._borrar_token()
                raise CredencialesError(
                    "Google ha invalidado la sesión. Vuelve a ejecutar la orden para iniciar sesión."
                ) from exc
            if exc.code == 403 and _es_limite_de_uso(exc):
                raise SinRedError("Gmail limita las peticiones ahora mismo (HTTP 403). Espera un poco.") from exc
            if exc.code == 403:
                raise CredencialesError(
                    "Google denegó el acceso (HTTP 403). ¿Has activado la API de Gmail en tu proyecto "
                    "de Google Cloud y añadido tu cuenta como usuario de prueba?"
                ) from exc
            if exc.code == 404:
                raise AccionNoValida("Gmail no encuentra ese mensaje o carpeta (HTTP 404).") from exc
            raise SinRedError(f"Gmail respondió con error HTTP {exc.code}. Inténtalo más tarde.") from exc
        except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
            raise SinRedError("No se pudo conectar con gmail.googleapis.com. Comprueba tu conexión.") from exc
        except ValueError as exc:  # UTF-8 inválido
            raise SinRedError("Gmail devolvió una respuesta ilegible.") from exc

        if not texto.strip():
            return {}
        try:
            datos = json.loads(texto)
        except json.JSONDecodeError as exc:
            raise SinRedError("Gmail devolvió una respuesta que no es JSON.") from exc
        if not isinstance(datos, dict):
            raise SinRedError("Gmail devolvió una respuesta inesperada.")
        return datos

    # --------------------------------------------------------------- carpetas

    def _etiqueta(self, carpeta: str) -> str:
        """Traduce el nombre de carpeta de acciones.json a un id de etiqueta de Gmail."""
        mapa = {
            self.cuenta.carpeta_entrada: "INBOX",
            self.cuenta.carpeta_spam: "SPAM",
            self.cuenta.carpeta_papelera: "TRASH",
        }
        if carpeta in mapa:
            return mapa[carpeta]
        if carpeta.upper() in ETIQUETAS_SISTEMA:
            return carpeta.upper()

        if self._etiquetas_usuario is None:
            datos = self._peticion("GET", "/labels")
            self._etiquetas_usuario = {
                etiqueta["name"].lower(): etiqueta["id"]
                for etiqueta in datos.get("labels", [])
                if "name" in etiqueta and "id" in etiqueta
            }
        identificador = self._etiquetas_usuario.get(carpeta.lower())
        if identificador is None:
            raise AccionNoValida(
                f"No existe la carpeta o etiqueta «{carpeta}» en Gmail. Usa entrada, spam, papelera "
                "o el nombre exacto de una etiqueta."
            )
        return identificador

    # ---------------------------------------------------------------- correos

    def listar(
        self,
        carpeta: str,
        horas: int | None = 24,
        ahora: datetime | None = None,
    ) -> list[Correo]:
        """Lista los correos de una carpeta. ``horas=None`` significa todos."""
        etiqueta = self._etiqueta(carpeta)
        parametros: dict = {"labelIds": etiqueta, "maxResults": 500}
        if etiqueta in {"SPAM", "TRASH"}:
            parametros["includeSpamTrash"] = "true"
        momento = ahora or datetime.now(timezone.utc)
        if horas is not None:
            parametros["q"] = f"after:{int((momento - timedelta(hours=horas)).timestamp())}"

        ids: list[str] = []
        while True:
            datos = self._peticion("GET", "/messages", parametros)
            ids += [mensaje["id"] for mensaje in datos.get("messages", []) if "id" in mensaje]
            siguiente = datos.get("nextPageToken")
            if not siguiente:
                break
            parametros["pageToken"] = siguiente

        correos: list[Correo] = []
        for identificador in ids:
            try:
                correos.append(self._leer_metadatos(identificador))
            except AccionNoValida:
                continue  # borrado entre el listado y la lectura: se omite
        if horas is None:
            return correos
        return filtrar_por_horas(correos, horas, momento)

    def _leer_metadatos(self, identificador: str) -> Correo:
        datos = self._peticion(
            "GET",
            f"/messages/{urllib.parse.quote(identificador)}",
            {"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
        )
        cabeceras = {
            cabecera.get("name", "").lower(): cabecera.get("value", "")
            for cabecera in datos.get("payload", {}).get("headers", [])
        }
        # Se rearma una cabecera RFC 822 para reutilizar el mismo parser que IMAP
        # (decodifica =?utf-8?...?= y quita caracteres de control).
        crudo = "".join(
            _cabecera(nombre, cabeceras[clave])
            for nombre, clave in (("From", "from"), ("Subject", "subject"), ("Date", "date"))
            if cabeceras.get(clave)
        ) + "\r\n"
        correo = _parsear_correo(identificador, b"", crudo.encode("ascii", "replace"))
        return replace(correo, importante="IMPORTANT" in datos.get("labelIds", []))

    def leer_texto(self, carpeta: str, uid: str) -> str:
        """Descarga el mensaje completo y devuelve su texto, sin marcarlo como leído."""
        datos = self._peticion("GET", f"/messages/{urllib.parse.quote(uid)}", {"format": "raw"})
        bruto = datos.get("raw", "")
        try:
            crudo = base64.urlsafe_b64decode(bruto + "=" * (-len(bruto) % 4))
        except (binascii.Error, ValueError) as exc:
            raise AccionNoValida(f"Gmail devolvió el mensaje {uid} en un formato ilegible.") from exc
        if not crudo:
            raise AccionNoValida(f"No se pudo leer el mensaje {uid}.")
        return extraer_texto(crudo)

    def mover_a_papelera(self, carpeta: str, uids: list[str], papelera: str) -> int:
        """Igual que :meth:`mover_uids_a_papelera`, pero devuelve cuántos se movieron."""
        return len(self.mover_uids_a_papelera(carpeta, uids, papelera))

    def mover_uids_a_papelera(self, carpeta: str, uids: list[str], papelera: str) -> list[str]:
        """Manda cada mensaje a la papelera de Gmail (se borra solo a los 30 días)."""
        movidos: list[str] = []
        for uid in uids:
            try:
                self._peticion("POST", f"/messages/{urllib.parse.quote(uid)}/trash")
            except AccionNoValida:
                continue  # ya no existe: se cuenta como no movido
            except (SinRedError, CredencialesError):
                if not movidos:
                    raise
                break  # se informa de los que sí se movieron
            movidos.append(uid)
        return movidos
