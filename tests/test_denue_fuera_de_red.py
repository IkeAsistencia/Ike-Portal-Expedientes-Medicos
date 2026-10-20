"""
Pruebas de la búsqueda FUERA DE LA RED (GET /directorio-proveedores/fuera-de-red),
que consulta el DENUE del INEGI.

NO pega al INEGI de verdad: se sustituye httpx.get por respuestas simuladas,
igual que el resto de la suite sustituye call_procedure. Así las pruebas
corren sin token, sin red y sin depender de que el servicio esté arriba.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import denue_service

# Una fila tal como la devuelve el DENUE (ver la documentación de la API y el
# ejemplo del propio INEGI) -- con los nombres de campo exactos.
FILA_DENUE = {
    "CLEE": "14039621112000684",
    "Id": "9321560",
    "Nombre": "CONSULTORIO DE CARDIOLOGIA DR PEREZ",
    "Razon_social": "SERVICIOS MEDICOS DEL VALLE SA DE CV",
    "Clase_actividad": "Consultorios de medicina especializada del sector privado",
    "Estrato": "0 a 5 personas",
    "Tipo_vialidad": "AVENIDA",
    "Calle": "VALLARTA",
    "Num_Exterior": "1450",
    "Num_Interior": "302",
    "Colonia": "AMERICANA",
    "CP": "44100",
    "Ubicacion": "GUADALAJARA, Guadalajara, JALISCO",
    "Telefono": "3312345678",
    "Correo_e": "consultorio@correo.mx",
    "Sitio_internet": "www.consultorio.mx",
    "Tipo": "Fijo",
    "Longitud": "-103.34440000",
    "Latitud": "20.67360000",
}

ENTIDADES_FALSAS = [
    {"clave": "JC", "descripcion": "JALISCO", "clave_inegi": "14"},
    {"clave": "DF", "descripcion": "CIUDAD DE MEXICO", "clave_inegi": "09"},
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

    # El catálogo de entidades pega a dbo.cEntFed (SQL Server real) -- aquí se
    # sustituye por las dos entidades de arriba.
    import app.repositories.catalogos_repo as catalogos_repo

    monkeypatch.setattr(
        catalogos_repo, "listar_entidades",
        lambda: [catalogos_repo.EntidadFederativa(**e) for e in ENTIDADES_FALSAS],
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
    monkeypatch.setenv("DENUE_TOKEN", "token-de-prueba")

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


def _parametros(url):
    """Los parámetros de BuscarAreaAct, por nombre, tal como los recibe el INEGI."""
    partes = url.split("/BuscarAreaAct/")[1].split("/")
    nombres = (
        "entidad", "municipio", "localidad", "ageb", "manzana",
        "sector", "subsector", "rama", "subrama", "nombre",
        "reg_inicial", "reg_final", "estrato", "token",
    )
    return dict(zip(nombres, partes))


def _responder(monkeypatch, respuesta, capturadas=None):
    def fake_get(url, **kwargs):
        if capturadas is not None:
            capturadas.append(url)
        return respuesta if not isinstance(respuesta, list) else respuesta.pop(0)
    monkeypatch.setattr(denue_service.httpx, "get", fake_get)


# ---------- Construcción de la clave de área (lo más delicado) ----------

def test_area_de_entidad_completa():
    assert denue_service.construir_area("14", None) == "14"
    assert denue_service.construir_area("14", "") == "14"


def test_area_de_municipio_usa_entidad_mas_tres_digitos():
    """El portal guarda CodMD con ceros a la izquierda ("00039"); el DENUE
    quiere entidad + 3 dígitos de municipio ("14039" = Guadalajara)."""
    assert denue_service.construir_area("14", "00039") == "14039"
    assert denue_service.construir_area("9", "00007") == "09007"


def test_area_ignora_un_municipio_sin_digitos():
    assert denue_service.construir_area("14", "NA") == "14"


def test_entidad_y_municipio_van_en_parametros_separados():
    """El error que costó encontrar: BuscarAreaAct NO recibe "14039" en un
    solo campo, sino entidad y municipio aparte (confirmado contra la API)."""
    assert denue_service.partir_area("14", "00039") == ("14", "039")
    assert denue_service.partir_area("9", "00007") == ("09", "007")


def test_municipio_vacio_significa_toda_la_entidad():
    assert denue_service.partir_area("14", None) == ("14", "0")
    assert denue_service.partir_area("14", "") == ("14", "0")
    assert denue_service.partir_area("14", "NA") == ("14", "0")


# ---------- Tipo de consultorio según la especialidad ----------

def test_las_especialidades_medicas_caen_en_medicina_especializada():
    """El DENUE no distingue cardiología de pediatría: todas son 621113."""
    for especialidad in ("Cardiología", "Pediatría", "Dermatología", "Ginecología"):
        assert denue_service.tipo_para(especialidad) == "medicina_especializada"


def test_las_especialidades_con_clase_propia_se_reconocen():
    assert denue_service.tipo_para("Odontología") == "dental"
    assert denue_service.tipo_para("Psicología") == "psicologia"
    assert denue_service.tipo_para("Nutrición") == "nutricion"
    assert denue_service.tipo_para("Medicina General") == "medicina_general"
    # Nombres como los trae el catálogo de especialidades del portal.
    assert denue_service.tipo_para("ODONTOLOGIA INTEGRAL") == "dental"


def test_una_cirugia_no_es_medicina_general():
    """"CIRUGIA GENERAL" contiene "general", pero un cirujano es un
    especialista: mandarlo a consultorios de medicina general daría una lista
    equivocada."""
    assert denue_service.tipo_para("CIRUGIA GENERAL") == "medicina_especializada"
    assert denue_service.tipo_para("CIRUGIA ONCOLOGICA") == "medicina_especializada"


def test_los_nombres_que_chocan_se_resuelven_por_nombre_completo():
    """"CLINICA" sola es una clínica de consultorios, pero "ALERGOLOGIA E
    INMUNOLOGIA CLINICA" también contiene esa palabra y es otra cosa."""
    assert denue_service.tipo_para("CLINICA") == "clinicas_consultorios"
    assert denue_service.tipo_para("ALERGOLOGIA E INMUNOLOGIA CLINICA") == "medicina_especializada"
    assert denue_service.tipo_para("CLINICA DE FISIOTERAPIA Y REHABILITACION") == "audiologia_terapia"
    assert denue_service.tipo_para("OPTICA") == "optometria"


