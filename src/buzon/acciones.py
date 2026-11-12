"""Las acciones que el motor sabe ejecutar.

Cada tipo de ``acciones.json`` tiene aquí una clase. La interfaz (``cli.py``)
no sabe qué hace cada acción: solo le pasa la definición al motor.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel

from .config import Accion, Configuracion
from .errores import AccionNoValida, BuzonError, SinRedError
from .ia import ProveedorIA
from .salida import LIMITE_FILAS, hora_local, mostrar_correos, nombre_remitente


class AccionBase:
    """Comportamiento común: guarda la definición y accede al motor."""

    def __init__(self, definicion: Accion, motor: object) -> None:
        self.definicion = definicion
        self.motor = motor

    @property
    def consola(self):  # tipo real: rich.console.Console
        return self.motor.consola

    @property
    def config(self) -> Configuracion:
        return self.motor.config

    def ejecutar(self, simular: bool = False, si: bool = False) -> int:
        raise NotImplementedError

    def _titulo(self, carpeta: str) -> str:
        if self.definicion.horas is None:
            return carpeta
        return f"{carpeta} · últimas {self.definicion.horas} h"


class AccionListar(AccionBase):
    """Lista los correos de una carpeta (solo lectura)."""

    def ejecutar(self, simular: bool = False, si: bool = False) -> int:
        cuenta = self.config.cuenta
        carpeta = cuenta.resolver_carpeta(self.definicion.carpeta)
        correos = self.motor.cliente().listar(carpeta, horas=self.definicion.horas)
        mostrar_correos(self.consola, correos, self._titulo(carpeta))
        return 0


class AccionConIA(AccionBase):
    """Base de las acciones que piden un resumen a la IA (resumen-ia y exportar)."""

    def _resumir(self, carpeta: str, correos: list, horas: int) -> str | None:
        """Lee el texto de los correos y pide el resumen a la IA.

        Devuelve ``None`` (tras explicar por qué) si no hay IA o no responde:
        la acción sigue y el usuario al menos ve la tabla.
        """
        proveedor = ProveedorIA.desde_entorno(self.config)
        try:
            proveedor.comprobar()  # sin IA no merece la pena descargar los cuerpos
            textos = self._leer_textos(carpeta, correos)
            with self.consola.status(f"La IA está resumiendo {len(correos)} correos…"):
                return proveedor.resumir(correos, horas, textos)
        except SinRedError as exc:
            self.consola.print(f"[yellow]Sin IA: {escape(str(exc))}[/yellow]")
            return None

    def _leer_textos(self, carpeta: str, correos: list) -> dict[str, str]:
        """Descarga el cuerpo de los correos más relevantes (importantes y recientes primero).

        Si uno falla se resume solo con su asunto: un correo raro no tumba el resumen.
        """
        # sorted es estable: primero por fecha y luego por importancia deja
        # los importantes delante, cada grupo del más nuevo al más viejo.
        elegidos = sorted(correos, key=_clave_fecha, reverse=True)
        elegidos = sorted(elegidos, key=lambda c: not c.importante)[:MAX_CORREOS_CON_TEXTO]
        textos: dict[str, str] = {}
        cliente = self.motor.cliente()
        with self.consola.status(f"Leyendo {len(elegidos)} correos…") as estado:
            for numero, correo in enumerate(elegidos, start=1):
                estado.update(f"Leyendo correos… {numero}/{len(elegidos)}")
                try:
                    textos[correo.uid] = cliente.leer_texto(carpeta, correo.uid)
                except BuzonError:
                    continue
        return textos


# Cuántos cuerpos se descargan para el resumen; el resto entra solo con remitente y asunto.
MAX_CORREOS_CON_TEXTO = 30


class AccionResumenIA(AccionConIA):
    """Enseña los correos de la ventana y pide a la IA un resumen de su contenido."""

    def ejecutar(self, simular: bool = False, si: bool = False) -> int:
        cuenta = self.config.cuenta
        horas = self.definicion.horas or 24
        carpeta = cuenta.resolver_carpeta(self.definicion.carpeta)
        correos = self.motor.cliente().listar(carpeta, horas=horas)

        if not correos:
            self.consola.print(f"[green]No hay correos en «{carpeta}» en las últimas {horas} h.[/green]")
            return 0

        correos.sort(key=_clave_fecha, reverse=True)
        mostrar_correos(self.consola, correos, f"Últimas {horas} h · {len(correos)} correos")

        resumen = self._resumir(carpeta, correos, horas)
        if resumen is not None:
            self.consola.print(Panel(Markdown(resumen), title="Resumen con IA", border_style="cyan"))
        return 0


class AccionMoverPapelera(AccionBase):
    """Mueve todos los mensajes de una carpeta a la papelera de Gmail."""

    def ejecutar(self, simular: bool = False, si: bool = False) -> int:
        cuenta = self.config.cuenta
        carpeta = cuenta.resolver_carpeta(self.definicion.carpeta)
        correos = self.motor.cliente().listar(carpeta, horas=None)

        if not correos:
            self.consola.print(f"[green]No hay mensajes en «{carpeta}».[/green]")
            return 0

        self.consola.print(
            f"Se van a mover [bold]{len(correos)}[/bold] mensajes de «{escape(carpeta)}» "
            f"a «{escape(cuenta.carpeta_papelera)}»."
        )

        if simular:
            mostrar_correos(self.consola, correos, "Se moverían estos mensajes", LIMITE_FILAS)
            self.consola.print("[yellow]Simulación: no se ha movido nada.[/yellow]")
            return 0

        if self.definicion.confirmar and not si:
            if not typer.confirm(
                "¿Eliminar TODA la bandeja de spam? (se moverá a la papelera)",
                default=False,
            ):
                self.consola.print("Cancelado. No se ha borrado nada.")
                return 0

        movidos = self.motor.cliente().mover_a_papelera(
            carpeta, [correo.uid for correo in correos], cuenta.carpeta_papelera
        )
        self.consola.print(
            f"[green]OK: {movidos} mensajes movidos a «{escape(cuenta.carpeta_papelera)}».[/green]"
        )
        if movidos < len(correos):
            self.consola.print(
                f"[yellow]Aviso: {len(correos) - movidos} mensajes no se pudieron mover.[/yellow]"
            )
            return 1
        return 0


LINEAS_CUERPO = 60
MAX_VER = 5
PATRON_TROZO = re.compile(r"(\d+)(?:-(\d+))?", re.ASCII)
PATRON_ORDEN = re.compile(r"([a-z?]+)\s*(.*)", re.IGNORECASE | re.DOTALL)

AYUDA_REVISAR = (
    "[bold]v N[/bold] ver correo · [bold]b 1,3,5-7[/bold] borrar · "
    "[bold]b *[/bold] borrar todos · [bold]l[/bold] listar · [bold]q[/bold] salir"
)


def parsear_seleccion(texto: str, total: int) -> list[int]:
    """Convierte ``"1,3,5-7"`` (o ``"*"``) en índices 0-based ordenados y sin repetir.

    Lanza :class:`AccionNoValida` con un mensaje claro si algo no cuadra.
    """
    texto = texto.strip()
    if not texto:
        raise AccionNoValida("Indica qué números: por ejemplo «b 2» o «b 1,3,5-7».")
    if texto == "*":
        return list(range(total))

    elegidos: set[int] = set()
    texto = re.sub(r"\s*-\s*", "-", texto)
    for trozo in texto.replace(" ", ",").split(","):
        if not trozo:
            continue
        coincidencia = PATRON_TROZO.fullmatch(trozo)
        if not coincidencia:
            raise AccionNoValida(f"«{trozo}» no es un número ni un rango (usa 3 o 2-5).")
        desde = int(coincidencia.group(1))
        hasta = int(coincidencia.group(2) or desde)
        if desde > hasta:
            desde, hasta = hasta, desde
        if desde < 1 or hasta > total:
            raise AccionNoValida(f"«{trozo}» está fuera de la lista (1-{total}).")
        elegidos.update(range(desde - 1, hasta))
    if not elegidos:
        raise AccionNoValida("No has indicado ningún número.")
    return sorted(elegidos)


class AccionRevisar(AccionBase):
    """Lista los correos recientes numerados y deja verlos y borrarlos uno a uno."""

    def ejecutar(self, simular: bool = False, si: bool = False) -> int:
        cuenta = self.config.cuenta
        horas = self.definicion.horas
        carpeta = cuenta.resolver_carpeta(self.definicion.carpeta)
        correos = self.motor.cliente().listar(carpeta, horas=horas)
        correos.sort(key=_clave_fecha, reverse=True)
        titulo = self._titulo(carpeta)

        if not correos:
            self.consola.print(f"[green]No hay correos en «{escape(titulo)}».[/green]")
            return 0

        mostrar_correos(self.consola, correos, titulo, len(correos), numerar=True)
        if simular:
            self.consola.print("[yellow]Simulación: lo que borres no se moverá a la papelera.[/yellow]")
        self.consola.print(AYUDA_REVISAR)

        codigo = 0
        while correos:
            orden = typer.prompt("buzon", default="", show_default=False).strip()
            if not orden:
                continue
            coincidencia = PATRON_ORDEN.fullmatch(orden)
            verbo, resto = (coincidencia.group(1).lower(), coincidencia.group(2)) if coincidencia else (orden, "")

            if verbo in {"q", "salir", "exit"}:
                break
            if verbo in {"l", "listar"}:
                mostrar_correos(self.consola, correos, titulo, len(correos), numerar=True)
                continue
            if verbo in {"?", "h", "ayuda"}:
                self.consola.print(AYUDA_REVISAR)
                continue
            if verbo not in {"v", "ver", "b", "borrar"}:
                self.consola.print(f"[yellow]No entiendo «{escape(orden)}».[/yellow] {AYUDA_REVISAR}")
                continue

            try:
                indices = parsear_seleccion(resto, len(correos))
                if verbo in {"v", "ver"}:
                    if len(indices) > MAX_VER:
                        raise AccionNoValida(f"Puedes ver como mucho {MAX_VER} correos a la vez.")
                    for indice in indices:
                        self._ver(carpeta, indice + 1, correos[indice])
                    continue
                elegidos = [correos[indice] for indice in indices]
                borrados = self._borrar(carpeta, elegidos, simular, si)
                if borrados is None:  # cancelado o simulación
                    continue
                # Primero se quitan los que sí se movieron, aunque alguno fallara.
                correos = [c for c in correos if c.uid not in borrados]
                if correos:
                    mostrar_correos(self.consola, correos, titulo, len(correos), numerar=True)
                if len(borrados) < len(elegidos):
                    raise BuzonError(f"{len(elegidos) - len(borrados)} correo(s) no se pudieron mover.")
            except AccionNoValida as exc:
                self.consola.print(f"[yellow]{escape(str(exc))}[/yellow]")
            except BuzonError as exc:
                self.consola.print(f"[red]Error:[/red] {escape(str(exc))}")
                codigo = 1

        if not correos:
            self.consola.print("[green]No quedan correos en la lista.[/green]")
        return codigo

    def _ver(self, carpeta: str, numero: int, correo) -> None:
        texto = self.motor.cliente().leer_texto(carpeta, correo.uid)
        lineas = texto.splitlines()
        if len(lineas) > LINEAS_CUERPO:
            lineas = lineas[:LINEAS_CUERPO] + [f"… ({len(texto.splitlines()) - LINEAS_CUERPO} líneas más)"]
        cabecera = (
            f"[bold]De:[/bold] {escape(correo.remitente)}\n"
            f"[bold]Fecha:[/bold] {hora_local(correo)}\n"
            f"[bold]Asunto:[/bold] {escape(correo.asunto)}\n"
        )
        self.consola.print(
            Panel(cabecera + "\n" + escape("\n".join(lineas)), title=f"Correo {numero}", border_style="cyan")
        )

    def _borrar(self, carpeta: str, elegidos: list, simular: bool, si: bool) -> set[str] | None:
        """Devuelve los UID movidos; ``None`` si se canceló o es una simulación."""
        cuenta = self.config.cuenta
        mostrar_correos(self.consola, elegidos, "Se moverán a la papelera", len(elegidos))
        if simular:
            self.consola.print("[yellow]Simulación: no se ha movido nada.[/yellow]")
            return None
        if not si and not typer.confirm(f"¿Mover {len(elegidos)} correo(s) a la papelera?", default=False):
            self.consola.print("Cancelado. No se ha borrado nada.")
            return None

        movidos = self.motor.cliente().mover_uids_a_papelera(
            carpeta, [correo.uid for correo in elegidos], cuenta.carpeta_papelera
        )
        self.consola.print(f"[green]OK: {len(movidos)} correo(s) movidos a la papelera.[/green]")
        return set(movidos)


def _clave_fecha(correo) -> datetime:
    return correo.fecha or datetime.min.replace(tzinfo=timezone.utc)


class AccionExportar(AccionConIA):
    """Escribe el resumen del día en un fichero Markdown."""

    def ejecutar(self, simular: bool = False, si: bool = False) -> int:
        cuenta = self.config.cuenta
        horas = self.definicion.horas or 24
        carpeta = cuenta.resolver_carpeta(self.definicion.carpeta)
        correos = self.motor.cliente().listar(carpeta, horas=horas)
        correos.sort(key=_clave_fecha, reverse=True)

        resumen = self._resumir(carpeta, correos, horas) if correos else None

        destino = Path(self.definicion.destino).expanduser()
        archivo = destino / f"resumen-{datetime.now():%Y-%m-%d}.md"
        contenido = _markdown(correos, resumen, horas)

        if simular:
            self.consola.print(f"[yellow]Simulación: se escribiría «{escape(str(archivo))}».[/yellow]")
            return 0

        try:
            destino.mkdir(parents=True, exist_ok=True)
            archivo.write_text(contenido, encoding="utf-8")
        except OSError as exc:
            raise BuzonError(f"No se pudo escribir «{archivo}»: {exc.strerror or exc}") from exc

        self.consola.print(f"[green]OK: resumen guardado en «{escape(str(archivo))}».[/green]")
        return 0


def _markdown(correos: list, resumen: str | None, horas: int) -> str:
    lineas = [
        f"# Resumen de correos · {datetime.now():%d/%m/%Y}",
        "",
        f"Ventana: últimas {horas} h · {len(correos)} correos",
        "",
    ]
    if resumen:
        lineas += ["## Resumen con IA", "", resumen, ""]
    lineas += ["## Correos", ""]
    for correo in correos:
        if correo.fecha is not None:
            fecha = correo.fecha.astimezone().strftime("%d/%m/%Y %H:%M")
        else:
            fecha = "fecha desconocida"
        marca = "⭐ " if correo.importante else ""
        lineas.append(
            f"- {marca}**{fecha}** · {nombre_remitente(correo.remitente)} — {correo.asunto}"
        )
    lineas.append("")
    return "\n".join(lineas)


ACCIONES: dict[str, type[AccionBase]] = {
    "listar": AccionListar,
    "resumen-ia": AccionResumenIA,
    "mover-papelera": AccionMoverPapelera,
    "exportar": AccionExportar,
    "revisar": AccionRevisar,
}
