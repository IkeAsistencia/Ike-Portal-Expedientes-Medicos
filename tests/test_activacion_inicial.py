"""
Activación inicial del portal: con la tabla de accesos vacía, POST
/auth/activacion crea al primer Administrador; en cuanto existe un acceso la
ruta responde 404 (ver app/routers/auth.py y accesos_repo.activar_portal).
"""

import threading

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.core.rate_limit import limpiar_todo
from app.main import app
from app.repositories import accesos_repo

CUERPO = {"rfc": "rocm940213", "nombre": "  Carlos Pineda  ", "password": "Clave#2026"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_AUTH_MODE", "sql")
    monkeypatch.setenv("DB_SERVER", "servidor-fake")
    monkeypatch.setenv("DB_NAME", "bd-fake")
    monkeypatch.setenv("DB_USER", "usuario-fake")
    monkeypatch.setenv("DB_PASSWORD", "password-fake")
    monkeypatch.setenv("JWT_SECRET_KEY", "clave-de-prueba")
    monkeypatch.setenv("LOCAL_DB_PATH", str(tmp_path / "activacion.db"))
    get_settings.cache_clear()

    import app.main as main_module

    monkeypatch.setattr(main_module, "calentar_pool", lambda: None)
    limpiar_todo()
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def test_estado_pide_activacion_con_la_tabla_vacia(client):
    assert client.get("/auth/activacion/estado").json() == {"requerida": True}


def test_activar_crea_al_primer_administrador_y_lo_deja_entrar(client):
    r = client.post("/auth/activacion", json=CUERPO)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["rfc"] == "ROCM940213"
    assert cuerpo["nombre"] == "Carlos Pineda"
    assert cuerpo["perfil"] == accesos_repo.PERFIL_ADMINISTRADOR
    assert cuerpo["access_token"]

    # Quedó con su contraseña: el login normal funciona sin pasar por "crear contraseña".
    login = client.post("/auth/rfc/login", json={"rfc": "ROCM940213", "password": "Clave#2026"})
    assert login.status_code == 200
    assert login.json()["perfil"] == accesos_repo.PERFIL_ADMINISTRADOR


def test_una_vez_activado_la_opcion_desaparece(client):
    assert client.post("/auth/activacion", json=CUERPO).status_code == 200

    assert client.get("/auth/activacion/estado").json() == {"requerida": False}
    otro = {"rfc": "OTRO950101", "nombre": "Otra Persona", "password": "Clave#2026"}
    assert client.post("/auth/activacion", json=otro).status_code == 404
    assert accesos_repo.buscar_acceso("OTRO950101") is None


def test_no_se_activa_si_ya_hay_accesos_sembrados(client):
    accesos_repo.alta_acceso("MIMA991129", "Miranda", accesos_repo.PERFIL_CABINA)

    assert client.get("/auth/activacion/estado").json() == {"requerida": False}
    assert client.post("/auth/activacion", json=CUERPO).status_code == 404
    assert accesos_repo.buscar_acceso("ROCM940213") is None


@pytest.mark.parametrize(
    "cambio",
    [
        {"rfc": "ROCM94021"},          # 9 caracteres
        {"rfc": "ROCM940213XY"},       # 12 caracteres
        {"rfc": "1234940213"},         # no empieza con 4 letras
        {"nombre": "   "},             # nombre vacío
        {"password": "corta1!"},       # menos de 8
        {"password": "sinmayuscula1!"},
    ],
)
def test_datos_invalidos_no_crean_nada(client, cambio):
    r = client.post("/auth/activacion", json={**CUERPO, **cambio})
    assert r.status_code == 422
    assert client.get("/auth/activacion/estado").json() == {"requerida": True}


def test_rfc_de_11_caracteres_no_se_acepta(client):
    r = client.post("/auth/activacion", json={**CUERPO, "rfc": "ROCM940213G"})
    assert r.status_code == 422
    assert client.get("/auth/activacion/estado").json() == {"requerida": True}


def test_dos_activaciones_simultaneas_solo_crean_a_uno(client):
    resultados = []

    def activar(rfc):
        resultados.append(accesos_repo.activar_portal(rfc, "Persona", "Clave#2026"))

    hilos = [threading.Thread(target=activar, args=(f"ABCD00000{i}",)) for i in range(5)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert sum(r is not None for r in resultados) == 1
    assert len(accesos_repo.listar_accesos()) == 1
