"""Cliente IMAP mínimo, solo con la librería estándar.

``imaplib`` habla con Gmail y ``email`` entiende las cabeceras (tildes
incluidas). El resto del programa no sabe nada de IMAP: usa :class:`Correo`.
"""

from __future__ import annotations

import html
import imaplib
import re
import urllib.parse
from dataclasses import dataclass
from html.parser import HTMLParser
from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime

from .errores import AccionNoValida, CredencialesError, SinRedError

MESES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
# La lista acaba en el primer «)» que NO está dentro de comillas: una etiqueta
# como "Clase (DAM)" no debe cortarla (si no, se perdería \Important).
PATRON_ETIQUETAS = re.compile(rb'X-GM-LABELS \(((?:"(?:[^"\\]|\\.)*"|[^()"])*)\)')
PATRON_LIST = re.compile(rb'\((?P<atributos>[^)]*)\) (?:"(?:[^"\\]|\\.)*"|NIL) (?P<nombre>.+)$')


@dataclass(frozen=True)
class Correo:
    """Lo que la herramienta necesita saber de un mensaje."""

    uid: str
    remitente: str
    asunto: str
    fecha: datetime | None
    importante: bool = False


def _fecha_imap(momento: datetime) -> str:
    """Formato de fecha que entiende IMAP, sin depender del idioma del sistema."""
    return f"{momento.day:02d}-{MESES[momento.month - 1]}-{momento.year}"


def _parsear_fecha(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        fecha = parsedate_to_datetime(valor)
    except (TypeError, ValueError):
        return None
    if fecha is None:
        return None
    if fecha.tzinfo is None:
        return fecha.replace(tzinfo=timezone.utc)
    return fecha.astimezone(timezone.utc)


def _etiquetas(meta: bytes) -> set[str]:
    """Extrae las etiquetas de Gmail (``\\Inbox``, ``\\Important``...) de la respuesta."""
    coincidencia = PATRON_ETIQUETAS.search(meta)
    if not coincidencia:
        return set()

    etiquetas: set[str] = set()
    for comilla, sistema in re.findall(rb'"((?:[^"\\]|\\.)*)"|(\\[A-Za-z]+)', coincidencia.group(1)):
        if comilla:
            etiquetas.add(comilla.decode("utf-8", "replace").replace('\\"', '"'))
        elif sistema:
            etiquetas.add(sistema.decode("ascii", "replace"))
    return etiquetas


def _parsear_correo(uid: str, meta: bytes, cuerpo: bytes) -> Correo:
    mensaje = BytesParser(policy=policy.default).parsebytes(cuerpo)
    remitente = mensaje.get("From")
    asunto = mensaje.get("Subject")
    etiquetas = _etiquetas(meta)
    return Correo(
        uid=uid,
        remitente=limpiar_control(str(remitente)) if remitente else "(remitente desconocido)",
        asunto=limpiar_control(str(asunto)) if asunto else "(sin asunto)",
        fecha=_parsear_fecha(mensaje.get("Date")),
        importante=any(etiqueta.lower() == "\\important" for etiqueta in etiquetas),
    )


class _TextoDeHtml(HTMLParser):
    """Convierte HTML en texto plano legible, ignorando ``<script>`` y ``<style>``."""

    BLOQUES = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "table"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.partes: list[str] = []
        self._ignorar = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in {"script", "style", "head"}:
            self._ignorar += 1
        elif tag in self.BLOQUES:
            self.partes.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "head"} and self._ignorar:
            self._ignorar -= 1
        elif tag in self.BLOQUES:
            self.partes.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignorar:
            self.partes.append(data)


def _html_a_texto(html: str) -> str:
    lector = _TextoDeHtml()
    lector.feed(html)
    lector.close()
    return "".join(lector.partes)


def _limpiar_lineas(texto: str) -> str:
    """Quita espacios sobrantes y deja como mucho una línea en blanco seguida."""
    lineas = [" ".join(linea.split()) for linea in texto.splitlines()]
    resultado: list[str] = []
    for linea in lineas:
        if linea or (resultado and resultado[-1]):
            resultado.append(linea)
    return "\n".join(resultado).strip()


def extraer_texto(crudo: bytes) -> str:
    """Devuelve el cuerpo legible de un mensaje: texto plano o, si no hay, HTML limpio."""
    mensaje = BytesParser(policy=policy.default).parsebytes(crudo)
    parte = mensaje.get_body(preferencelist=("plain", "html"))
    if parte is None:
        return "(el mensaje no tiene texto que mostrar)"
    try:
        contenido = parte.get_content()
    except (LookupError, ValueError):
        # Charset desconocido o mal declarado: se decodifica a mano.
        contenido = (parte.get_payload(decode=True) or b"").decode("utf-8", "replace")
    if parte.get_content_subtype() == "html":
        contenido = _html_a_texto(contenido)
    else:
        contenido = _limpiar_restos_html(contenido)
    contenido = _acortar_enlaces(PATRON_INVISIBLES.sub("", contenido))
    return _quitar_enlaces_repetidos(_limpiar_lineas(limpiar_control(contenido))) or "(mensaje vacío)"