def test_todo_el_catalogo_de_especialidades_resuelve_a_un_tipo_valido():
    """Como el combo del portal ya ofrece las 38 del catálogo, cualquiera de
    ellas puede llegar aquí: ninguna debe quedar sin tipo."""
    from app.repositories.especialidades_repo import SEMILLA

    for _cl, descripcion, _prioridad, _orden in SEMILLA:
        tipo = denue_service.tipo_para(descripcion)
        assert tipo in denue_service.CLASES_POR_TIPO, descripcion
        assert tipo in denue_service.ETIQUETA_TIPO, descripcion


# ---------- Mapeo de la respuesta ----------

def test_la_respuesta_del_denue_se_mapea_al_formato_del_padron(client, monkeypatch):
    _responder(monkeypatch, RespuestaFalsa(200, [FILA_DENUE]))

    r = client.get(
        "/directorio-proveedores/fuera-de-red",
        params={"cod_ent": "JC", "cod_mun": "00039", "especialidad": "cardiologia"},
        headers=_admin(client),
    )
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["fuente"] == "DENUE (INEGI)"
    assert cuerpo["area"] == "14039"
    assert cuerpo["total"] == 1

    c = cuerpo["candidatos"][0]
    assert c["nombre"] == "CONSULTORIO DE CARDIOLOGIA DR PEREZ"
    assert c["calle_num_ext_int"] == "Avenida VALLARTA 1450, Int. 302"
    assert c["colonia"] == "AMERICANA"
    assert c["codigo_postal"] == "44100"
    assert c["telefono"] == "3312345678"
    assert c["latitud"] == pytest.approx(20.6736)
    assert c["longitud"] == pytest.approx(-103.3444)
    assert c["origen"] == "fuera_de_red"
    # Identificador del DENUE, nunca una clave PRV- del padrón.
    assert c["id_denue"] == "9321560"
    assert not any(k.startswith("clave") for k in c)


def test_no_inventa_cedula_ni_costo_ni_convenio(client, monkeypatch):
    """El DENUE registra el establecimiento, no al médico: esos datos no
    existen y no deben aparecer rellenados con algo verosímil."""
    _responder(monkeypatch, RespuestaFalsa(200, [FILA_DENUE]))
    r = client.get(
        "/directorio-proveedores/fuera-de-red",
        params={"cod_ent": "JC", "especialidad": "cardiologia"},
        headers=_admin(client),
    )
    c = r.json()["candidatos"][0]
    for campo in ("cedula", "costo_consulta", "convenio", "horario", "rating"):
        assert campo not in c


