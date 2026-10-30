"""
Pruebas de app/services/carga_usuarios_service.py (lectura/validación del
Excel) y de la siembra automática del primer arranque
(_sembrar_usuarios_iniciales en app/main.py).
"""

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories import accesos_repo
from app.services.carga_usuarios_service import ErrorCargaUsuarios, leer_filas, sembrar_desde_excel, validar_fila


def _excel(tmp_path, filas, encabezados=("RFC", "NOMBRE", "ROL")):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(list(encabezados))
    for fila in filas:
        ws.append(fila)
    ruta = tmp_path / "usuarios.xlsx"
    wb.save(ruta)
    return str(ruta)


def test_leer_filas_ignora_renglones_sin_rfc(tmp_path):
    ruta = _excel(tmp_path, [
        ("MIMA991129", "Miranda Martinez Ana Karen", "CABINA"),
        (None, "Renglón vacío", "CABINA"),
    ])
    filas = leer_filas(ruta)
    assert len(filas) == 1
    assert filas[0]["rfc"] == "MIMA991129"
    assert filas[0]["rol"] == "CABINA"


def test_leer_filas_exige_columnas_obligatorias(tmp_path):
    ruta = _excel(tmp_path, [("MIMA991129", "X", "CABINA")], encabezados=("RFC", "NOMBRE"))
    with pytest.raises(ErrorCargaUsuarios):
        leer_filas(ruta)


def test_validar_fila_administrador_exige_11_caracteres():
    fila = {"rfc": "PASE950502", "nombre": "Emmanuel", "rol": "ADMINISTRADOR", "entidad": None, "correo": None}
    assert validar_fila(fila) is not None  # 10 caracteres, le falta la homoclave

    fila["rfc"] = "PASE950502G"
    assert validar_fila(fila) is None


def test_validar_fila_proveedor_exige_entidad_y_correo():
    fila = {"rfc": "PROV000001", "nombre": "X", "rol": "PROVEEDOR", "entidad": None, "correo": None}
    assert validar_fila(fila) is not None

    fila["entidad"], fila["correo"] = "Jalisco", "x@example.com"
    assert validar_fila(fila) is None


def test_sembrar_desde_excel_aplica_solo_filas_validas(tmp_path, monkeypatch):
    from app.config import get_settings
    from app.db.local_store import init_local_db

    # init_local_db()/accesos_repo leen la ruta del sqlite de get_settings();
    # sin esto se iría a la base real de desarrollo (./data/app_local.db).
    monkeypatch.setenv("DB_AUTH_MODE", "sql")
    monkeypatch.setenv("DB_SERVER", "servidor-fake")
    monkeypatch.setenv("DB_NAME", "bd-fake")
    monkeypatch.setenv("DB_USER", "usuario-fake")
    monkeypatch.setenv("DB_PASSWORD", "password-fake")
    monkeypatch.setenv("JWT_SECRET_KEY", "clave-de-prueba")
    monkeypatch.setenv("LOCAL_DB_PATH", str(tmp_path / "siembra_directa.db"))
    get_settings.cache_clear()

    ruta = _excel(tmp_path, [
        ("MIMA991129", "Miranda Martinez Ana Karen", "CABINA"),
        ("PASE950502G", "Emmanuel Parra Sanchez", "ADMINISTRADOR"),
        ("ADMI000001", "Admin RFC corto", "ADMINISTRADOR"),  # rechazada: faltan 11 caracteres
    ])
    init_local_db()
    resultado = sembrar_desde_excel(ruta, aplicar=True)

    assert len(resultado["listas"]) == 2
    assert len(resultado["rechazadas"]) == 1
    accesos = {a["rfc"] for a in accesos_repo.listar_accesos()}
    assert "MIMA991129" in accesos
    assert "PASE950502G" in accesos
    assert "ADMI000001" not in accesos


def test_siembra_automatica_al_primer_arranque(tmp_path, monkeypatch):
    ruta = _excel(tmp_path, [
        ("MIMA991129", "Miranda Martinez Ana Karen", "CABINA"),
        ("PASE950502G", "Emmanuel Parra Sanchez", "ADMINISTRADOR"),
    ])

    monkeypatch.setenv("DB_AUTH_MODE", "sql")
    monkeypatch.setenv("DB_SERVER", "servidor-fake")
    monkeypatch.setenv("DB_NAME", "bd-fake")
    monkeypatch.setenv("DB_USER", "usuario-fake")
    monkeypatch.setenv("DB_PASSWORD", "password-fake")
    monkeypatch.setenv("LOCAL_DB_PATH", str(tmp_path / "siembra.db"))
    monkeypatch.setenv("JWT_SECRET_KEY", "clave-de-prueba")
    monkeypatch.setenv("SEED_USUARIOS_RUTA", ruta)

    import app.main as main_module

    monkeypatch.setattr(main_module, "calentar_pool", lambda: None)

    from app.config import get_settings

    get_settings.cache_clear()

    with TestClient(app):
        accesos = {a["rfc"]: a for a in accesos_repo.listar_accesos()}
        assert accesos["MIMA991129"]["perfil"] == accesos_repo.PERFIL_CABINA
        assert accesos["PASE950502G"]["perfil"] == accesos_repo.PERFIL_ADMINISTRADOR
        assert accesos["PASE950502G"]["tiene_password"] is False

        # Un segundo "arranque" no debe volver a sembrar (la tabla ya no está
        # vacía): dar de alta a mano a un tercero y confirmar que sigue ahí
        # tal cual después de reiniciar, y que no se repite ni se altera.
        accesos_repo.alta_acceso("CABI999999", "Dado de alta a mano", accesos_repo.PERFIL_CABINA)

    get_settings.cache_clear()
    with TestClient(app):
        accesos = {a["rfc"] for a in accesos_repo.listar_accesos()}
        assert "CABI999999" in accesos  # no se perdió
        assert len(accesos) == 3  # no se volvió a sembrar el Excel encima
