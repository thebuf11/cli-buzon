import copy
import json

import pytest

from buzon.config import cargar_configuracion
from buzon.errores import AccionNoValida, ConfigError

ACCIONES = [
    {"nombre": "resumen-24h", "descripcion": "Resumen", "tipo": "resumen-ia"},
    {"nombre": "listar-spam", "descripcion": "Spam", "tipo": "listar", "carpeta": "spam"},
    {
        "nombre": "limpiar-spam",
        "descripcion": "Limpiar",
        "tipo": "mover-papelera",
        "carpeta": "spam",
        "confirmar": True,
    },
    {"nombre": "guardar", "descripcion": "Guardar", "tipo": "exportar", "destino": "~/resumenes"},
]


def escribir(tmp_path, datos):
    ruta = tmp_path / "acciones.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    return ruta


def base():
    # Copia profunda: cada test modifica su propio JSON sin contaminar los demás.
    return {"version": 1, "acciones": copy.deepcopy(ACCIONES)}


def test_carga_valida(tmp_path):
    config = cargar_configuracion(escribir(tmp_path, base()))
    assert len(config.acciones) == 4
    assert config.cuenta.servidor == "imap.gmail.com"
    assert config.accion("resumen-24h").horas == 24
    assert config.accion("listar-spam").horas is None


def test_resolver_alias_de_carpetas(tmp_path):
    config = cargar_configuracion(escribir(tmp_path, base()))
    assert config.cuenta.resolver_carpeta("spam") == "[Gmail]/Spam"
    assert config.cuenta.resolver_carpeta("papelera") == "[Gmail]/Trash"
    assert config.cuenta.resolver_carpeta("INBOX") == "INBOX"


def test_json_mal_formado(tmp_path):
    ruta = tmp_path / "acciones.json"
    ruta.write_text("{ no es json", encoding="utf-8")
    with pytest.raises(ConfigError, match="JSON mal formado"):
        cargar_configuracion(ruta)


def test_version_incorrecta(tmp_path):
    datos = base()
    datos["version"] = 2
    with pytest.raises(ConfigError, match="version"):
        cargar_configuracion(escribir(tmp_path, datos))


def test_accion_sin_descripcion(tmp_path):
    datos = base()
    del datos["acciones"][0]["descripcion"]
    with pytest.raises(ConfigError, match=r"acciones\[0\]\.descripcion"):
        cargar_configuracion(escribir(tmp_path, datos))


def test_tipo_invalido(tmp_path):
    datos = base()
    datos["acciones"][0]["tipo"] = "magia"
    with pytest.raises(ConfigError, match="tipo"):
        cargar_configuracion(escribir(tmp_path, datos))


def test_nombre_repetido(tmp_path):
    datos = base()
    datos["acciones"][1]["nombre"] = "resumen-24h"
    with pytest.raises(ConfigError, match="repetido"):
        cargar_configuracion(escribir(tmp_path, datos))


def test_exportar_sin_destino(tmp_path):
    datos = base()
    del datos["acciones"][3]["destino"]
    with pytest.raises(ConfigError, match="destino"):
        cargar_configuracion(escribir(tmp_path, datos))


def test_accion_inexistente(tmp_path):
    config = cargar_configuracion(escribir(tmp_path, base()))
    with pytest.raises(AccionNoValida, match="noexiste"):
        config.accion("noexiste")


def test_proveedor_por_defecto_es_imap(tmp_path):
    config = cargar_configuracion(escribir(tmp_path, base()))
    assert config.cuenta.proveedor == "imap"
    assert config.cuenta.credenciales_api == "credentials.json"
    assert config.cuenta.token_api == "token.json"


def test_proveedor_gmail_api(tmp_path):
    datos = base()
    datos["cuenta"] = {"proveedor": "gmail-api", "token_api": "mi-token.json"}
    config = cargar_configuracion(escribir(tmp_path, datos))
    assert config.cuenta.proveedor == "gmail-api"
    assert config.cuenta.token_api == "mi-token.json"


def test_proveedor_invalido(tmp_path):
    datos = base()
    datos["cuenta"] = {"proveedor": "pop3"}
    with pytest.raises(ConfigError, match="cuenta.proveedor"):
        cargar_configuracion(escribir(tmp_path, datos))


def test_buscar_configuracion_desde_otra_carpeta(tmp_path, monkeypatch):
    from buzon import config
    from buzon.config import RAIZ_PROYECTO, buscar_configuracion

    monkeypatch.delenv("BUZON_CONFIG", raising=False)
    monkeypatch.setattr(config, "carpeta_usuario", lambda: tmp_path / "usuario")
    monkeypatch.chdir(tmp_path)  # carpeta sin acciones.json
    assert buscar_configuracion() == RAIZ_PROYECTO / "acciones.json"


def test_buscar_configuracion_prefiere_carpeta_usuario(tmp_path, monkeypatch):
    from buzon import config
    from buzon.config import buscar_configuracion

    usuario = tmp_path / "usuario"
    usuario.mkdir()
    (usuario / "acciones.json").write_text("{}", encoding="utf-8")
    monkeypatch.delenv("BUZON_CONFIG", raising=False)
    monkeypatch.setattr(config, "carpeta_usuario", lambda: usuario)
    monkeypatch.chdir(tmp_path)
    assert buscar_configuracion() == usuario / "acciones.json"