def _quitar_enlaces_repetidos(texto: str) -> str:
    """Un «[enlace: x]» igual al anterior (aunque haya líneas en blanco entre medias) sobra."""
    resultado: list[str] = []
    ultima = ""
    for linea in texto.splitlines():
        if linea.startswith("[enlace: ") and linea == ultima:
            if resultado and not resultado[-1]:
                resultado.pop()  # también la línea en blanco que lo separaba
            continue
        resultado.append(linea)
        if linea:
            ultima = linea
    return "\n".join(resultado).strip()


# Caracteres invisibles que los boletines usan de relleno (&zwnj;, &nbsp; de ancho cero…).
PATRON_INVISIBLES = re.compile("[­͏​-‏⁠-⁤﻿]")
# Etiquetas HTML sueltas que algunos boletines dejan en su versión «texto plano».
# Solo nombres de etiqueta conocidos, para no comerse direcciones como <ana@x.es>.
PATRON_ETIQUETA_SUELTA = re.compile(
    r"</?(?:span|b|i|u|em|strong|br|p|div|font|a|small|center|td|tr|table)\b[^<>]*>", re.IGNORECASE
)
PATRON_ENLACE = re.compile(r"https?://[^\s<>\"')\]]+")
LARGO_MAX_ENLACE = 60


def _limpiar_restos_html(texto: str) -> str:
    return PATRON_ETIQUETA_SUELTA.sub("", html.unescape(texto))


def _acortar_enlaces(texto: str) -> str:
    """Los enlaces de seguimiento ocupan varias líneas: se dejan en «[enlace: dominio]»."""

    def acortar(coincidencia: re.Match) -> str:
        url = coincidencia.group(0)
        if len(url) <= LARGO_MAX_ENLACE:
            return url
        return f"[enlace: {urllib.parse.urlsplit(url).netloc}]"

    return PATRON_ENLACE.sub(acortar, texto)


PATRON_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def limpiar_control(texto: str) -> str:
    """Quita caracteres de control (ESC incluido) para que un correo no pueda
    mandar secuencias a la terminal; conserva saltos de línea y tabuladores."""
    return PATRON_CONTROL.sub("", texto)


def filtrar_por_horas(
    correos: list[Correo],
    horas: int,
    ahora: datetime | None = None,
) -> list[Correo]:
    """Se queda con los correos dentro de la ventana de ``horas``."""
    limite = (ahora or datetime.now(timezone.utc)) - timedelta(hours=horas)
    return [correo for correo in correos if correo.fecha is None or correo.fecha >= limite]


