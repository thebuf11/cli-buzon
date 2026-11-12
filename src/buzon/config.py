"""Lectura y validación de ``acciones.json`` y del fichero ``.env``.

Todo lo que el usuario puede escribir mal (JSON roto, campos que faltan,
tipos incorrectos) se convierte aquí en un :class:`ConfigError` con un
mensaje que dice exactamente qué campo falla.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from difflib import get_close_matches
from importlib.resources import files
from pathlib import Path

from platformdirs import user_config_dir

from .errores import AccionNoValida, ConfigError, CredencialesError

PROVEEDORES = {"imap", "gmail-api"}
PATRON_NOMBRE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# Campos opcionales que admite cada tipo, además de nombre, descripcion y tipo.
# Un campo que el tipo no usa es casi siempre un error: «horas» en
# «mover-papelera» haría creer que solo se borran las últimas horas, y se borra todo.
CAMPOS_POR_TIPO: dict[str, frozenset[str]] = {
    "resumen-ia": frozenset({"carpeta", "horas"}),
    "listar": frozenset({"carpeta", "horas"}),
    "mover-papelera": frozenset({"carpeta", "confirmar"}),
    "exportar": frozenset({"carpeta", "horas", "destino"}),
    "revisar": frozenset({"carpeta", "horas"}),
}
TIPOS_VALIDOS = set(CAMPOS_POR_TIPO)
CAMPOS_COMUNES = frozenset({"nombre", "descripcion", "tipo"})
CAMPOS_ACCION = CAMPOS_COMUNES.union(*CAMPOS_POR_TIPO.values())
CAMPOS_RAIZ = frozenset({"version", "cuenta", "ia", "acciones"})
CAMPOS_CUENTA = frozenset(
    {
        "proveedor",
        "servidor",
        "puerto",
        "usuario_env",
        "password_env",
        "carpeta_entrada",
        "carpeta_spam",
        "carpeta_papelera",
        "credenciales_api",
        "token_api",
    }
)
CAMPOS_IA = frozenset({"url_env", "clave_env", "modelo_env", "modelo_por_defecto"})


def _comprobar_campos(datos: dict, validos: frozenset[str], contexto: str) -> None:
    """Rechaza claves desconocidas y sugiere la más parecida.

    Las claves que empiezan por ``_`` se permiten como comentarios
    (JSON no tiene comentarios): ``"_nota": "esto lo uso los lunes"``.
    """
    for clave in datos:
        if not isinstance(clave, str) or clave.startswith("_") or clave in validos:
            continue
        prefijo = f"{contexto}." if contexto else ""
        parecidas = get_close_matches(clave, validos, n=1, cutoff=0.6)
        pista = f" ¿Quisiste decir «{parecidas[0]}»?" if parecidas else ""
        raise ConfigError(
            f"{prefijo}{clave}: campo desconocido.{pista} "
            f"Campos válidos: {', '.join(sorted(validos))}"
        )


@dataclass(frozen=True)
class Cuenta:
    """Datos de conexión con el buzón IMAP."""

    servidor: str
    puerto: int
    usuario_env: str
    password_env: str
    carpeta_entrada: str
    carpeta_spam: str
    carpeta_papelera: str
    proveedor: str = "imap"
    credenciales_api: str = "credentials.json"
    token_api: str = "token.json"

    def resolver_carpeta(self, alias: str) -> str:
        """Traduce ``entrada``/``spam``/``papelera`` al nombre real de la carpeta."""
        return {
            "entrada": self.carpeta_entrada,
            "spam": self.carpeta_spam,
            "papelera": self.carpeta_papelera,
        }.get(alias, alias)


@dataclass(frozen=True)
class Ia:
    """Nombres de las variables de entorno del servicio de IA."""

    url_env: str
    clave_env: str
    modelo_env: str
    modelo_por_defecto: str


@dataclass(frozen=True)
class Accion:
    """Una acción definida por el usuario en ``acciones.json``."""

    nombre: str
    descripcion: str
    tipo: str
    horas: int | None = 24
    carpeta: str = "entrada"
    destino: str = ""
    confirmar: bool = False


@dataclass(frozen=True)
class Configuracion:
    """El fichero ``acciones.json`` ya validado."""

    ruta: Path
    cuenta: Cuenta
    ia: Ia
    acciones: tuple[Accion, ...]
    avisos: tuple[str, ...] = ()

    def accion(self, nombre: str) -> Accion:
        for accion in self.acciones:
            if accion.nombre == nombre:
                return accion
        disponibles = ", ".join(a.nombre for a in self.acciones) or "(ninguna)"
        raise AccionNoValida(f"No existe la acción «{nombre}». Disponibles: {disponibles}")


def _texto(datos: dict, clave: str, contexto: str, defecto: str | None = None) -> str:
    valor = datos.get(clave, defecto)
    if not isinstance(valor, str) or not valor.strip():
        raise ConfigError(f"{contexto}.{clave}: debe ser un texto no vacío")
    return valor.strip()


def _entero(
    datos: dict,
    clave: str,
    contexto: str,
    defecto: int,
    minimo: int,
    maximo: int | None = None,
) -> int:
    valor = datos.get(clave, defecto)
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ConfigError(
            f"{contexto}.{clave}: se esperaba un número entero, se encontró {valor!r}"
        )
    if valor < minimo or (maximo is not None and valor > maximo):
        rango = f"entre {minimo} y {maximo}" if maximo is not None else f"mayor o igual que {minimo}"
        raise ConfigError(f"{contexto}.{clave}: debe estar {rango}")
    return valor


def _leer_cuenta(datos: dict) -> Cuenta:
    bruto = datos.get("cuenta", {})
    if not isinstance(bruto, dict):
        raise ConfigError("cuenta: debe ser un objeto JSON {...}")
    _comprobar_campos(bruto, CAMPOS_CUENTA, "cuenta")
    proveedor = _texto(bruto, "proveedor", "cuenta", "imap")
    if proveedor not in PROVEEDORES:
        raise ConfigError(
            f"cuenta.proveedor: «{proveedor}» no es válido. Usa uno de: {', '.join(sorted(PROVEEDORES))}"
        )
    return Cuenta(
        proveedor=proveedor,
        credenciales_api=_texto(bruto, "credenciales_api", "cuenta", "credentials.json"),
        token_api=_texto(bruto, "token_api", "cuenta", "token.json"),
        servidor=_texto(bruto, "servidor", "cuenta", "imap.gmail.com"),
        puerto=_entero(bruto, "puerto", "cuenta", 993, 1, 65535),
        usuario_env=_texto(bruto, "usuario_env", "cuenta", "GMAIL_USUARIO"),
        password_env=_texto(bruto, "password_env", "cuenta", "GMAIL_APP_PASSWORD"),
        carpeta_entrada=_texto(bruto, "carpeta_entrada", "cuenta", "INBOX"),
        carpeta_spam=_texto(bruto, "carpeta_spam", "cuenta", "[Gmail]/Spam"),
        carpeta_papelera=_texto(bruto, "carpeta_papelera", "cuenta", "[Gmail]/Trash"),
    )


def _leer_ia(datos: dict) -> Ia:
    bruto = datos.get("ia", {})
    if not isinstance(bruto, dict):
        raise ConfigError("ia: debe ser un objeto JSON {...}")
    _comprobar_campos(bruto, CAMPOS_IA, "ia")
    return Ia(
        url_env=_texto(bruto, "url_env", "ia", "IA_API_URL"),
        clave_env=_texto(bruto, "clave_env", "ia", "IA_API_KEY"),
        modelo_env=_texto(bruto, "modelo_env", "ia", "IA_MODELO"),
        modelo_por_defecto=_texto(bruto, "modelo_por_defecto", "ia", "llama3"),
    )


def _leer_accion(datos: dict, contexto: str) -> Accion:
    # Lo primero, las erratas: con «"tpo": "listar"» el mensaje útil es «¿quisiste decir tipo?»,
    # no «tipo None no es válido».
    _comprobar_campos(datos, CAMPOS_ACCION, contexto)

    nombre = datos.get("nombre")
    if not isinstance(nombre, str) or not PATRON_NOMBRE.match(nombre):
        raise ConfigError(
            f"{contexto}.nombre: usa minúsculas, números y guiones (por ejemplo «limpiar-spam»); "
            f"se encontró {nombre!r}"
        )

    descripcion = datos.get("descripcion")
    if not isinstance(descripcion, str) or not descripcion.strip():
        raise ConfigError(f"{contexto}.descripcion: es obligatoria y no puede estar vacía")

    tipo = datos.get("tipo")
    if tipo not in TIPOS_VALIDOS:
        raise ConfigError(
            f"{contexto}.tipo: «{tipo}» no es válido. Usa uno de: "
            f"{', '.join(sorted(TIPOS_VALIDOS))}"
        )

    # Los campos que existen pero este tipo no usa (las erratas ya se han detectado arriba).
    permitidos = CAMPOS_COMUNES | CAMPOS_POR_TIPO[tipo]
    for clave in datos:
        if isinstance(clave, str) and not clave.startswith("_") and clave not in permitidos:
            raise ConfigError(
                f"{contexto}.{clave}: las acciones de tipo «{tipo}» no usan este campo. "
                f"Campos válidos para «{tipo}»: {', '.join(sorted(CAMPOS_POR_TIPO[tipo]))}"
            )

    if "horas" in datos:
        horas: int | None = _entero(datos, "horas", contexto, 24, 1)
    else:
        horas = 24 if tipo in {"resumen-ia", "exportar", "revisar"} else None

    carpeta = datos.get("carpeta", "entrada")
    if not isinstance(carpeta, str) or not carpeta.strip():
        raise ConfigError(
            f"{contexto}.carpeta: debe ser «entrada», «spam», «papelera» o un nombre de carpeta IMAP"
        )

    destino = datos.get("destino", "")
    if not isinstance(destino, str):
        raise ConfigError(f"{contexto}.destino: debe ser un texto")
    if tipo == "exportar" and not destino.strip():
        raise ConfigError(f"{contexto}.destino: una acción «exportar» necesita una carpeta de destino")

    confirmar = datos.get("confirmar", False)
    if not isinstance(confirmar, bool):
        raise ConfigError(f"{contexto}.confirmar: debe ser true o false")

    return Accion(
        nombre=nombre,
        descripcion=descripcion.strip(),
        tipo=tipo,
        horas=horas,
        carpeta=carpeta.strip(),
        destino=destino.strip(),
        confirmar=confirmar,
    )


def cargar_configuracion(ruta: str | Path) -> Configuracion:
    """Lee y valida ``acciones.json``. Lanza :class:`ConfigError` si algo falla."""
    ruta = Path(ruta)
    if not ruta.exists():
        raise ConfigError(
            f"No existe el fichero de configuración «{ruta}». "
            "Ejecuta «buzon init» para crear uno o indica otro con --config."
        )

    try:
        texto = ruta.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"No se pudo leer «{ruta}»: {exc.strerror or exc}") from exc

    try:
        datos = json.loads(texto)
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"JSON mal formado en «{ruta.name}», línea {exc.lineno}, columna {exc.colno}: {exc.msg}"
        ) from exc

    if not isinstance(datos, dict):
        raise ConfigError("La raíz del fichero debe ser un objeto JSON {...}")

    if datos.get("version") != 1:
        raise ConfigError(f"version: se esperaba 1, se encontró {datos.get('version')!r}")
    _comprobar_campos(datos, CAMPOS_RAIZ, "")

    cuenta = _leer_cuenta(datos)
    ia = _leer_ia(datos)

    bruto = datos.get("acciones")
    if not isinstance(bruto, list) or not bruto:
        raise ConfigError("acciones: debe ser una lista con al menos una acción")

    acciones: list[Accion] = []
    vistos: set[str] = set()
    for indice, elemento in enumerate(bruto):
        contexto = f"acciones[{indice}]"
        if not isinstance(elemento, dict):
            raise ConfigError(f"{contexto}: cada acción debe ser un objeto JSON")
        accion = _leer_accion(elemento, contexto)
        if accion.nombre in vistos:
            raise ConfigError(f"{contexto}.nombre: «{accion.nombre}» está repetido")
        vistos.add(accion.nombre)
        acciones.append(accion)

    return Configuracion(
        ruta=ruta.resolve(),
        cuenta=cuenta,
        ia=ia,
        acciones=tuple(acciones),
        avisos=tuple(_avisos(acciones)),
    )


def _avisos(acciones: list[Accion]) -> list[str]:
    """Cosas válidas pero arriesgadas: no impiden usar la configuración."""
    avisos = []
    for accion in acciones:
        if accion.tipo == "mover-papelera" and not accion.confirmar:
            avisos.append(
                f"«{accion.nombre}» mueve correos a la papelera sin pedir confirmación; "
                "añade \"confirmar\": true para que pregunte antes."
            )
    return avisos


# cli-buzon/src/buzon/config.py → cli-buzon/. Solo sirve con «uv tool install --editable .»:
# instalado desde git, esta ruta cae dentro de site-packages y no hay acciones.json.
RAIZ_PROYECTO = Path(__file__).resolve().parents[2]


def carpeta_usuario() -> Path:
    """Carpeta de configuración del usuario según el sistema.

    Windows: ``%APPDATA%\\buzon`` · Linux: ``~/.config/buzon`` ·
    macOS: ``~/Library/Application Support/buzon``. La crea ``buzon init``.
    """
    return Path(user_config_dir("buzon", appauthor=False, roaming=True))


def buscar_configuracion(explicita: str | Path | None = None) -> Path:
    """Decide qué ``acciones.json`` usar, para que ``buzon`` funcione desde cualquier carpeta.

    Orden: ``--config`` → variable ``BUZON_CONFIG`` → ``./acciones.json`` →
    carpeta del usuario (``buzon init``) → el del proyecto (instalación editable).
    Si no hay ninguno, devuelve la ruta de la carpeta del usuario para que el
    error sugiera ``buzon init``.
    """
    if explicita is not None:
        return Path(explicita).expanduser()
    entorno = os.environ.get("BUZON_CONFIG", "").strip()
    if entorno:
        return Path(entorno).expanduser()
    local = Path("acciones.json")
    if local.exists():
        return local
    usuario = carpeta_usuario() / "acciones.json"
    if usuario.exists():
        return usuario
    proyecto = RAIZ_PROYECTO / "acciones.json"
    if proyecto.exists():
        return proyecto
    return usuario


# plantilla del paquete → nombre con el que se copia en la carpeta del usuario
PLANTILLAS = {"acciones.json": "acciones.json", "env.example": ".env"}


def inicializar(destino: Path) -> list[tuple[Path, bool]]:
    """Copia las plantillas a ``destino`` sin sobrescribir nada.

    Devuelve ``(ruta, creado)`` por fichero: ``creado`` es ``False`` si ya existía.
    """
    try:
        destino.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ConfigError(f"No se pudo crear «{destino}»: {exc.strerror or exc}") from exc

    origen = files("buzon") / "plantillas"
    resultado: list[tuple[Path, bool]] = []
    for plantilla, nombre in PLANTILLAS.items():
        ruta = destino / nombre
        if ruta.exists():
            resultado.append((ruta, False))
            continue
        try:
            ruta.write_text((origen / plantilla).read_text(encoding="utf-8"), encoding="utf-8")
        except OSError as exc:
            raise ConfigError(f"No se pudo escribir «{ruta}»: {exc.strerror or exc}") from exc
        resultado.append((ruta, True))
    return resultado


def cargar_env(ruta: str | Path = ".env") -> None:
    """Carga ``.env`` sin sobrescribir variables ya definidas en el sistema."""
    archivo = Path(ruta)
    if not archivo.exists():
        return
    try:
        lineas = archivo.read_text(encoding="utf-8").splitlines()
    except OSError:
        return

    for linea in lineas:
        limpia = linea.strip()
        if not limpia or limpia.startswith("#") or "=" not in limpia:
            continue
        clave, _, valor = limpia.partition("=")
        clave = clave.strip()
        valor = valor.strip().strip('"').strip("'")
        if clave:
            os.environ.setdefault(clave, valor)


def obtener_credenciales(cuenta: Cuenta) -> tuple[str, str]:
    """Devuelve usuario y contraseña de aplicación, o falla con un mensaje claro."""
    usuario = os.environ.get(cuenta.usuario_env, "").strip()
    password = os.environ.get(cuenta.password_env, "").strip()
    if not usuario or not password:
        raise CredencialesError(
            f"Faltan credenciales: define {cuenta.usuario_env} y {cuenta.password_env} "
            "en tu .env (copia .env.example). Para Gmail necesitas una contraseña de aplicación."
        )
    return usuario, password
