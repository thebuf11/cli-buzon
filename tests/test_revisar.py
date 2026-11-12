"""Pruebas de la revisión interactiva (sin red ni cuenta real)."""

import io
import json
from datetime import datetime, timezone

import pytest
import typer
from rich.console import Console

from buzon.acciones import parsear_seleccion
from buzon.config import cargar_configuracion
from buzon.errores import AccionNoValida
from buzon.imap_client import Correo, extraer_texto
from buzon.motor import Motor


class ClienteFalso:
    def __init__(self, correos, fallan=()):
        self.correos = correos
        self.movidos = []
        self.leidos = []
        self.fallan = set(fallan)

    def listar(self, carpeta, horas=None, ahora=None):
        return list(self.correos)

    def leer_texto(self, carpeta, uid):
        self.leidos.append(uid)
        return f"Cuerpo del correo {uid}"

    def mover_uids_a_papelera(self, carpeta, uids, papelera):
        ok = [uid for uid in uids if uid not in self.fallan]
        self.movidos.extend(ok)
        return ok

    def cerrar(self):
        pass


def fecha(hora):
    return datetime(2026, 11, 10, hora, tzinfo=timezone.utc)


CORREOS = [
    Correo("10", "Ana <ana@x.es>", "Reunión", fecha(9), importante=True),
    Correo("11", "Tienda <promo@t.com>", "Ofertas", fecha(11)),
    Correo("12", "Boletín <news@n.com>", "Noticias", fecha(10)),
]


def preparar(tmp_path, monkeypatch, ordenes, confirmar=True, fallan=()):
    datos = {
        "version": 1,
        "acciones": [{"nombre": "revisar-24h", "descripcion": "Revisar", "tipo": "revisar"}],
    }
    ruta = tmp_path / "acciones.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    cola = list(ordenes)
    monkeypatch.setattr(typer, "prompt", lambda *a, **k: cola.pop(0))
    monkeypatch.setattr("buzon.acciones.confirmar", lambda *a, **k: confirmar)
    salida = io.StringIO()
    cliente = ClienteFalso(CORREOS, fallan)
    motor = Motor(cargar_configuracion(ruta), Console(file=salida, width=140), cliente=cliente)
    return motor, cliente, salida


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [("2", [1]), ("1,3", [0, 2]), ("3-1", [0, 1, 2]), ("1, 1 2", [0, 1]), ("*", [0, 1, 2]), ("1 - 3", [0, 1, 2])],
)
def test_parsear_seleccion(texto, esperado):
    assert parsear_seleccion(texto, 3) == esperado


@pytest.mark.parametrize("texto", ["", "0", "4", "a", "1-x", "1_0", "²"])
def test_parsear_seleccion_invalida(texto):
    with pytest.raises(AccionNoValida):
        parsear_seleccion(texto, 3)


def test_revisar_ordena_del_mas_nuevo_al_mas_viejo_y_borra_el_elegido(tmp_path, monkeypatch):
    motor, cliente, _ = preparar(tmp_path, monkeypatch, ["b 1", "q"])
    assert motor.ejecutar("revisar-24h") == 0
    # El nº 1 es el más reciente: «Ofertas» (11:00), UID 11.
    assert cliente.movidos == ["11"]


def test_revisar_ver_no_borra(tmp_path, monkeypatch):
    motor, cliente, salida = preparar(tmp_path, monkeypatch, ["v 3", "q"])
    assert motor.ejecutar("revisar-24h") == 0
    assert cliente.leidos == ["10"]
    assert cliente.movidos == []
    assert "Cuerpo del correo 10" in salida.getvalue()


def test_revisar_cancelar_confirmacion_no_borra(tmp_path, monkeypatch):
    motor, cliente, _ = preparar(tmp_path, monkeypatch, ["b *", "q"], confirmar=False)
    assert motor.ejecutar("revisar-24h") == 0
    assert cliente.movidos == []


def test_revisar_simular_no_borra(tmp_path, monkeypatch):
    motor, cliente, salida = preparar(tmp_path, monkeypatch, ["b 1-2", "q"])
    assert motor.ejecutar("revisar-24h", simular=True) == 0
    assert cliente.movidos == []
    assert "Simulación" in salida.getvalue()


