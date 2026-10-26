"""
Cierre de sesión por inactividad (30 minutos) y duración máxima (8 horas):
el servidor emite tokens cortos que el portal renueva mientras hay actividad
(POST /auth/renovar). Sin actividad nadie los renueva y vencen solos.
"""
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from app.main import app

SECRETO = "clave-de-prueba-de-al-menos-32-caracteres"


@pytest.fixture(autouse=True)
def _sin_sql_server(monkeypatch):
    import app.main as main_module

    monkeypatch.setattr(main_module, "calentar_pool", lambda: None)
    from app.core.rate_limit import limpiar_todo

    limpiar_todo()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_AUTH_MODE", "sql")
    monkeypatch.setenv("DB_SERVER", "servidor-fake")
    monkeypatch.setenv("DB_NAME", "bd-fake")
    monkeypatch.setenv("DB_USER", "usuario-fake")
    monkeypatch.setenv("DB_PASSWORD", "password-fake")
    monkeypatch.setenv("LOCAL_DB_PATH", str(tmp_path / "test_local.db"))
    monkeypatch.setenv("JWT_SECRET_KEY", SECRETO)
    from app.config import get_settings

    get_settings.cache_clear()
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def _login(client):
    import app.repositories.accesos_repo as accesos

    accesos.alta_acceso("RFCPROTEST", "Proveedor de Prueba", accesos.PERFIL_PROVEEDOR)
    accesos.crear_password("RFCPROTEST", "Proveedor2024$")
    return client.post("/auth/rfc/login", json={"rfc": "RFCPROTEST", "password": "Proveedor2024$"}).json()["access_token"]


def _leer(token):
    return jwt.decode(token, SECRETO, algorithms=["HS256"])


def _token(**cambios):
    base = {"nombre": "Proveedor de Prueba", "rfc": "RFCPROTEST", "perfil": 3}
    return jwt.encode({**base, **cambios}, SECRETO, algorithm="HS256")


def _ahora():
    return datetime.now(timezone.utc)


def test_el_token_dura_la_ventana_de_inactividad_y_no_ocho_horas(client):
    datos = _leer(_login(client))
    minutos = (datos["exp"] - _ahora().timestamp()) / 60
    assert 31 <= minutos <= 32.1, minutos   # 30 de inactividad + 2 de margen
    assert abs(datos["ini"] - _ahora().timestamp()) < 60


def test_renovar_extiende_la_ventana_y_conserva_el_inicio(client):
    inicio = int((_ahora() - timedelta(minutes=20)).timestamp())
    viejo = _token(ini=inicio, exp=_ahora() + timedelta(minutes=10))
    r = client.post("/auth/renovar", headers={"Authorization": f"Bearer {viejo}"})
    assert r.status_code == 200, r.text
    assert r.json()["inactividad_minutos"] == 30
    nuevo = _leer(r.json()["access_token"])
    assert nuevo["ini"] == inicio, "renovar no reinicia la sesión"
    assert (nuevo["exp"] - _ahora().timestamp()) / 60 > 31
    assert nuevo["rfc"] == "RFCPROTEST" and nuevo["perfil"] == 3 and nuevo["nombre"] == "Proveedor de Prueba"
    # Y el token renovado sirve para usar el portal.
    assert client.get("/solicitudes-alta-medico", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).status_code == 200


def test_sin_actividad_el_token_vence_solo(client):
    vencido = _token(ini=int(_ahora().timestamp()) - 3600, exp=_ahora() - timedelta(seconds=1))
    assert client.get("/solicitudes-alta-medico", headers={"Authorization": f"Bearer {vencido}"}).status_code == 401
    assert client.post("/auth/renovar", headers={"Authorization": f"Bearer {vencido}"}).status_code == 401


def test_renovar_no_pasa_de_la_duracion_maxima(client):
    # Inició hace 8 h: aunque su token siga vivo, ya no se renueva.
    inicio = int((_ahora() - timedelta(minutes=480)).timestamp())
    token = _token(ini=inicio, exp=_ahora() + timedelta(minutes=5))
    assert client.post("/auth/renovar", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_cerca_del_maximo_la_renovacion_se_recorta_al_maximo(client):
    inicio = _ahora() - timedelta(minutes=470)   # le quedan 10 minutos de sesión
    token = _token(ini=int(inicio.timestamp()), exp=_ahora() + timedelta(minutes=5))
    nuevo = _leer(client.post("/auth/renovar", headers={"Authorization": f"Bearer {token}"}).json()["access_token"])
    assert nuevo["exp"] <= (inicio + timedelta(minutes=480)).timestamp() + 1


def test_renovar_sin_sesion(client):
    assert client.post("/auth/renovar").status_code == 401
