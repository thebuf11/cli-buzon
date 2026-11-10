from datetime import datetime, timedelta, timezone
from pathlib import Path

from buzon.imap_client import (
    Correo,
    _etiquetas,
    _parsear_correo,
    _parsear_fecha,
    filtrar_por_horas,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_fecha_con_zona_horaria():
    fecha = _parsear_fecha("Mon, 09 Nov 2026 10:00:00 +0100")
    assert fecha == datetime(2026, 11, 9, 9, 0, tzinfo=timezone.utc)


def test_fecha_rota_devuelve_none():
    assert _parsear_fecha("no es una fecha") is None
    assert _parsear_fecha(None) is None


def test_etiquetas_de_gmail():
    meta = (
        b'1 (X-GM-LABELS ("\\Inbox" "\\Important" "Trabajo") '
        b"BODY[HEADER.FIELDS (FROM SUBJECT DATE)] {42}"
    )
    assert _etiquetas(meta) == {"\\Inbox", "\\Important", "Trabajo"}


def test_correo_con_tildes_y_marcado_importante():
    cuerpo = (FIXTURES / "correo.eml").read_bytes()
    meta = (
        b'7 (X-GM-LABELS ("\\Inbox" "\\Important") '
        b"BODY[HEADER.FIELDS (FROM SUBJECT DATE)] {10}"
    )
    correo = _parsear_correo("7", meta, cuerpo)
    assert correo.asunto == "Reunión de tutores"
    assert correo.importante is True
    assert "Ana Torres" in correo.remitente


def test_correo_sin_etiquetas_no_es_importante():
    correo = _parsear_correo(
        "8",
        b"8 (BODY[HEADER.FIELDS (FROM SUBJECT DATE)] {10}",
        b"From: a@b.c\r\nSubject: Hola\r\n\r\n",
    )
    assert correo.importante is False
    assert correo.asunto == "Hola"


def test_filtro_de_24_horas():
    ahora = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)
    reciente = Correo("1", "Ana", "Hoy", ahora - timedelta(hours=2))
    viejo = Correo("2", "Ana", "Ayer", ahora - timedelta(hours=30))
    assert filtrar_por_horas([reciente, viejo], 24, ahora) == [reciente]


def test_correo_sin_fecha_se_conserva():
    ahora = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)
    sin_fecha = Correo("3", "Ana", "Sin fecha", None)
    assert filtrar_por_horas([sin_fecha], 24, ahora) == [sin_fecha]
