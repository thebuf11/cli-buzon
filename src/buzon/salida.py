"""Formato de las tablas en la terminal.

Todo texto que viene de un correo se escapa antes de pasarlo a Rich: un
asunto con ``[bold]`` no debe cambiar el formato de la tabla.
"""

from __future__ import annotations

from email.utils import parseaddr

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from .imap_client import Correo

LIMITE_FILAS = 15


def nombre_remitente(remitente: str) -> str:
    nombre, direccion = parseaddr(remitente)
    return nombre or direccion or remitente


def hora_local(correo: Correo) -> str:
    if correo.fecha is None:
        return "—"
    return correo.fecha.astimezone().strftime("%d/%m %H:%M")


def tabla_correos(
    correos: list[Correo],
    titulo: str,
    limite: int = LIMITE_FILAS,
    numerar: bool = False,
) -> Table:
    tabla = Table(title=titulo, title_justify="left", header_style="bold cyan", expand=False)
    if numerar:
        tabla.add_column("#", style="bold", justify="right", no_wrap=True)
    tabla.add_column("Hora", style="dim", no_wrap=True)
    tabla.add_column("Remitente", max_width=28, overflow="ellipsis")
    tabla.add_column("Asunto", max_width=60, overflow="ellipsis")
    for numero, correo in enumerate(correos[:limite], start=1):
        fila = [
            hora_local(correo),
            escape(nombre_remitente(correo.remitente)),
            ("⭐ " if correo.importante and numerar else "") + escape(correo.asunto),
        ]
        if numerar:
            fila.insert(0, str(numero))
        tabla.add_row(*fila)
    return tabla


def mostrar_correos(
    consola: Console,
    correos: list[Correo],
    titulo: str,
    limite: int = LIMITE_FILAS,
    numerar: bool = False,
) -> None:
    if not correos:
        consola.print("[green]No hay correos que mostrar.[/green]")
        return
    consola.print(tabla_correos(correos, titulo, limite, numerar))
    if len(correos) > limite:
        consola.print(f"[dim]… y {len(correos) - limite} más.[/dim]")
