"""
Pruebas de /catalogos/entidades y /catalogos/municipios (combo Entidad/
Municipio del Alta de médico, Directorio de Proveedores) -- NO requiere SQL
Server real.
"""
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

import app.repositories.catalogos_repo as catalogos_repo_module
from app.main import app


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
    monkeypatch.setenv("JWT_SECRET_KEY", "clave-de-prueba")

    from app.config import get_settings

    get_settings.cache_clear()

    with TestClient(app) as c:
        yield c


def _auth_headers(client):
    import app.repositories.accesos_repo as accesos_repo_module

    accesos_repo_module.alta_acceso("RFCCATTEST", "Usuario de Prueba", accesos_repo_module.PERFIL_ADMINISTRADOR)
    accesos_repo_module.crear_password("RFCCATTEST", "Clave2024xx")
    r = client.post("/auth/rfc/login", json={"rfc": "RFCCATTEST", "password": "Clave2024xx"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


class _FilaCEntFed:
    """Simula una fila de pyodbc: acceso por atributo, igual que
    CodEnt/dsEntFed/clEntFed reales."""

    def __init__(self, cod_ent, ds_ent_fed, cl_ent_fed=1):
        self.CodEnt = cod_ent
        self.dsEntFed = ds_ent_fed
        # clEntFed (1 a 32) es la clave de entidad del INEGI; se expone como
        # clave_inegi porque es la que pide el DENUE (ver denue_service.py).
        self.clEntFed = cl_ent_fed


class _CursorFake:
    def __init__(self, filas):
        self._filas = filas
        self.ejecutado = None

    def execute(self, query):
        self.ejecutado = query

    def fetchall(self):
        return self._filas


class _ConexionFake:
    def __init__(self, filas):
        self._cursor = _CursorFake(filas)

    def cursor(self):
        return self._cursor


def _fake_get_connection(filas):
    @contextmanager
    def _gen():
        yield _ConexionFake(filas)
    return _gen


# ---------- /catalogos/entidades ----------

def test_entidades_consulta_centfed_estatico(client, monkeypatch):
    filas = [_FilaCEntFed("JC", "Jalisco", 14), _FilaCEntFed("DF", "Ciudad de México", 9)]
    conexion_fake = _fake_get_connection(filas)
    monkeypatch.setattr(catalogos_repo_module, "get_connection", conexion_fake)

    r = client.get("/catalogos/entidades", headers=_auth_headers(client))
    assert r.status_code == 200
    assert r.json() == [
        {"clave": "JC", "descripcion": "Jalisco", "clave_inegi": "14"},
        {"clave": "DF", "descripcion": "Ciudad de México", "clave_inegi": "09"},
    ]


def test_entidades_traen_la_clave_del_inegi_a_dos_digitos(client, monkeypatch):
    """clEntFed se expone con dos dígitos porque así la pide el DENUE para
    acotar el área geográfica ("09", no "9")."""
    monkeypatch.setattr(
        catalogos_repo_module, "get_connection",
        _fake_get_connection([_FilaCEntFed("AS", "Aguascalientes", 1)]),
    )
    r = client.get("/catalogos/entidades", headers=_auth_headers(client))
    assert r.json()[0]["clave_inegi"] == "01"


def test_entidades_quita_espacios_del_codent(client, monkeypatch):
    # CHAR/VARCHAR de SQL Server a veces viene con relleno -- no debe colarse
    # al frontend, porque luego ese valor se manda tal cual a sp_GetMun.
    filas = [_FilaCEntFed("JC  ", "Jalisco", 14)]
    monkeypatch.setattr(catalogos_repo_module, "get_connection", _fake_get_connection(filas))

    r = client.get("/catalogos/entidades", headers=_auth_headers(client))
    assert r.json()[0]["clave"] == "JC"


def test_entidades_requiere_sesion(client):
    r = client.get("/catalogos/entidades")
    assert r.status_code == 401


# ---------- /catalogos/municipios ----------

def test_municipios_llama_sp_getmun_con_clexpediente_en_cero(client, monkeypatch):
    llamadas = []

    def fake_call_procedure(sp_name, params=None):
        llamadas.append((sp_name, params))
        return [{"CodMD": "039", "dsMunDel": "Guadalajara"}, {"CodMD": "120", "dsMunDel": "Zapopan"}]

    monkeypatch.setattr(catalogos_repo_module, "call_procedure", fake_call_procedure)

    r = client.get("/catalogos/municipios", params={"cod_ent": "14"}, headers=_auth_headers(client))
    assert r.status_code == 200
    assert r.json() == [
        {"clave": "039", "descripcion": "Guadalajara"},
        {"clave": "120", "descripcion": "Zapopan"},
    ]
    # @clExpediente siempre en 0 (no aplica para este catálogo) y @CodEnt es
    # justo el que mandó el frontend -- el que salió de /catalogos/entidades.
    assert llamadas == [("dbo.sp_GetMun", {"CodEnt": "14", "clExpediente": 0})]


def test_municipios_requiere_cod_ent(client):
    r = client.get("/catalogos/municipios", headers=_auth_headers(client))
    assert r.status_code == 422


def test_municipios_no_distingue_mayusculas_en_las_columnas_del_sp(client, monkeypatch):
    # No hay una definición de dbo.sp_GetMun en el repo para confirmar la
    # casing exacta de sus columnas -- no debe tronar si vienen distintas.
    def fake_call_procedure(sp_name, params=None):
        return [{"codMd": "039", "dsMundel": "Guadalajara"}]

    monkeypatch.setattr(catalogos_repo_module, "call_procedure", fake_call_procedure)

    r = client.get("/catalogos/municipios", params={"cod_ent": "14"}, headers=_auth_headers(client))
    assert r.status_code == 200
    assert r.json() == [{"clave": "039", "descripcion": "Guadalajara"}]