def test_la_respuesta_dice_que_tipo_de_consultorio_se_consulto(client, monkeypatch):
    """Como el DENUE no distingue especialidades, la pantalla necesita saber
    qué se buscó de verdad para avisárselo al usuario."""
    _responder(monkeypatch, RespuestaFalsa(200, [FILA_DENUE]))
    r = client.get(
        "/directorio-proveedores/fuera-de-red",
        params={"cod_ent": "JC", "cod_mun": "00039", "especialidad": "cardiologia"},
        headers=_admin(client),
    )
    cuerpo = r.json()
    assert cuerpo["tipo_consultado"] == "medicina_especializada"
    assert cuerpo["tipo_descripcion"] == "consultorios de medicina especializada"


def test_sin_resultados_no_es_error(client, monkeypatch):
    """El DENUE responde 404 cuando la consulta es válida pero no hay
    coincidencias -- eso es "no encontré nada", no un fallo."""
    _responder(monkeypatch, RespuestaFalsa(404))
    r = client.get(
        "/directorio-proveedores/fuera-de-red",
        params={"cod_ent": "JC", "especialidad": "cardiologia"},
        headers=_admin(client),
    )
    assert r.status_code == 200
    assert r.json()["total"] == 0
    assert r.json()["candidatos"] == []


@pytest.mark.parametrize("cuerpo", ["", "No hay resultados. "])
def test_el_texto_sin_resultados_con_http_200_tampoco_es_error(client, monkeypatch, cuerpo):
    """Comprobado contra la API real: cuando no hay coincidencias el DENUE a
    veces responde 200 con una CADENA JSON en lugar de una lista. Si eso se
    toma como "respuesta inesperada", municipios chicos truenan con 502."""
    _responder(monkeypatch, RespuestaFalsa(200, cuerpo))
    r = client.get(
        "/directorio-proveedores/fuera-de-red",
        params={"cod_ent": "JC", "cod_mun": "00061", "especialidad": "nutricion"},
        headers=_admin(client),
    )
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 0


# ---------- Parámetros que se le mandan al INEGI ----------

def test_la_consulta_acota_por_entidad_municipio_y_clase(client, monkeypatch):
    """Formato real de BuscarAreaAct: entidad y municipio separados, y la
    clase del SCIAN en la posición de "subrama"."""
    urls = []
    _responder(monkeypatch, RespuestaFalsa(200, [FILA_DENUE]), capturadas=urls)
    client.get(
        "/directorio-proveedores/fuera-de-red",
        params={"cod_ent": "JC", "cod_mun": "00039", "especialidad": "cardiologia"},
        headers=_admin(client),
    )
    # Una consulta por cada clase del tipo (privado y público).
    clases = denue_service.CLASES_POR_TIPO["medicina_especializada"]
    assert len(urls) == len(clases)
    for url, clase in zip(urls, clases):
        p = _parametros(url)
        assert p["entidad"] == "14"
        assert p["municipio"] == "039"
        # La clase de 6 dígitos va en la posición de su nivel; los niveles
        # superiores quedan en 0 para no contradecirla.
        assert p["subrama"] == clase
        assert p["sector"] == p["subsector"] == p["rama"] == "0"


def test_odontologia_consulta_las_clases_de_consultorios_dentales(client, monkeypatch):
    """Los consultorios dentales tienen clases propias en el SCIAN."""
    urls = []
    _responder(monkeypatch, RespuestaFalsa(200, []), capturadas=urls)
    client.get(
        "/directorio-proveedores/fuera-de-red",
        params={"cod_ent": "JC", "especialidad": "Odontología"},
        headers=_admin(client),
    )
    assert [_parametros(u)["subrama"] for u in urls] == list(
        denue_service.CLASES_POR_TIPO["dental"]
    )


def test_el_token_viaja_pero_no_se_registra_en_el_log(client, monkeypatch, caplog):
    import logging

    urls = []
    _responder(monkeypatch, RespuestaFalsa(500), capturadas=urls)
    with caplog.at_level(logging.WARNING, logger="denue_service"):
        r = client.get(
            "/directorio-proveedores/fuera-de-red",
            params={"cod_ent": "JC", "especialidad": "cardiologia"},
            headers=_admin(client),
        )
    assert r.status_code == 502
    assert "token-de-prueba" in urls[0], "el token sí debe ir en la petición"
    registros = [x.getMessage() for x in caplog.records if x.name == "denue_service"]
    assert registros, "debió registrarse el error"
    assert not any("token-de-prueba" in m for m in registros), "el token NO debe quedar en el log"


