"""Modo demo: un buzón de ejemplo en memoria, sin Gmail ni contraseñas.

Sirve para que cualquiera (el profesor, un compañero) pruebe todas las
acciones, incluidas las de IA, sin dar acceso a su correo. Los correos salen
de ``plantillas/demo.json`` y sus fechas se calculan desde «ahora», así que
siempre caen dentro de las últimas 24 horas.

Lo que se «borra» solo desaparece de la memoria: no se toca ningún correo real.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from importlib.resources import files

from .config import Cuenta
from .errores import AccionNoValida, ConfigError
from .imap_client import Correo, filtrar_por_horas


class ClienteDemo:
    """Imita a ``ClienteIMAP`` y ``ClienteGmailAPI`` con correos de ejemplo."""

    def __init__(self, cuenta: Cuenta, ahora: datetime | None = None) -> None:
        self.cuenta = cuenta
        self._ahora = ahora
        # carpeta real («INBOX», «[Gmail]/Spam»…) → correos; y uid → texto del cuerpo
        self._carpetas: dict[str, list[Correo]] = {}
        self._textos: dict[str, str] = {}

    def __enter__(self) -> ClienteDemo:
        return self.conectar()

    def __exit__(self, *exc: object) -> bool:
        self.cerrar()
        return False

    def conectar(self) -> ClienteDemo:
        """Carga los correos de ejemplo; no abre ninguna conexión."""
        ahora = self._ahora or datetime.now(timezone.utc)
        for alias, mensajes in self._leer_plantilla().items():
            carpeta = self.cuenta.resolver_carpeta(alias)
            self._carpetas[carpeta] = []
            for indice, mensaje in enumerate(mensajes, start=1):
                uid = f"{alias}-{indice}"
                try:
                    correo = Correo(
                        uid=uid,
                        remitente=str(mensaje["remitente"]),
                        asunto=str(mensaje["asunto"]),
                        fecha=ahora - timedelta(hours=float(mensaje["hace_horas"])),
                        importante=bool(mensaje.get("importante", False)),
                    )
                except (KeyError, TypeError, ValueError, AttributeError) as exc:
                    raise ConfigError(
                        f"demo.json: el correo {indice} de «{alias}» está mal ({exc!r}). "
                        "Necesita remitente, asunto y hace_horas."
                    ) from exc
                self._carpetas[carpeta].append(correo)
                self._textos[uid] = str(mensaje.get("texto", ""))
        # Aserción de desarrollo: los UID son la clave para borrar; repetidos borrarían de más.
        uids = [c.uid for correos in self._carpetas.values() for c in correos]
        assert len(uids) == len(set(uids)), "UID repetidos en el modo demo"
        # La papelera empieza vacía, pero existe: «listar papelera» no debe fallar.
        self._carpetas.setdefault(self.cuenta.carpeta_papelera, [])
        return self

    @staticmethod
    def _leer_plantilla() -> dict[str, list[dict]]:
        """Lee ``plantillas/demo.json`` del paquete (va dentro de la instalación)."""
        try:
            texto = (files("buzon") / "plantillas" / "demo.json").read_text(encoding="utf-8")
            datos = json.loads(texto)
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(f"No se pudieron cargar los correos de ejemplo del modo demo: {exc}") from exc
        valido = isinstance(datos, dict) and all(isinstance(v, list) for v in datos.values())
        if not valido:
            raise ConfigError("demo.json debe ser un objeto {carpeta: [correos]}.")
        return datos

    def cerrar(self) -> None:
        """Nada que cerrar: todo vive en memoria."""

    def _carpeta(self, carpeta: str) -> list[Correo]:
        if carpeta not in self._carpetas:
            disponibles = ", ".join(sorted(self._carpetas))
            raise AccionNoValida(
                f"En el modo demo no existe la carpeta «{carpeta}». Hay: {disponibles} "
                "(o los alias entrada, spam y papelera)."
            )
        return self._carpetas[carpeta]

    def listar(
        self,
        carpeta: str,
        horas: int | None = 24,
        ahora: datetime | None = None,
    ) -> list[Correo]:
        correos = list(self._carpeta(carpeta))
        if horas is None:
            return correos
        return filtrar_por_horas(correos, horas, ahora)

    def leer_texto(self, carpeta: str, uid: str) -> str:
        self._carpeta(carpeta)
        return self._textos.get(uid, "")

    def mover_a_papelera(self, carpeta: str, uids: list[str], papelera: str) -> int:
        return len(self.mover_uids_a_papelera(carpeta, uids, papelera))

    def mover_uids_a_papelera(self, carpeta: str, uids: list[str], papelera: str) -> list[str]:
        """Pasa los correos a la papelera de memoria y devuelve los UID movidos."""
        origen = self._carpeta(carpeta)
        pedidos = set(uids)
        movidos = [correo for correo in origen if correo.uid in pedidos]
        self._carpetas[carpeta] = [correo for correo in origen if correo.uid not in pedidos]
        self._carpetas.setdefault(papelera, []).extend(movidos)
        return [correo.uid for correo in movidos]
