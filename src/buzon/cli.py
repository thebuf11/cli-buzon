"""Interfaz de línea de órdenes (Typer).

La interfaz solo habla con el usuario: lee opciones, llama al motor y
traduce los errores a mensajes y códigos de salida (0 bien, 1 fallo,
2 uso, 3 configuración, 4 sin IA en ``comprobar-ia``).
"""

from __future__ import annotations

import os
import sys
import time
from contextlib import contextmanager
from dataclasses import replace
from importlib.resources import files
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
from .errores import BuzonError, ConfigError, IANoDisponible, SinRedError
from .ia import ProveedorCentro
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


# click comparte ctx.meta entre todas las órdenes: la clave lleva el nombre del paquete.
CLAVE_DEMO = "buzon.demo"
# Si el usuario nombró un acciones.json (--config o BUZON_CONFIG), que no exista es un error.
CLAVE_CONFIG_EXPLICITA = "buzon.config_explicita"


def _demo_por_entorno() -> bool:
    """``BUZON_DEMO=1`` equivale a ``--demo`` (útil para no repetirlo en cada orden)."""
    return os.environ.get("BUZON_DEMO", "").strip().lower() in {"1", "si", "sí", "true", "yes"}


def _leer(ctx: typer.Context) -> Configuracion:
    """Lee acciones.json; con --demo cambia el buzón por los correos de ejemplo."""
    ruta = Path(ctx.obj)
    if ctx.meta.get(CLAVE_DEMO) and not ctx.meta.get(CLAVE_CONFIG_EXPLICITA) and not ruta.exists():
        # Recién instalado y sin «buzon init»: para probar basta con las acciones de ejemplo.
        ruta = Path(str(files("buzon") / "plantillas" / "acciones.json"))
        consola.print("[dim]Sin acciones.json: se usan las acciones de ejemplo (buzon init para crear las tuyas).[/dim]")
    config = cargar_configuracion(ruta)
    if ctx.meta.get(CLAVE_DEMO):
        config = replace(config, cuenta=replace(config.cuenta, proveedor="demo"))
    return config


def _cargar(ctx: typer.Context) -> Configuracion:
    try:
        return _leer(ctx)
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
    if isinstance(exc.__context__, EOFError):
        return True
    # sys.stdin puede ser None (pythonw) y, en Windows, NUL dice ser una terminal.
    es_terminal = getattr(sys.stdin, "isatty", None)
    return not (callable(es_terminal) and es_terminal())


PISTA_EJECUTAR = "o añade --si para que no pregunte"
PISTA_FLUJO = "o, para scripts, usa «buzon ejecutar limpiar-spam --si»"


@contextmanager
def _errores_controlados(pista_sin_teclado: str = PISTA_EJECUTAR):
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
    # «buzon» a secas no tiene --si: la pista lleva a la orden que sí lo tiene.
    with Motor(config, consola) as motor, _errores_controlados(PISTA_FLUJO):
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
    if cuenta.proveedor == "demo":
        return "modo demo (correos de ejemplo, sin Gmail)"
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
    demo: bool = typer.Option(
        False,
        "--demo",
        help=(
            "Usa correos de ejemplo en vez de tu Gmail: no hace falta cuenta y no se borra nada "
            "real. También con BUZON_DEMO=1."
        ),
    ),
) -> None:
    """Punto de entrada común: decide qué acciones.json usar y carga el .env de su carpeta."""
    ruta = buscar_configuracion(config)
    cargar_env(ruta.parent / ".env")
    ctx.obj = ruta
    ctx.meta[CLAVE_DEMO] = demo or _demo_por_entorno()
    ctx.meta[CLAVE_CONFIG_EXPLICITA] = config is not None or bool(os.environ.get("BUZON_CONFIG", "").strip())
    if ctx.invoked_subcommand is None:
        raise typer.Exit(_flujo_por_defecto(_cargar(ctx)))


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
        "\n[bold]Siguientes pasos[/bold]\n"
        "0. ¿Solo quieres probarla? [bold]buzon --demo[/bold] usa correos de ejemplo, sin Gmail.\n"
        f"1. Rellena {escape(str(destino / '.env'))}: GMAIL_USUARIO y GMAIL_APP_PASSWORD "
        "(contraseña de aplicación de Gmail) y, para la IA del centro, CENTRO_IA_URL, "
        "CENTRO_IA_KEY y CENTRO_IA_CA.\n"
        "2. Comprueba la configuración: [bold]buzon validar[/bold] y [bold]buzon comprobar-ia[/bold].\n"
        "Si tu red bloquea IMAP (puerto 993), pon \"proveedor\": \"gmail-api\" en acciones.json "
        f"y guarda el credentials.json de Google Cloud en {escape(str(destino))} (ver README)."
    )