# ---------- Errores del servicio ----------

def test_sin_token_configurado_responde_503(client, monkeypatch):
    monkeypatch.setenv("DENUE_TOKEN", "")
    from app.config import get_settings

    get_settings.cache_clear()

    r = client.get(
        "/directorio-proveedores/fuera-de-red",
        params={"cod_ent": "JC", "especialidad": "cardiologia"},
        headers=_admin(client),
    )
    assert r.status_code == 503
    assert "token" in r.json()["detail"].lower()


def test_token_invalido_responde_502_con_mensaje_claro(client, monkeypatch):
    _responder(monkeypatch, RespuestaFalsa(401))
    r = client.get(
        "/directorio-proveedores/fuera-de-red",
        params={"cod_ent": "JC", "especialidad": "cardiologia"},
        headers=_admin(client),
    )
    assert r.status_code == 502
    assert "token" in r.json()["detail"].lower()


def test_timeout_del_inegi_responde_502(client, monkeypatch):
    def fake_get(url, **kwargs):
        raise denue_service.httpx.TimeoutException("tardó demasiado")
    monkeypatch.setattr(denue_service.httpx, "get", fake_get)

    r = client.get(
        "/directorio-proveedores/fuera-de-red",
        params={"cod_ent": "JC", "especialidad": "cardiologia"},
        headers=_admin(client),
    )
    assert r.status_code == 502
    assert "tardó" in r.json()["detail"]


def test_respuesta_que_no_es_json_responde_502(client, monkeypatch):
    _responder(monkeypatch, RespuestaFalsa(200, texto="<html>mantenimiento</html>"))
    r = client.get(
        "/directorio-proveedores/fuera-de-red",
        params={"cod_ent": "JC", "especialidad": "cardiologia"},
        headers=_admin(client),
    )
    assert r.status_code == 502


def test_entidad_fuera_del_catalogo_responde_400(client, monkeypatch):
    _responder(monkeypatch, RespuestaFalsa(200, [FILA_DENUE]))
    r = client.get(
        "/directorio-proveedores/fuera-de-red",
        params={"cod_ent": "ZZ", "especialidad": "cardiologia"},
        headers=_admin(client),
    )
    assert r.status_code == 400


def test_especialidad_demasiado_corta_se_rechaza(client):
    r = client.get(
        "/directorio-proveedores/fuera-de-red",
        params={"cod_ent": "JC", "especialidad": "ca"},
        headers=_admin(client),
    )
    assert r.status_code == 422


# ---------- Permisos ----------

def test_proveedor_y_administrador_pueden_buscar_fuera_de_la_red(client, monkeypatch):
    _responder(monkeypatch, RespuestaFalsa(200, [FILA_DENUE]))
    for headers in (_admin(client), _proveedor(client)):
        r = client.get(
            "/directorio-proveedores/fuera-de-red",
            params={"cod_ent": "JC", "especialidad": "cardiologia"},
            headers=headers,
        )
        assert r.status_code == 200


def test_cabina_no_puede_buscar_fuera_de_la_red(client, monkeypatch):
    _responder(monkeypatch, RespuestaFalsa(200, [FILA_DENUE]))
    r = client.get(
        "/directorio-proveedores/fuera-de-red",
        params={"cod_ent": "JC", "especialidad": "cardiologia"},
        headers=_cabina(client),
    )
    assert r.status_code == 403


def test_sin_sesion_no_se_puede_buscar(client):
    r = client.get(
        "/directorio-proveedores/fuera-de-red",
        params={"cod_ent": "JC", "especialidad": "cardiologia"},
    )
    assert r.status_code == 401


# ---------- Nada se guarda ----------

def test_la_busqueda_no_toca_el_padron_ni_las_citas(client, monkeypatch):
    """Decisión del usuario (2026-10-20): consulta en vivo, sin persistir."""
    _responder(monkeypatch, RespuestaFalsa(200, [FILA_DENUE]))
    headers = _admin(client)
    client.get(
        "/directorio-proveedores/fuera-de-red",
        params={"cod_ent": "JC", "especialidad": "cardiologia"},
        headers=headers,
    )
    assert client.get("/directorio-proveedores", headers=headers).json() == []
    assert client.get("/directorio-proveedores/citas", headers=headers).json() == []
