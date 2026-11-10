"""Limpieza del cuerpo de los correos al mostrarlos con «v N»."""

from buzon.imap_client import extraer_texto


def correo_plano(cuerpo: str) -> bytes:
    cabecera = "From: a@b.c\r\nSubject: Hola\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n"
    return (cabecera + cuerpo).encode("utf-8")


def test_quita_entidades_e_invisibles_de_relleno():
    texto = extraer_texto(correo_plano("&zwnj; &zwnj; &zwnj;‌​\r\nHola &amp; adiós\r\n"))
    assert texto == "Hola & adiós"


def test_quita_etiquetas_sueltas_pero_no_direcciones():
    texto = extraer_texto(
        correo_plano('<span style="color: red;">CUPÓN</span><br> SOLO <b>PARA TI</b>\r\n'
                     "Escribe a Ana <ana@example.com>\r\n")
    )
    assert texto == "CUPÓN SOLO PARA TI\nEscribe a Ana <ana@example.com>"


def test_acorta_enlaces_largos_y_deja_los_cortos():
    largo = "https://click.email.tienda.com/?qs=" + "A" * 120
    texto = extraer_texto(correo_plano(f"Mira {largo} o https://ejemplo.es/oferta\r\n"))
    assert texto == "Mira [enlace: click.email.tienda.com] o https://ejemplo.es/oferta"


def test_enlaces_repetidos_seguidos_se_juntan():
    url = "https://click.email.tienda.com/?qs=" + "B" * 80
    texto = extraer_texto(correo_plano(f"{url}\r\n\r\n{url}\r\n\r\nRunning\r\n\r\n{url}\r\n"))
    assert texto == "[enlace: click.email.tienda.com]\n\nRunning\n\n[enlace: click.email.tienda.com]"
