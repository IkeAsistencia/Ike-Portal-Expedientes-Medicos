"""
Pruebas de la búsqueda FUERA DE LA RED alternativa
(GET /directorio-proveedores/fuera-de-red-google-maps), que consulta la
Places API (New) de Google Maps.

NO pega a Google de verdad: se sustituye httpx.post por respuestas simuladas,
igual que tests/test_denue_fuera_de_red.py sustituye la del INEGI. Así las
pruebas corren sin llave, sin red y sin gastar cuota de Google.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import google_maps_service

# Un resultado tal como lo regresa Places API (New) / places:searchText, con
# los nombres de campo exactos de la API nueva (displayName.text,
# formattedAddress, userRatingCount, currentOpeningHours.openNow,
# location.latitude/longitude).
LUGAR_GOOGLE = {
    "id": "ChIJ_algun_place_id",
    "displayName": {"text": "Consultorio Dr. Pérez - Cardiología", "languageCode": "es"},
    "formattedAddress": "Av. Vallarta 1450, Americana, 44100 Guadalajara, Jal., México",
    "rating": 4.7,
    "userRatingCount": 83,
    "currentOpeningHours": {"openNow": True},
    "location": {"latitude": 20.6736, "longitude": -103.3444},
}

ENTIDADES_FALSAS = [
    {"clave": "JC", "descripcion": "JALISCO", "clave_inegi": "14"},
    {"clave": "DF", "descripcion": "CIUDAD DE MEXICO", "clave_inegi": "09"},
]

MUNICIPIOS_FALSOS_JC = [
    {"clave": "00039", "descripcion": "Guadalajara"},
]


class RespuestaFalsa:
    def __init__(self, status_code=200, datos=None, texto=None):
        self.status_code = status_code
        self._datos = datos
        self._texto = texto

    def json(self):
        if self._texto is not None:
            raise ValueError("no es JSON")
        return self._datos


@pytest.fixture(autouse=True)
def _sin_sql_server(monkeypatch):
    import app.main as main_module

    monkeypatch.setattr(main_module, "calentar_pool", lambda: None)

    from app.core.rate_limit import limpiar_todo

    limpiar_todo()

    # Los catálogos de entidad/municipio pegan a SQL Server real -- aquí se
    # sustituyen por los de arriba.
    import app.repositories.catalogos_repo as catalogos_repo

    monkeypatch.setattr(
        catalogos_repo, "listar_entidades",
        lambda: [catalogos_repo.EntidadFederativa(**e) for e in ENTIDADES_FALSAS],
    )
    monkeypatch.setattr(
        catalogos_repo, "listar_municipios",
        lambda cod_ent: [catalogos_repo.CatalogoItemTexto(**m) for m in MUNICIPIOS_FALSOS_JC],
    )


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_AUTH_MODE", "sql")
    monkeypatch.setenv("DB_SERVER", "servidor-fake")
    monkeypatch.setenv("DB_NAME", "bd-fake")
    monkeypatch.setenv("DB_USER", "usuario-fake")
    monkeypatch.setenv("DB_PASSWORD", "password-fake")
    monkeypatch.setenv("LOCAL_DB_PATH", str(tmp_path / "test_local.db"))
    monkeypatch.setenv("JWT_SECRET_KEY", "clave-de-prueba")
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "llave-de-prueba")

    from app.config import get_settings

    get_settings.cache_clear()

    with TestClient(app) as c:
        yield c


def _headers(client, rfc, nombre, perfil, password):
    import app.repositories.accesos_repo as accesos_repo_module

    if perfil == accesos_repo_module.PERFIL_PROVEEDOR:
        accesos_repo_module.alta_acceso(rfc, nombre, perfil, "Jalisco", "p@correo.mx")
    else:
        accesos_repo_module.alta_acceso(rfc, nombre, perfil)
    accesos_repo_module.crear_password(rfc, password)
    r = client.post("/auth/rfc/login", json={"rfc": rfc, "password": password})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _admin(client):
    import app.repositories.accesos_repo as a
    return _headers(client, "RFCADMTEST", "Admin", a.PERFIL_ADMINISTRADOR, "Admin2024xx")


def _proveedor(client):
    import app.repositories.accesos_repo as a
    return _headers(client, "RFCPROTEST", "Proveedor", a.PERFIL_PROVEEDOR, "Proveedor2024")


def _cabina(client):
    import app.repositories.accesos_repo as a
    return _headers(client, "RFCCABTEST", "Cabina", a.PERFIL_CABINA, "Cabina2024xx")


def _responder(monkeypatch, respuesta, capturadas=None):
    def fake_post(url, json=None, headers=None, **kwargs):
        if capturadas is not None:
            capturadas.append({"url": url, "json": json or {}, "headers": headers or {}})
        return respuesta
    monkeypatch.setattr(google_maps_service.httpx, "post", fake_post)


# ---------- Construcción de la consulta de texto libre ----------

def test_la_consulta_combina_especialidad_municipio_y_entidad():
    consulta = google_maps_service.construir_consulta("Cardiología", "JALISCO", "Guadalajara")
    assert consulta == "Cardiología en Guadalajara, JALISCO, México"


def test_sin_municipio_la_consulta_usa_toda_la_entidad():
    consulta = google_maps_service.construir_consulta("Cardiología", "JALISCO", None)
    assert consulta == "Cardiología en JALISCO, México"


# ---------- Mapeo de la respuesta (API nueva) ----------

def test_la_respuesta_de_google_se_mapea_a_candidatos(client, monkeypatch):
    _responder(monkeypatch, RespuestaFalsa(200, {"places": [LUGAR_GOOGLE]}))

    r = client.get(
        "/directorio-proveedores/fuera-de-red-google-maps",
        params={"cod_ent": "JC", "cod_mun": "00039", "especialidad": "cardiologia"},
        headers=_proveedor(client),
    )
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["fuente"] == "Google Maps"
    assert cuerpo["area"] == "Guadalajara, JALISCO"
    assert cuerpo["total"] == 1

    c = cuerpo["candidatos"][0]
    # Los nombres de campo de la API nueva se traducen a los que ya usa la
    # pantalla (displayName.text -> nombre, userRatingCount -> total_calificaciones...).
    assert c["nombre"] == "Consultorio Dr. Pérez - Cardiología"
    assert c["direccion"].startswith("Av. Vallarta 1450")
    assert c["calificacion"] == pytest.approx(4.7)
    assert c["total_calificaciones"] == 83
    assert c["abierto_ahora"] is True
    assert c["latitud"] == pytest.approx(20.6736)
    assert c["longitud"] == pytest.approx(-103.3444)
    assert c["place_id"] == "ChIJ_algun_place_id"
    assert c["enlace_maps"] == "https://www.google.com/maps/place/?q=place_id:ChIJ_algun_place_id"
    assert c["origen"] == "fuera_de_red_google"
    # Nunca una clave PRV- del padrón, ni datos que Google no tiene.
    assert not any(k.startswith("clave") for k in c)


def test_no_inventa_cedula_costo_convenio_ni_telefono(client, monkeypatch):
    """Google no regresa teléfono en Text Search (costaría una consulta de
    Place Details por cada candidato) -- no debe rellenarse con nada."""
    _responder(monkeypatch, RespuestaFalsa(200, {"places": [LUGAR_GOOGLE]}))
    r = client.get(
        "/directorio-proveedores/fuera-de-red-google-maps",
        params={"cod_ent": "JC", "especialidad": "cardiologia"},
        headers=_proveedor(client),
    )
    c = r.json()["candidatos"][0]
    for campo in ("cedula", "costo_consulta", "convenio", "horario", "telefono"):
        assert campo not in c


def test_sin_resultados_no_es_error(client, monkeypatch):
    """La API nueva responde 200 con el objeto vacío (sin la clave "places")
    cuando no hay coincidencias -- eso es "no encontré nada", no un fallo."""
    _responder(monkeypatch, RespuestaFalsa(200, {}))
    r = client.get(
        "/directorio-proveedores/fuera-de-red-google-maps",
        params={"cod_ent": "JC", "especialidad": "cardiologia"},
        headers=_proveedor(client),
    )
    assert r.status_code == 200
    assert r.json()["total"] == 0
    assert r.json()["candidatos"] == []


def test_area_sin_municipio_es_solo_la_entidad(client, monkeypatch):
    _responder(monkeypatch, RespuestaFalsa(200, {"places": [LUGAR_GOOGLE]}))
    r = client.get(
        "/directorio-proveedores/fuera-de-red-google-maps",
        params={"cod_ent": "JC", "especialidad": "cardiologia"},
        headers=_proveedor(client),
    )
    assert r.json()["area"] == "JALISCO"


def test_la_consulta_viaja_en_el_cuerpo_y_la_llave_en_el_encabezado(client, monkeypatch):
    """La API nueva recibe el texto en el cuerpo JSON y la llave en
    X-Goog-Api-Key (no en la URL, para que no quede en logs de proxy)."""
    capturadas = []
    _responder(monkeypatch, RespuestaFalsa(200, {"places": []}), capturadas=capturadas)
    client.get(
        "/directorio-proveedores/fuera-de-red-google-maps",
        params={"cod_ent": "JC", "cod_mun": "00039", "especialidad": "cardiologia"},
        headers=_proveedor(client),
    )
    peticion = capturadas[0]
    assert peticion["url"] == "https://places.googleapis.com/v1/places:searchText"
    assert peticion["json"]["textQuery"] == "cardiologia en Guadalajara, JALISCO, México"
    assert peticion["json"]["regionCode"] == "MX"
    assert peticion["headers"]["X-Goog-Api-Key"] == "llave-de-prueba"
    # El FieldMask es obligatorio en la API nueva y define el costo.
    assert "places.displayName" in peticion["headers"]["X-Goog-FieldMask"]
    assert "places.formattedAddress" in peticion["headers"]["X-Goog-FieldMask"]


# ---------- Errores del servicio ----------

def test_sin_llave_configurada_responde_503(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "")
    from app.config import get_settings

    get_settings.cache_clear()

    r = client.get(
        "/directorio-proveedores/fuera-de-red-google-maps",
        params={"cod_ent": "JC", "especialidad": "cardiologia"},
        headers=_proveedor(client),
    )
    assert r.status_code == 503
    assert "llave" in r.json()["detail"].lower() or "google_maps_api_key" in r.json()["detail"].lower()


def test_llave_invalida_responde_502_con_mensaje_claro(client, monkeypatch):
    _responder(monkeypatch, RespuestaFalsa(403, {"error": {"status": "PERMISSION_DENIED", "message": "denied"}}))
    r = client.get(
        "/directorio-proveedores/fuera-de-red-google-maps",
        params={"cod_ent": "JC", "especialidad": "cardiologia"},
        headers=_proveedor(client),
    )
    assert r.status_code == 502
    assert "llave" in r.json()["detail"].lower()


def test_limite_de_cuota_responde_502_con_mensaje_claro(client, monkeypatch):
    _responder(monkeypatch, RespuestaFalsa(429, {"error": {"status": "RESOURCE_EXHAUSTED", "message": "quota"}}))
    r = client.get(
        "/directorio-proveedores/fuera-de-red-google-maps",
        params={"cod_ent": "JC", "especialidad": "cardiologia"},
        headers=_proveedor(client),
    )
    assert r.status_code == 502
    assert "límite" in r.json()["detail"].lower() or "limite" in r.json()["detail"].lower()


def test_timeout_de_google_responde_502(client, monkeypatch):
    def fake_post(*args, **kwargs):
        raise google_maps_service.httpx.TimeoutException("tardó demasiado")
    monkeypatch.setattr(google_maps_service.httpx, "post", fake_post)

    r = client.get(
        "/directorio-proveedores/fuera-de-red-google-maps",
        params={"cod_ent": "JC", "especialidad": "cardiologia"},
        headers=_proveedor(client),
    )
    assert r.status_code == 502
    assert "tardó" in r.json()["detail"]


def test_respuesta_que_no_es_json_responde_502(client, monkeypatch):
    _responder(monkeypatch, RespuestaFalsa(200, texto="<html>mantenimiento</html>"))
    r = client.get(
        "/directorio-proveedores/fuera-de-red-google-maps",
        params={"cod_ent": "JC", "especialidad": "cardiologia"},
        headers=_proveedor(client),
    )
    assert r.status_code == 502


def test_http_distinto_de_200_responde_502(client, monkeypatch):
    _responder(monkeypatch, RespuestaFalsa(500))
    r = client.get(
        "/directorio-proveedores/fuera-de-red-google-maps",
        params={"cod_ent": "JC", "especialidad": "cardiologia"},
        headers=_proveedor(client),
    )
    assert r.status_code == 502


def test_la_llave_viaja_pero_no_se_registra_en_el_log(client, monkeypatch, caplog):
    import logging

    _responder(monkeypatch, RespuestaFalsa(403, {"error": {"status": "PERMISSION_DENIED", "message": "denied"}}))
    with caplog.at_level(logging.WARNING, logger="google_maps_service"):
        r = client.get(
            "/directorio-proveedores/fuera-de-red-google-maps",
            params={"cod_ent": "JC", "especialidad": "cardiologia"},
            headers=_proveedor(client),
        )
    assert r.status_code == 502
    registros = [x.getMessage() for x in caplog.records if x.name == "google_maps_service"]
    assert registros, "debió registrarse el error"
    assert not any("llave-de-prueba" in m for m in registros), "la llave NO debe quedar en el log"


def test_entidad_fuera_del_catalogo_responde_400(client, monkeypatch):
    _responder(monkeypatch, RespuestaFalsa(200, {"places": [LUGAR_GOOGLE]}))
    r = client.get(
        "/directorio-proveedores/fuera-de-red-google-maps",
        params={"cod_ent": "ZZ", "especialidad": "cardiologia"},
        headers=_proveedor(client),
    )
    assert r.status_code == 400


def test_especialidad_demasiado_corta_se_rechaza(client):
    r = client.get(
        "/directorio-proveedores/fuera-de-red-google-maps",
        params={"cod_ent": "JC", "especialidad": "ca"},
        headers=_proveedor(client),
    )
    assert r.status_code == 422


# ---------- Permisos ----------

def test_solo_el_proveedor_busca_fuera_de_la_red_con_google(client, monkeypatch):
    """Misma restricción que /fuera-de-red (DENUE), decisión del usuario
    (2026-10-26): del directorio, el Administrador solo usa Solicitudes,
    Alta de médico, Carga del catálogo y Métricas."""
    _responder(monkeypatch, RespuestaFalsa(200, {"places": [LUGAR_GOOGLE]}))
    parametros = {"cod_ent": "JC", "especialidad": "cardiologia"}
    r_proveedor = client.get("/directorio-proveedores/fuera-de-red-google-maps", params=parametros, headers=_proveedor(client))
    assert r_proveedor.status_code == 200
    r_admin = client.get("/directorio-proveedores/fuera-de-red-google-maps", params=parametros, headers=_admin(client))
    assert r_admin.status_code == 403


def test_cabina_no_puede_usar_el_directorio(client, monkeypatch):
    _responder(monkeypatch, RespuestaFalsa(200, {"places": [LUGAR_GOOGLE]}))
    r = client.get(
        "/directorio-proveedores/fuera-de-red-google-maps",
        params={"cod_ent": "JC", "especialidad": "cardiologia"},
        headers=_cabina(client),
    )
    assert r.status_code == 403
