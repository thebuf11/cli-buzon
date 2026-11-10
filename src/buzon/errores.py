"""Excepciones propias de la herramienta.

Todas heredan de :class:`BuzonError` para que la interfaz pueda capturarlas
de una vez y mostrar un mensaje humano en lugar de un traceback.
"""


class BuzonError(Exception):
    """Error controlado: se muestra al usuario sin traceback."""


class ConfigError(BuzonError):
    """``acciones.json`` ilegible o inválido (código de salida 3)."""


class CredencialesError(BuzonError):
    """Faltan credenciales o el servidor las rechaza."""


class SinRedError(BuzonError):
    """No se puede conectar con IMAP o con el servicio de IA."""


class AccionNoValida(BuzonError):
    """La acción no existe o no se puede ejecutar con estos datos."""
