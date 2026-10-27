"""
Pruebas de GET /directorio-proveedores/configuracion-mapa, que entrega al
navegador la llave para pintar el mapa de Google (Maps JavaScript API).

¿Por qué una llave aparte? Los Términos de Servicio de Google
(Maps Service Specific Terms, 14.2) prohíben mostrar contenido de la Places
API sobre un mapa que no sea de Google. Eso obliga a pintar los resultados de
Google con Maps JavaScript API, y esa llave SÍ viaja al navegador -- así que
tiene que ser distinta de google_maps_api_key (que solo usa el servidor) y
estar restringida por dominio.

La regla que se cuida aquí: google_maps_api_key NUNCA debe salir en esta
respuesta.
"""
import pytest
from fastapi.testclient import TestClient

import app.repositories.accesos_repo as accesos_repo
from app.main import app

LLAVE_SERVIDOR = "llave-solo-del-servidor"
LLAVE_NAVEGADOR = "llave-del-navegador-restringida"


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
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", LLAVE_SERVIDOR)

    from app.config import get_settings

    get_settings.cache_clear()

    with TestClient(app) as c:
        yield c


def _headers(client, rfc, perfil, password):
    if perfil == accesos_repo.PERFIL_PROVEEDOR:
        accesos_repo.alta_acceso(rfc, "Proveedor", perfil, "Jalisco", "p@correo.mx")
    else:
        accesos_repo.alta_acceso(rfc, "Otro", perfil)
    accesos_repo.crear_password(rfc, password)
    r = client.post("/auth/rfc/login", json={"rfc": rfc, "password": password})
    token = r.json()["access_token"]
    return {"Authorization": "Bearer " + token}


def _proveedor(client):
    return _headers(client, "RFCPROTEST", accesos_repo.PERFIL_PROVEEDOR, "Proveedor2024")


def _admin(client):
    return _headers(client, "RFCADMTEST", accesos_repo.PERFIL_ADMINISTRADOR, "Admin2024xx")


def test_sin_llave_de_navegador_responde_null(client):
    """Sin GOOGLE_MAPS_BROWSER_API_KEY la pantalla debe poder distinguir
    "no configurado" (y caer a lista) de un error."""
    r = client.get("/directorio-proveedores/configuracion-mapa", headers=_proveedor(client))
    assert r.status_code == 200, r.text
    assert r.json() == {"llave": None, "map_id": None}


def test_entrega_la_llave_del_navegador(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_BROWSER_API_KEY", LLAVE_NAVEGADOR)
    monkeypatch.setenv("GOOGLE_MAPS_MAP_ID", "mi-map-id")
    from app.config import get_settings

    get_settings.cache_clear()

    r = client.get("/directorio-proveedores/configuracion-mapa", headers=_proveedor(client))
    assert r.status_code == 200, r.text
    assert r.json() == {"llave": LLAVE_NAVEGADOR, "map_id": "mi-map-id"}


def test_la_llave_del_servidor_nunca_sale_en_la_respuesta(client, monkeypatch):
    """google_maps_api_key consulta Places API desde el servidor: si viajara
    al navegador, cualquiera podría copiarla y gastar la cuota."""
    monkeypatch.setenv("GOOGLE_MAPS_BROWSER_API_KEY", LLAVE_NAVEGADOR)
    from app.config import get_settings

    get_settings.cache_clear()

    r = client.get("/directorio-proveedores/configuracion-mapa", headers=_proveedor(client))
    assert LLAVE_SERVIDOR not in r.text
    assert LLAVE_SERVIDOR not in str(r.headers)


def test_una_llave_en_blanco_cuenta_como_no_configurada(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_BROWSER_API_KEY", "   ")
    from app.config import get_settings

    get_settings.cache_clear()

    r = client.get("/directorio-proveedores/configuracion-mapa", headers=_proveedor(client))
    assert r.json()["llave"] is None


def test_exige_sesion(client):
    r = client.get("/directorio-proveedores/configuracion-mapa")
    assert r.status_code == 401


def test_el_administrador_no_la_recibe(client, monkeypatch):
    """Misma restricción que las búsquedas fuera de la red: del directorio,
    el Administrador no usa esta pantalla."""
    monkeypatch.setenv("GOOGLE_MAPS_BROWSER_API_KEY", LLAVE_NAVEGADOR)
    from app.config import get_settings

    get_settings.cache_clear()

    r = client.get("/directorio-proveedores/configuracion-mapa", headers=_admin(client))
    assert r.status_code == 403


def test_la_configuracion_no_depende_de_la_llave_del_servidor(client, monkeypatch):
    """Se puede pintar el mapa aunque falte la llave de Places API (y al
    revés): son dos llaves independientes."""
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "")
    monkeypatch.setenv("GOOGLE_MAPS_BROWSER_API_KEY", LLAVE_NAVEGADOR)
    from app.config import get_settings

    get_settings.cache_clear()

    r = client.get("/directorio-proveedores/configuracion-mapa", headers=_proveedor(client))
    assert r.status_code == 200
    assert r.json()["llave"] == LLAVE_NAVEGADOR