def test_revisar_numeros_se_recalculan_tras_borrar(tmp_path, monkeypatch):
    # Tras borrar el nº 1 (UID 11), el nuevo nº 1 es «Noticias» (UID 12).
    motor, cliente, _ = preparar(tmp_path, monkeypatch, ["b 1", "b 1", "q"])
    motor.ejecutar("revisar-24h")
    assert cliente.movidos == ["11", "12"]


def test_revisar_orden_erronea_no_revienta(tmp_path, monkeypatch):
    motor, cliente, salida = preparar(tmp_path, monkeypatch, ["borrar 9", "xyz", "", "q"])
    assert motor.ejecutar("revisar-24h") == 0
    assert cliente.movidos == []
    assert "fuera de la lista" in salida.getvalue()


def test_revisar_sale_sola_al_vaciar_la_lista(tmp_path, monkeypatch):
    motor, cliente, salida = preparar(tmp_path, monkeypatch, ["b *"])
    assert motor.ejecutar("revisar-24h") == 0
    assert sorted(cliente.movidos) == ["10", "11", "12"]
    assert "No quedan correos" in salida.getvalue()


def test_extraer_texto_plano():
    crudo = (
        b"From: a@b.c\r\nSubject: Hola\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n"
        b"L\xc3\xadnea 1\r\n\r\n\r\n\r\nL\xc3\xadnea 2\r\n"
    )
    assert extraer_texto(crudo) == "Línea 1\n\nLínea 2"


def test_extraer_texto_html_quita_etiquetas_y_estilos():
    crudo = (
        b"From: a@b.c\r\nContent-Type: text/html; charset=utf-8\r\n\r\n"
        b"<html><head><style>p{color:red}</style></head><body>"
        b"<p>Hola &amp; adi\xc3\xb3s</p><script>alert(1)</script><div>Fin</div></body></html>"
    )
    assert extraer_texto(crudo) == "Hola & adiós\n\nFin"


class ConexionLista:
    def __init__(self, lineas):
        self.lineas = lineas

    def list(self):
        return "OK", self.lineas


@pytest.mark.parametrize(
    ("lineas", "esperado"),
    [
        (
            [
                rb'(\HasNoChildren) "/" "INBOX"',
                rb'(\HasNoChildren \Junk) "/" "[Gmail]/Spam"',
                rb'(\HasNoChildren \Trash) "/" "[Gmail]/Papelera"',
            ],
            "[Gmail]/Papelera",
        ),
        ([rb'(\HasNoChildren) "/" "INBOX"'], None),
    ],
)
def test_buscar_papelera_por_atributo(lineas, esperado):
    from buzon.imap_client import ClienteIMAP

    cliente = ClienteIMAP("x", 993, "u", "p")
    cliente._conexion = ConexionLista(lineas)
    assert cliente.buscar_papelera() == esperado


def test_revisar_acepta_orden_sin_espacio(tmp_path, monkeypatch):
    motor, cliente, _ = preparar(tmp_path, monkeypatch, ["b1", "q"])
    motor.ejecutar("revisar-24h")
    assert cliente.movidos == ["11"]


def test_revisar_limita_cuantos_se_ven(tmp_path, monkeypatch):
    motor, cliente, salida = preparar(tmp_path, monkeypatch, ["v *", "q"])
    monkeypatch.setattr("buzon.acciones.MAX_VER", 2)
    motor.ejecutar("revisar-24h")
    assert cliente.leidos == []
    assert "como mucho 2" in salida.getvalue()


def test_revisar_borrado_parcial_quita_solo_los_movidos(tmp_path, monkeypatch):
    # Falla el UID 12; el 11 sí se mueve. Después, «b 1» debe apuntar al 12 (sigue en la lista).
    motor, cliente, salida = preparar(tmp_path, monkeypatch, ["b 1-2", "b 1", "q"], fallan={"12"})
    assert motor.ejecutar("revisar-24h") == 1
    assert cliente.movidos == ["11"]
    assert "no se pudieron mover" in salida.getvalue()


def test_texto_de_correo_sin_secuencias_de_terminal():
    from buzon.imap_client import _parsear_correo

    crudo = (
        b"From: a@b.c\r\nSubject: Hola\x1b]0;pwn\x07\r\nContent-Type: text/plain\r\n\r\n"
        b"Texto\x1b[31m rojo\r\n"
    )
    assert "\x1b" not in extraer_texto(crudo)
    assert "\x1b" not in _parsear_correo("1", b"", crudo).asunto