@app.command()
def acciones(ctx: typer.Context) -> None:
    """Lista las acciones definidas en acciones.json."""
    config = _cargar(ctx)
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
        config = _leer(ctx)
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


URL_NO_VALIDA = "(URL no válida: debe empezar por http:// o https://)"


def _url_sin_secretos(url: str) -> str:
    """Enseña de la URL solo esquema, servidor, puerto y el último tramo de la ruta.

    Algunos servicios meten la clave en el usuario/contraseña, en los
    parámetros o en la propia ruta (``/v1/CLAVE/chat``). Ante cualquier cosa
    rara (sin esquema, puerto que no es un número) no se enseña nada de ella.
    """
    if not url:
        return ""
    try:
        partes = urlsplit(url.strip())
        puerto = partes.port  # lanza ValueError con «:abc» o «:99999»
    except ValueError:
        return URL_NO_VALIDA
    if partes.scheme not in {"http", "https"} or not partes.hostname:
        return URL_NO_VALIDA

    servidor = partes.hostname + (f":{puerto}" if puerto else "")
    tramos = [tramo for tramo in partes.path.split("/") if tramo]
    ruta = f"/…/{tramos[-1]}" if len(tramos) > 1 else partes.path
    oculto = " (credenciales o parámetros ocultos)" if partes.query or partes.username or partes.password else ""
    return f"{partes.scheme}://{servidor}{ruta}{oculto}"


@app.command("comprobar-ia")
def comprobar_ia(ctx: typer.Context) -> None:
    """Dice si la IA está configurada y responde (no muestra la clave)."""
    config = _cargar(ctx)
    nombres = config.ia
    proveedor = ProveedorCentro.desde_entorno(config)

    ancho = max(len(n) for n in (nombres.url_env, nombres.modelo_env, nombres.clave_env, nombres.ca_env))

    def fila(nombre: str, valor: str) -> None:
        consola.print(f"[bold]{nombre.ljust(ancho)}[/bold]  {valor}")

    fila(nombres.url_env, escape(_url_sin_secretos(proveedor.url)) or "[red]no definida[/red]")
    fila(nombres.modelo_env, escape(proveedor.modelo))
    fila(nombres.clave_env, "[green]definida[/green] (no se muestra)" if proveedor.clave_definida else "[dim]no definida[/dim]")
    ruta_ca = proveedor.ruta_ca
    if ruta_ca is None:
        fila(nombres.ca_env, "[dim]no definido (se usan los certificados del sistema)[/dim]")
    elif ruta_ca.is_file():
        fila(nombres.ca_env, f"[green]{escape(ruta_ca.name)}[/green] (existe)")
    else:
        fila(nombres.ca_env, f"[red]{escape(str(ruta_ca))} no existe[/red]")

    for aviso in config.avisos:
        if "«ia»" in aviso:  # p. ej., un acciones.json de la 1.0.0 con IA_API_URL
            consola.print(f"[yellow]Aviso:[/yellow] {escape(aviso)}")

    inicio = time.perf_counter()
    try:
        with consola.status("Preguntando al modelo…"):
            respuesta = proveedor.probar()
    except KeyboardInterrupt:  # la espera puede durar hasta un minuto
        error.print("\n[yellow]Interrumpido por el usuario.[/yellow]")
        raise typer.Exit(1) from None
    except SinRedError as exc:
        # Código 4: «sin IA». Es distinto de 1 para que un script sepa que lo demás sí funciona.
        error.print(f"[red]Error:[/red] La IA no está disponible: {escape(str(exc))}")
        error.print(
            "[dim]Las acciones sin IA (listar, revisar, limpiar-spam…) siguen funcionando.[/dim]"
        )
        raise typer.Exit(IANoDisponible.codigo_salida) from exc

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
    config = _cargar(ctx)
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
    config = _cargar(ctx)
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
    config = _cargar(ctx)
    with Motor(config, consola) as motor, _errores_controlados():
        codigo = motor.ejecutar(nombre, simular=simular, si=si)

    raise typer.Exit(codigo)


if __name__ == "__main__":
    app()
