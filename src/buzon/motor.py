"""El motor: une configuración, cliente IMAP y acciones.

La interfaz no habla con IMAP ni con las clases de acción: le pide al motor
que ejecute un nombre y el motor decide qué hacer.
"""

from __future__ import annotations

from rich.console import Console

from .acciones import ACCIONES
from .config import Accion, Configuracion, obtener_credenciales
from .demo import ClienteDemo
from .gmail_api import ClienteGmailAPI
from .imap_client import ClienteIMAP


class Motor:
    """Ejecuta las acciones definidas en ``acciones.json``."""

    def __init__(
        self,
        configuracion: Configuracion,
        consola: Console,
        cliente: object | None = None,
        fabrica_cliente: type[ClienteIMAP] = ClienteIMAP,
    ) -> None:
        self.config = configuracion
        self.consola = consola
        self._cliente = cliente
        self._fabrica = fabrica_cliente

    def __enter__(self) -> Motor:
        return self

    def __exit__(self, *exc: object) -> bool:
        self.cerrar()
        return False

    def cliente(self):
        """Devuelve el cliente IMAP, conectándose la primera vez que hace falta."""
        if self._cliente is None:
            cuenta = self.config.cuenta
            if cuenta.proveedor == "demo":
                # Correos de ejemplo en memoria: ni red, ni contraseñas, ni Gmail.
                self.consola.print(
                    "[yellow]Modo demo:[/yellow] correos de ejemplo; no se toca ningún correo real.\n"
                )
                self._cliente = ClienteDemo(cuenta).conectar()
                return self._cliente
            if cuenta.proveedor == "gmail-api":
                # HTTPS (443): no necesita GMAIL_APP_PASSWORD, usa OAuth.
                self._cliente = ClienteGmailAPI(cuenta, base=self.config.ruta.parent).conectar()
                return self._cliente
            usuario, password = obtener_credenciales(cuenta)
            self._cliente = self._fabrica(
                servidor=cuenta.servidor,
                puerto=cuenta.puerto,
                usuario=usuario,
                password=password,
            ).conectar()
        return self._cliente

    def ejecutar(self, nombre: str, simular: bool = False, si: bool = False) -> int:
        return self.ejecutar_definicion(self.config.accion(nombre), simular=simular, si=si)

    def ejecutar_definicion(self, accion: Accion, simular: bool = False, si: bool = False) -> int:
        """Ejecuta una acción que no tiene por qué estar en ``acciones.json``."""
        clase = ACCIONES[accion.tipo]
        return clase(accion, self).ejecutar(simular=simular, si=si)

    def cerrar(self) -> None:
        if self._cliente is not None:
            cerrar = getattr(self._cliente, "cerrar", None)
            if callable(cerrar):
                cerrar()
            self._cliente = None
