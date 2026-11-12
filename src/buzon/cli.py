"""Interfaz de línea de órdenes (Typer).

La interfaz solo habla con el usuario: lee opciones, llama al motor y
traduce los errores a mensajes y códigos de salida (0, 1, 2, 3).
"""

from __future__ import annotations

import sys
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from . import __version__
from .config import (
    Accion,
    Configuracion,
    buscar_configuracion,
    cargar_configuracion,
    cargar_env,
    carpeta_usuario,
    inicializar,
)
from .errores import BuzonError, ConfigError, SinRedError
from .ia import ProveedorIA
from .motor import Motor
from .salida import LIMITE_FILAS, confirmar, mostrar_correos

app = typer.Typer(
    name="buzon",
    help=(
        "Resume con IA los correos de las últimas 24 h y limpia el spam de Gmail.\n\n"
        "Sin argumentos ejecuta el flujo completo: resumen + lista de spam + confirmación."
    ),
    no_args_is_help=False,
    invoke_without_command=True,
    add_completion=False,
)

def _preparar_salida() -> None:
    """Evita que un carácter raro tumbe la CLI en consolas antiguas.

    En Windows con cp1252 un emoji en un asunto no se puede codificar. Con
    ``errors="replace"`` se muestra un ``?`` en vez de un traceback.
    """
    for flujo in (sys.stdout, sys.stderr):
        reconfigurar = getattr(flujo, "reconfigure", None)
        if callable(reconfigurar):
            try:
                # Si la salida va a una tubería o al chat, Windows usaría cp1252 y las
                # tildes saldrían como «�»: se fuerza UTF-8, que todo lo demás entiende.
                reconfigurar(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


_preparar_salida()

consola = Console()
error = Console(stderr=True)


def _cargar(ruta: Path) -> Configuracion:
    try:
        return cargar_configuracion(ruta)
    except ConfigError as exc:
        error.print(f"[red]Configuración inválida:[/red] {escape(str(exc))}")
        raise typer.Exit(3) from exc


def _sin_teclado(exc: BaseException) -> bool:
    """click convierte en Abort tanto Ctrl+C como el fin de la entrada (EOFError).

    El segundo caso significa que no hay nadie al teclado: salida a una
    tubería, un script o el chat de un agente.
    """
    if isinstance(exc, KeyboardInterrupt):
        return False
    return isinstance(exc.__context__, EOFError) or not sys.stdin.isatty()


@contextmanager
def _errores_controlados(pista_sin_teclado: str = "o añade --si para que no pregunte"):
    """Traduce los errores previsibles a un mensaje y código 1, nunca a un traceback."""
    try:
        yield
    except BuzonError as exc:
        error.print(f"[red]Error:[/red] {escape(str(exc))}")
        raise typer.Exit(1) from exc
    except (KeyboardInterrupt, typer.Abort) as exc:
        if _sin_teclado(exc):
            error.print(
                "\n[yellow]Esta orden necesita que respondas por teclado y aquí no hay teclado "
                "(salida a una tubería, un script o un chat). Ábrela en una terminal "
                f"(PowerShell o Windows Terminal) {pista_sin_teclado}.[/yellow]"
            )
        else:
            error.print("\n[yellow]Interrumpido por el usuario. No se ha borrado nada más.[/yellow]")
        raise typer.Exit(1) from None


def _flujo_por_defecto(config: Configuracion) -> int:
    """Lo que pasa al escribir solo ``buzon``."""
    nombres = {accion.nombre for accion in config.acciones}
    with Motor(config, consola) as motor, _errores_controlados():
        if "resumen-24h" in nombres:
            motor.ejecutar("resumen-24h")
        else:
            consola.print("[yellow]No hay una acción «resumen-24h» en acciones.json.[/yellow]")

        if "listar-spam" not in nombres or "limpiar-spam" not in nombres:
            consola.print(
                "[yellow]Añade «listar-spam» y «limpiar-spam» para completar el flujo.[/yellow]"
            )
            return 0

        accion_spam = config.accion("listar-spam")
        carpeta = config.cuenta.resolver_carpeta(accion_spam.carpeta)
        correos = motor.cliente().listar(carpeta, horas=None)
        if not correos:
            consola.print("[green]La bandeja de spam ya está vacía.[/green]")
            return 0

        consola.print(f"\n[bold]Spam: {len(correos)} mensajes[/bold]")
        mostrar_correos(consola, correos, carpeta, LIMITE_FILAS)
        if confirmar(f"¿Eliminar TODA la bandeja de spam ({len(correos)} mensajes)?"):
            return motor.ejecutar("limpiar-spam", si=True)

        consola.print("No se ha borrado nada.")
        return 0


def _origen(config: Configuracion) -> str:
    cuenta = config.cuenta
    if cuenta.proveedor == "gmail-api":
        return "API de Gmail (HTTPS 443)"
    return f"IMAP {escape(cuenta.servidor)}:{cuenta.puerto}"


@app.callback()
def principal(
    ctx: typer.Context,
    config: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        help=(
            "Ruta al fichero de acciones. Si no se indica: $BUZON_CONFIG, ./acciones.json, "
            "el de tu carpeta de usuario (buzon init) o el del proyecto."
        ),
        show_default=False,
    ),
) -> None:
    """Punto de entrada común: decide qué acciones.json usar y carga el .env de su carpeta."""
    ruta = buscar_configuracion(config)
    cargar_env(ruta.parent / ".env")
    ctx.obj = ruta
    if ctx.invoked_subcommand is None:
        raise typer.Exit(_flujo_por_defecto(_cargar(ruta)))