def test_instalado_sin_proyecto_apunta_a_carpeta_usuario(tmp_path, monkeypatch):
    # Instalado con «uv tool install git+…»: RAIZ_PROYECTO cae en site-packages.
    from buzon import config
    from buzon.config import buscar_configuracion

    monkeypatch.delenv("BUZON_CONFIG", raising=False)
    monkeypatch.setattr(config, "carpeta_usuario", lambda: tmp_path / "usuario")
    monkeypatch.setattr(config, "RAIZ_PROYECTO", tmp_path / "site-packages")
    monkeypatch.chdir(tmp_path)
    assert buscar_configuracion() == tmp_path / "usuario" / "acciones.json"


def test_inicializar_crea_y_no_sobrescribe(tmp_path):
    from buzon.config import inicializar

    destino = tmp_path / "buzon"
    primera = inicializar(destino)
    assert [(ruta.name, creado) for ruta, creado in primera] == [
        ("acciones.json", True),
        (".env", True),
    ]
    # La plantilla es un acciones.json válido de verdad.
    assert len(cargar_configuracion(destino / "acciones.json").acciones) >= 3

    (destino / ".env").write_text("GMAIL_USUARIO=yo@ejemplo.com\n", encoding="utf-8")
    segunda = inicializar(destino)
    assert all(not creado for _, creado in segunda)
    assert "yo@ejemplo.com" in (destino / ".env").read_text(encoding="utf-8")


def test_buscar_configuracion_prioridades(tmp_path, monkeypatch):
    from buzon.config import buscar_configuracion

    monkeypatch.chdir(tmp_path)
    (tmp_path / "acciones.json").write_text("{}", encoding="utf-8")
    monkeypatch.delenv("BUZON_CONFIG", raising=False)
    assert buscar_configuracion() == tmp_path.joinpath("acciones.json").relative_to(tmp_path)

    monkeypatch.setenv("BUZON_CONFIG", str(tmp_path / "otra.json"))
    assert buscar_configuracion() == tmp_path / "otra.json"
    assert buscar_configuracion(tmp_path / "explicita.json") == tmp_path / "explicita.json"


# ── campos desconocidos y campos que el tipo no usa ───────────


def test_errata_en_un_campo_sugiere_el_correcto(tmp_path):
    datos = base()
    datos["acciones"][0]["hroas"] = 12
    with pytest.raises(ConfigError, match=r"acciones\[0\]\.hroas: campo desconocido\. ¿Quisiste decir «horas»\?"):
        cargar_configuracion(escribir(tmp_path, datos))


def test_errata_en_tipo_se_detecta_antes_que_el_tipo_vacio(tmp_path):
    datos = base()
    datos["acciones"][1]["tpo"] = datos["acciones"][1].pop("tipo")
    with pytest.raises(ConfigError, match="¿Quisiste decir «tipo»"):
        cargar_configuracion(escribir(tmp_path, datos))


def test_horas_en_mover_papelera_se_rechaza(tmp_path):
    # Haría creer que solo se borran las últimas horas, y se borra toda la carpeta.
    datos = base()
    datos["acciones"][2]["horas"] = 24
    with pytest.raises(ConfigError, match=r"acciones\[2\]\.horas: las acciones de tipo «mover-papelera» no usan"):
        cargar_configuracion(escribir(tmp_path, datos))


def test_destino_fuera_de_exportar_se_rechaza(tmp_path):
    datos = base()
    datos["acciones"][1]["destino"] = "~/spam"
    with pytest.raises(ConfigError, match=r"acciones\[1\]\.destino"):
        cargar_configuracion(escribir(tmp_path, datos))


@pytest.mark.parametrize(
    ("seccion", "clave", "sugerencia"),
    [("cuenta", "pueto", "puerto"), ("ia", "url", "url_env")],
)
def test_errata_en_cuenta_e_ia(tmp_path, seccion, clave, sugerencia):
    datos = base()
    datos[seccion] = {clave: "x"}
    with pytest.raises(ConfigError, match=rf"{seccion}\.{clave}: campo desconocido\. ¿Quisiste decir «{sugerencia}»"):
        cargar_configuracion(escribir(tmp_path, datos))


def test_campo_desconocido_en_la_raiz(tmp_path):
    datos = base()
    datos["acione"] = []
    with pytest.raises(ConfigError, match=r"^acione: campo desconocido\. ¿Quisiste decir «acciones»"):
        cargar_configuracion(escribir(tmp_path, datos))


def test_claves_con_guion_bajo_son_comentarios(tmp_path):
    datos = base()
    datos["_nota"] = "JSON no tiene comentarios"
    datos["acciones"][0]["_uso"] = "lo lanzo cada mañana"
    assert len(cargar_configuracion(escribir(tmp_path, datos)).acciones) == 4


def test_mover_papelera_sin_confirmar_da_aviso(tmp_path):
    datos = base()
    assert cargar_configuracion(escribir(tmp_path, datos)).avisos == ()
    datos["acciones"][2]["confirmar"] = False
    avisos = cargar_configuracion(escribir(tmp_path, datos)).avisos
    assert len(avisos) == 1
    assert "limpiar-spam" in avisos[0]


def test_errata_en_version_sugiere_el_nombre(tmp_path):
    # Antes: «version: se esperaba 1, se encontró None».
    datos = base()
    datos["versoin"] = datos.pop("version")
    with pytest.raises(ConfigError, match="¿Quisiste decir «version»"):
        cargar_configuracion(escribir(tmp_path, datos))


def test_clave_repetida_es_un_error(tmp_path):
    # json se quedaría con el último «tipo» y una acción de lectura pasaría a borrar.
    ruta = tmp_path / "acciones.json"
    ruta.write_text(
        '{"version": 1, "acciones": [{"nombre": "x", "descripcion": "X", '
        '"tipo": "listar", "tipo": "mover-papelera"}]}',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="«tipo» aparece dos veces"):
        cargar_configuracion(ruta)
