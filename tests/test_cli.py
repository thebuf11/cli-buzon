import json

from typer.testing import CliRunner

from buzon.cli import app

runner = CliRunner()


def salida_completa(resultado):
    return resultado.output + (getattr(resultado, "stderr", "") or "")


def test_version():
    resultado = runner.invoke(app, ["version"])
    assert resultado.exit_code == 0
    assert "buzon" in resultado.output


def test_validar_correcto(tmp_path):
    ruta = tmp_path / "acciones.json"
    ruta.write_text(
        json.dumps(
            {
                "version": 1,
                "acciones": [
                    {"nombre": "listar-spam", "descripcion": "Spam", "tipo": "listar"}
                ],
            }
        ),
        encoding="utf-8",
    )
    resultado = runner.invoke(app, ["--config", str(ruta), "validar"])
    assert resultado.exit_code == 0
    assert "válido" in resultado.output


def test_validar_incorrecto(tmp_path):
    ruta = tmp_path / "acciones.json"
    ruta.write_text("{ roto", encoding="utf-8")
    resultado = runner.invoke(app, ["--config", str(ruta), "validar"])
    assert resultado.exit_code == 3
    assert "JSON mal formado" in salida_completa(resultado)


def test_config_inexistente(tmp_path):
    resultado = runner.invoke(app, ["--config", str(tmp_path / "no-existe.json"), "acciones"])
    assert resultado.exit_code == 3
    assert "No existe" in salida_completa(resultado)


def test_funciona_desde_cualquier_carpeta(tmp_path, monkeypatch):
    from buzon import config

    monkeypatch.delenv("BUZON_CONFIG", raising=False)
    monkeypatch.setattr(config, "carpeta_usuario", lambda: tmp_path / "usuario")
    monkeypatch.chdir(tmp_path)
    resultado = runner.invoke(app, ["validar"])
    assert resultado.exit_code == 0
    assert "acciones.json" in resultado.output


def test_init_y_validar(tmp_path):
    destino = tmp_path / "config"
    resultado = runner.invoke(app, ["init", "--carpeta", str(destino)])
    assert resultado.exit_code == 0
    assert (destino / "acciones.json").exists()
    assert (destino / ".env").exists()

    resultado = runner.invoke(app, ["--config", str(destino / "acciones.json"), "validar"])
    assert resultado.exit_code == 0


def test_sin_configuracion_sugiere_init(tmp_path, monkeypatch):
    from buzon import config

    monkeypatch.delenv("BUZON_CONFIG", raising=False)
    monkeypatch.setattr(config, "carpeta_usuario", lambda: tmp_path / "usuario")
    monkeypatch.setattr(config, "RAIZ_PROYECTO", tmp_path / "site-packages")
    monkeypatch.chdir(tmp_path)
    resultado = runner.invoke(app, ["acciones"])
    assert resultado.exit_code == 3
    assert "buzon init" in salida_completa(resultado)


def test_validar_errata_sale_con_3_y_sugiere(tmp_path):
    ruta = tmp_path / "acciones.json"
    ruta.write_text(
        json.dumps(
            {
                "version": 1,
                "acciones": [{"nombre": "listar-spam", "descripcion": "Spam", "tipo": "listar", "carpta": "spam"}],
            }
        ),
        encoding="utf-8",
    )
    resultado = runner.invoke(app, ["--config", str(ruta), "validar"])
    assert resultado.exit_code == 3
    # Rich parte las líneas a 80 columnas: se comparan las palabras, no los saltos.
    assert "¿Quisiste decir «carpeta»?" in " ".join(salida_completa(resultado).split())


def test_validar_muestra_avisos_sin_fallar(tmp_path):
    ruta = tmp_path / "acciones.json"
    ruta.write_text(
        json.dumps(
            {
                "version": 1,
                "acciones": [{"nombre": "vaciar-spam", "descripcion": "Vaciar", "tipo": "mover-papelera"}],
            }
        ),
        encoding="utf-8",
    )
    resultado = runner.invoke(app, ["--config", str(ruta), "validar"])
    assert resultado.exit_code == 0
    assert "Aviso" in resultado.output


def test_init_explica_credenciales_y_la_plantilla_usa_imap(tmp_path):
    destino = tmp_path / "config"
    resultado = runner.invoke(app, ["init", "--carpeta", str(destino)])
    texto = " ".join(resultado.output.split())
    assert "GMAIL_APP_PASSWORD" in texto
    assert "credentials.json" in texto
    assert json.loads((destino / "acciones.json").read_text(encoding="utf-8"))["cuenta"]["proveedor"] == "imap"