@app.command()
def version() -> None:
    """Muestra la versión instalada."""
    consola.print(f"buzon {__version__}")


@app.command()
def init(
    carpeta: Path | None = typer.Option(
        None,
        "--carpeta",
        help="Dónde crear la configuración (por defecto, la carpeta de usuario del sistema)",
        show_default=False,
    ),
) -> None:
    """Crea acciones.json y .env en tu carpeta de configuración (no sobrescribe nada)."""
    destino = carpeta.expanduser() if carpeta is not None else carpeta_usuario()
    try:
        ficheros = inicializar(destino)
    except ConfigError as exc:
        error.print(f"[red]Error:[/red] {escape(str(exc))}")
        raise typer.Exit(1) from exc

    for ruta, creado in ficheros:
        if creado:
            consola.print(f"[green]Creado[/green]  {escape(str(ruta))}")
        else:
            consola.print(f"[yellow]Ya existe[/yellow] {escape(str(ruta))} (no se ha tocado)")
    consola.print(
        "\nSiguiente paso: rellena el [bold].env[/bold] con tus credenciales "
        "y comprueba la configuración con [bold]buzon validar[/bold]."
    )


@app.command()
def acciones(ctx: typer.Context) -> None:
    """Lista las acciones definidas en acciones.json."""
    config = _cargar(ctx.obj)
    tabla = Table(title=f"Acciones · {config.ruta.name}", title_justify="left", header_style="bold cyan")
    tabla.add_column("Nombre", style="bold")
    tabla.add_column("Tipo")
    tabla.add_column("Descripción", max_width=70, overflow="fold")
    for accion in config.acciones:
        tabla.add_row(accion.nombre, accion.tipo, escape(accion.descripcion))
    consola.print(tabla)


@app.command()
def validar(ctx: typer.Context) -> None:
    """Comprueba acciones.json y dice exactamente qué campo falla."""
    try:
        config = cargar_configuracion(ctx.obj)
    except ConfigError as exc:
        error.print(f"[red]Configuración inválida:[/red] {escape(str(exc))}")
        raise typer.Exit(3) from exc

    consola.print(
        f"[green]OK[/green] «{escape(config.ruta.name)}» es válido · "
        f"{len(config.acciones)} acciones · {_origen(config)}"
    )
    for accion in config.acciones:
        consola.print(f"  · [bold]{escape(accion.nombre)}[/bold] ({escape(accion.tipo)})")
    for aviso in config.avisos:
        consola.print(f"[yellow]Aviso:[/yellow] {escape(aviso)}")


