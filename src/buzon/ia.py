"""Capa de IA: un cliente HTTP compatible con la API de OpenAI.

La clave y la URL viven en variables de entorno (``.env``), nunca en el
código. Si no hay configuración o no hay red, la CLI sigue funcionando.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Sequence

from .config import Configuracion
from .errores import SinRedError
from .imap_client import Correo

SISTEMA = "Eres un asistente breve que resume correo electrónico en español."


def _prompt(correos: Sequence[Correo], horas: int) -> str:
    lineas = [f"Estos son los correos de las últimas {horas} horas:", ""]
    for correo in correos:
        if correo.fecha is not None:
            fecha = correo.fecha.astimezone().strftime("%d/%m %H:%M")
        else:
            fecha = "hora desconocida"
        lineas.append(f"- [{fecha}] De: {correo.remitente} | Asunto: {correo.asunto}")
    lineas += [
        "",
        "Resume en español, en 3 a 5 líneas, lo más importante para el usuario.",
        "Señala lo urgente o con plazo y qué puede ignorar. No inventes datos.",
    ]
    return "\n".join(lineas)


class ProveedorIA:
    """Llama a un servicio compatible con ``/v1/chat/completions``."""

    def __init__(self, url: str, clave: str, modelo: str, timeout: float = 60.0) -> None:
        self.url = url
        self.clave = clave
        self.modelo = modelo
        self.timeout = timeout

    @classmethod
    def desde_entorno(cls, configuracion: Configuracion) -> ProveedorIA:
        ia = configuracion.ia
        return cls(
            url=os.environ.get(ia.url_env, "").strip(),
            clave=os.environ.get(ia.clave_env, "").strip(),
            modelo=os.environ.get(ia.modelo_env, "").strip() or ia.modelo_por_defecto,
        )

    @property
    def disponible(self) -> bool:
        return bool(self.url)

    def resumir(self, correos: Sequence[Correo], horas: int) -> str:
        if not self.disponible:
            raise SinRedError(
                "No hay IA configurada: define IA_API_URL (y IA_API_KEY si tu servicio la pide) en .env."
            )

        carga = {
            "model": self.modelo,
            "messages": [
                {"role": "system", "content": SISTEMA},
                {"role": "user", "content": _prompt(correos, horas)},
            ],
            "temperature": 0.2,
        }
        cabeceras = {"Content-Type": "application/json"}
        if self.clave:
            cabeceras["Authorization"] = f"Bearer {self.clave}"

        peticion = urllib.request.Request(
            self.url,
            data=json.dumps(carga).encode("utf-8"),
            headers=cabeceras,
            method="POST",
        )

        try:
            with urllib.request.urlopen(peticion, timeout=self.timeout) as respuesta:
                datos = json.loads(respuesta.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise SinRedError(
                f"El servicio de IA respondió con error HTTP {exc.code}. Revisa IA_API_URL, IA_API_KEY y IA_MODELO."
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise SinRedError("No se pudo contactar con el servicio de IA. Revisa tu conexión.") from exc
        except json.JSONDecodeError as exc:
            raise SinRedError("El servicio de IA devolvió algo que no es JSON.") from exc

        try:
            contenido = datos["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise SinRedError("El servicio de IA devolvió una respuesta inesperada.") from exc

        texto = str(contenido).strip()
        if not texto:
            raise SinRedError("El servicio de IA devolvió un resumen vacío.")
        return texto