class ClienteIMAP:
    """Conexión IMAP segura. Se usa como context manager."""

    def __init__(
        self,
        servidor: str,
        puerto: int,
        usuario: str,
        password: str,
        timeout: float = 30.0,
    ) -> None:
        self.servidor = servidor
        self.puerto = puerto
        self.usuario = usuario
        self.password = password
        self.timeout = timeout
        self._conexion: imaplib.IMAP4_SSL | None = None

    def __enter__(self) -> ClienteIMAP:
        return self.conectar()

    def __exit__(self, *exc: object) -> bool:
        self.cerrar()
        return False

    def conectar(self) -> ClienteIMAP:
        try:
            self._conexion = imaplib.IMAP4_SSL(self.servidor, self.puerto, timeout=self.timeout)
        except (OSError, imaplib.IMAP4.error) as exc:
            raise SinRedError(
                f"No se pudo conectar con {self.servidor}:{self.puerto}. Comprueba tu conexión."
            ) from exc

        try:
            self._conexion.login(self.usuario, self.password)
        except imaplib.IMAP4.error as exc:
            raise CredencialesError(
                "Gmail rechazó las credenciales. Revisa GMAIL_USUARIO y GMAIL_APP_PASSWORD "
                "(contraseña de aplicación, no la de tu cuenta) y que IMAP esté activado."
            ) from exc
        return self

    def cerrar(self) -> None:
        if self._conexion is None:
            return
        try:
            self._conexion.logout()
        except (imaplib.IMAP4.error, OSError):
            pass
        finally:
            self._conexion = None

    @property
    def conexion(self) -> imaplib.IMAP4_SSL:
        if self._conexion is None:
            raise SinRedError("La conexión IMAP no está abierta.")
        return self._conexion

    def _seleccionar(self, carpeta: str, readonly: bool) -> None:
        tip, _ = self.conexion.select(f'"{carpeta}"', readonly=readonly)
        if tip != "OK":
            raise AccionNoValida(
                f"No se pudo abrir la carpeta «{carpeta}». Revisa su nombre en acciones.json "
                "(en Gmail, spam suele ser «[Gmail]/Spam» y papelera «[Gmail]/Trash»)."
            )

    def listar(
        self,
        carpeta: str,
        horas: int | None = 24,
        ahora: datetime | None = None,
    ) -> list[Correo]:
        """Lista los correos de una carpeta. ``horas=None`` significa todos."""
        try:
            self._seleccionar(carpeta, readonly=True)
            if horas is None:
                tip, datos = self.conexion.uid("SEARCH", None, "ALL")
            else:
                desde = _fecha_imap((ahora or datetime.now(timezone.utc)) - timedelta(hours=horas))
                tip, datos = self.conexion.uid("SEARCH", None, "SINCE", desde)
            if tip != "OK":
                raise AccionNoValida(f"No se pudo buscar en «{carpeta}».")

            uids = datos[0].split() if datos and datos[0] else []
            correos = [self._leer(uid) for uid in uids]
        except (imaplib.IMAP4.error, OSError) as exc:
            raise SinRedError(f"Se perdió la conexión con el servidor: {exc}") from exc

        if horas is None:
            return correos
        return filtrar_por_horas(correos, horas, ahora)

    def _leer(self, uid: bytes) -> Correo:
        criterio = "(X-GM-LABELS BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])"
        try:
            tip, datos = self.conexion.uid("FETCH", uid, criterio)
        except imaplib.IMAP4.error:
            # Otros servidores no entienden X-GM-LABELS: se lee sin etiquetas.
            tip, datos = self.conexion.uid(
                "FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])"
            )

        if tip != "OK" or not datos:
            raise AccionNoValida(f"No se pudo leer el mensaje UID {uid!r}.")

        meta = b""
        cuerpo = b""
        for parte in datos:
            if isinstance(parte, tuple) and len(parte) == 2:
                meta = parte[0] or b""
                cuerpo = parte[1] or b""
                break

        return _parsear_correo(uid.decode("ascii", "replace"), meta, cuerpo)

    def leer_texto(self, carpeta: str, uid: str) -> str:
        """Descarga el mensaje completo y devuelve su texto, sin marcarlo como leído."""
        try:
            self._seleccionar(carpeta, readonly=True)
            tip, datos = self.conexion.uid("FETCH", uid, "(BODY.PEEK[])")
        except (imaplib.IMAP4.error, OSError) as exc:
            raise SinRedError(f"Se perdió la conexión con el servidor: {exc}") from exc

        crudo = b""
        for parte in datos or []:
            if isinstance(parte, tuple) and len(parte) == 2:
                crudo = parte[1] or b""
                break
        if tip != "OK" or not crudo:
            raise AccionNoValida(f"No se pudo leer el mensaje UID {uid}.")
        return extraer_texto(crudo)

    def buscar_papelera(self) -> str | None:
        """Busca la carpeta marcada como ``\\Trash`` (en Gmail en español: «[Gmail]/Papelera»)."""
        try:
            tip, datos = self.conexion.list()
        except (imaplib.IMAP4.error, OSError):
            return None
        if tip != "OK":
            return None
        for linea in datos or []:
            if not isinstance(linea, bytes):
                continue
            coincidencia = PATRON_LIST.match(linea)
            if coincidencia and b"\\trash" in coincidencia.group("atributos").lower():
                return coincidencia.group("nombre").strip().strip(b'"').decode("utf-8", "replace")
        return None

    def mover_a_papelera(self, carpeta: str, uids: list[str], papelera: str) -> int:
        """Igual que :meth:`mover_uids_a_papelera`, pero devuelve cuántos se movieron."""
        return len(self.mover_uids_a_papelera(carpeta, uids, papelera))

    def mover_uids_a_papelera(self, carpeta: str, uids: list[str], papelera: str) -> list[str]:
        """Copia los mensajes a la papelera, los quita de ``carpeta`` y devuelve los UID movidos.

        Es lo mismo que hace el botón «Eliminar» de Gmail: los mensajes quedan
        30 días en la papelera antes de borrarse del todo. Si la carpeta
        configurada no existe (cuenta en otro idioma), se usa la que el servidor
        marca como papelera.
        """
        if not uids:
            return []

        try:
            if papelera != carpeta and self.conexion.select(f'"{papelera}"', readonly=True)[0] != "OK":
                detectada = self.buscar_papelera()
                if detectada is None:
                    raise AccionNoValida(
                        f"No existe la carpeta de papelera «{papelera}» y el servidor no indica otra. "
                        "Revisa «carpeta_papelera» en acciones.json."
                    )
                papelera = detectada
            self._seleccionar(carpeta, readonly=False)
            movidos: list[str] = []
            for uid in uids:
                tip, _ = self.conexion.uid("COPY", uid, f'"{papelera}"')
                if tip != "OK":
                    continue
                tip, _ = self.conexion.uid("STORE", uid, "+FLAGS", "(\\Deleted)")
                if tip != "OK":
                    continue
                movidos.append(uid)
            if movidos:
                try:
                    # Solo borra los marcados aquí, no otros \Deleted de otro cliente.
                    self.conexion.uid("EXPUNGE", ",".join(movidos))
                except imaplib.IMAP4.error:
                    self.conexion.expunge()  # servidor sin UIDPLUS
            return movidos
        except (imaplib.IMAP4.error, OSError) as exc:
            raise SinRedError(f"Falló la limpieza de «{carpeta}»: {exc}") from exc