def _url_sin_secretos(url: str) -> str:
    """Quita usuario, contraseña y parámetros: algunos servicios ponen la clave en la URL."""
    if not url:
        return ""
    partes = urlsplit(url)
    servidor = partes.hostname or ""
    if partes.port:
        servidor += f":{partes.port}"
    oculto = " (parámetros ocultos)" if partes.query or partes.username else ""
    return f"{partes.scheme}://{servidor}{partes.path}{oculto}"


@app.command("comprobar-ia")
def comprobar_ia(ctx: typer.Context) -> None:
    """Dice si la IA está configurada y responde (no muestra la clave)."""
    config = _cargar(ctx.obj)
    nombres = config.ia
    proveedor = ProveedorIA.desde_entorno(config)

    consola.print(
        f"[bold]{nombres.url_env}[/bold]   {escape(_url_sin_secretos(proveedor.url)) or '[red]no definida[/red]'}"
    )
    consola.print(f"[bold]{nombres.modelo_env}[/bold]    {escape(proveedor.modelo)}")
    clave = "[green]definida[/green] (no se muestra)" if proveedor.clave else "[dim]no definida[/dim]"
    consola.print(f"[bold]{nombres.clave_env}[/bold]   {clave}")

    inicio = time.perf_counter()
    try:
        with consola.status("Preguntando al modelo…"):
            respuesta = proveedor.probar()
    except SinRedError as exc:
        error.print(f"[red]La IA no está disponible:[/red] {escape(str(exc))}")
        error.print(
            "[dim]Las acciones sin IA (listar, revisar, limpiar-spam…) siguen funcionando.[/dim]"
        )
        raise typer.Exit(1) from exc

    segundos = time.perf_counter() - inicio
    consola.print(
        f"[green]OK[/green] la IA responde en {segundos:.1f} s: «{escape(respuesta[:60])}»"
    )


@app.command()
def listar(
    ctx: typer.Context,
    carpeta: str = typer.Argument("INBOX", help="Carpeta IMAP o alias: entrada, spam, papelera"),
    horas: int = typer.Option(24, "--horas", min=0, help="Horas hacia atrás; 0 = todo"),
) -> None:
    """Muestra los correos de una carpeta (solo lectura)."""
    config = _cargar(ctx.obj)
    destino = config.cuenta.resolver_carpeta(carpeta)
    ventana = horas if horas > 0 else None

    with Motor(config, consola) as motor, _errores_controlados():
        correos = motor.cliente().listar(destino, horas=ventana)

    titulo = f"{destino} · todo" if ventana is None else f"{destino} · últimas {ventana} h"
    mostrar_correos(consola, correos, titulo)


@app.command()
def revisar(
    ctx: typer.Context,
    carpeta: str = typer.Argument("entrada", help="Carpeta IMAP o alias: entrada, spam, papelera"),
    horas: int = typer.Option(24, "--horas", min=0, help="Horas hacia atrás; 0 = todo"),
    simular: bool = typer.Option(False, "--simular", help="Enseña qué borraría sin tocar nada"),
) -> None:
    """Lista los correos recientes y te deja verlos y borrar los que no te interesen."""
    config = _cargar(ctx.obj)
    definicion = Accion(
        nombre="revisar",
        descripcion="Revisión interactiva",
        tipo="revisar",
        horas=horas if horas > 0 else None,
        carpeta=carpeta,
    )
    # «revisar» no tiene --si: es interactivo por naturaleza.
    with Motor(config, consola) as motor, _errores_controlados("para escribir las órdenes"):
        codigo = motor.ejecutar_definicion(definicion, simular=simular)

    raise typer.Exit(codigo)


@app.command()
def ejecutar(
    ctx: typer.Context,
    nombre: str = typer.Argument(..., help="Nombre de la acción (ver «buzon acciones»)"),
    simular: bool = typer.Option(False, "--simular", help="Enseña qué haría sin tocar nada"),
    si: bool = typer.Option(False, "--si", help="No pide confirmación (para scripts)"),
) -> None:
    """Ejecuta una acción definida en acciones.json."""
    config = _cargar(ctx.obj)
    with Motor(config, consola) as motor, _errores_controlados():
        codigo = motor.ejecutar(nombre, simular=simular, si=si)

    raise typer.Exit(codigo)


if __name__ == "__main__":
    app()
