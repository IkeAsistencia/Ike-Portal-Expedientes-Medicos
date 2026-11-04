"""
Prueba de humo: NO requiere un SQL Server real. Se sustituyen
call_procedure / call_procedure_write por datos falsos (monkeypatch).

Ejecutar con:
    pytest tests/test_smoke.py -v
"""
import datetime

import pytest
from fastapi.testclient import TestClient

import app.repositories.auth_repo as auth_repo_module
import app.repositories.catalogos_repo as catalogos_repo_module
import app.repositories.expedientes_repo as expedientes_repo_module
import app.repositories.seguimiento_repo as seguimiento_repo_module
from app.main import app


EXPEDIENTES_DEMO = [
    {
        "Expediente": 1001,
        "Cuenta": "Cuenta Demo",
        "TipoServicio": "Servicio Médico",
        "TipoSubservicio": "Consulta Externa",
        "NombreTitular": "Juan Pérez López",
        "NombrePaciente": "Paciente de Prueba",
        "Especialidad": "Medicina General",
        "Entidad": "Campeche",
        "Municipio": "Campeche",
        "FechaAperturaServicio": datetime.date(2026, 8, 1),
        "FechaAperturaCompleta": datetime.datetime(2026, 8, 1, 8, 0, 0),
        "ClSubServicio": 383,
        "FechaAsignacionProveedor": datetime.date(2026, 8, 1),
        "FechaCita": datetime.date(2026, 8, 3),
        "Telefono": "9811234567",
        "Email": "paciente.demo@example.com",
    },
    {
        "Expediente": 1002,
        "Cuenta": "Cuenta Demo",
        "TipoServicio": "Servicio Médico",
        "TipoSubservicio": "Hospitalización",
        "NombreTitular": "María García Ruiz",
        "NombrePaciente": "Paciente Dos",
        "Especialidad": "Pediatría",
        "Entidad": "Yucatán",
        "Municipio": "Mérida",
        "FechaAperturaServicio": datetime.date(2026, 8, 2),
        "FechaAperturaCompleta": datetime.datetime(2026, 8, 2, 8, 0, 0),
        "ClSubServicio": 377,
        "FechaAsignacionProveedor": None,
        "FechaCita": None,
        "Telefono": "9997654321",
        "Email": "paciente2.demo@example.com",
    },
    {
        # Simula un expediente cuyo subservicio no tiene fila en ninguna de
        # las fuentes (S2_ReferciasMedicas / s2_cPuntoVision / Check_Up) --
        # desde que esos JOIN pasaron a LEFT, NombrePaciente puede venir NULL.
        "Expediente": 1003,
        "Cuenta": "Cuenta Demo",
        "TipoServicio": "Servicio Médico",
        "TipoSubservicio": "Otro Subservicio",
        "NombreTitular": "Carlos Ruiz Soto",
        "NombrePaciente": None,
        "Especialidad": None,
        "Entidad": None,
        "Municipio": None,
        "FechaAperturaServicio": datetime.date(2026, 8, 3),
        "FechaAperturaCompleta": datetime.datetime(2026, 8, 3, 8, 0, 0),
        "ClSubServicio": 999,  # subservicio fuera de los 8 que maneja el SP -- sin grupo de semáforo
        "FechaAsignacionProveedor": None,
        "FechaCita": None,
        "Telefono": None,
        "Email": None,
    },
]


def fake_call_procedure(sp_name, params=None):
    if sp_name == "dbo.ST_CP_ObtenerExpedientesSinProveedorMedico":
        if params and params.get("clExpediente"):
            # Búsqueda puntual por clave: nunca debe ir acotada por fecha,
            # servicio/subservicio ni cuenta.
            assert params.get("fechaInicio") is None
            assert params.get("fechaFin") is None
            assert params.get("clServicio") is None
            assert params.get("clSubServicio") is None
            assert params.get("Cuenta") == []
            return [e for e in EXPEDIENTES_DEMO if e["Expediente"] == params["clExpediente"]]
        return EXPEDIENTES_DEMO
    if sp_name == "dbo.ST_CP_ObtenerCatalogoServicio":
        return [{"clServicio": 4, "dsServicio": "Servicio Médico"}]
    if sp_name == "dbo.ST_CP_ObtenerServicioMedico":
        assert params.get("clServicio") == 4
        return [{"clSubServicio": 377, "dsSubServicio": "Consulta Externa"}]
    if sp_name == "dbo.ST_CP_ObtenerCatalogoCuentas":
        return [{"clCuenta": 2819, "Nombre": "Cuenta Demo"}]
    if sp_name == "dbo.sp_S2_BuscaCuenta":
        return [{"clCuenta": 2819, "Nombre": "Cuenta Demo"}]
    if sp_name == "dbo.ST_CP_ObtenerExpedientesSinRespuestaProveedor":
        horas = params.get("horasMinimas")
        assert horas == 8
        return [
            {
                "Expediente": 2001,
                "Cuenta": "Cuenta Demo",
                "NombrePaciente": "Paciente Naranja",
                "FechaApertura": datetime.date(2026, 8, 1),
                "FechaAsignacionProveedor": datetime.date(2026, 8, 1),
                "HorasSinRespuesta": 10,
            },
            {
                "Expediente": 2002,
                "Cuenta": "Cuenta Demo",
                "NombrePaciente": "Paciente Rojo",
                "FechaApertura": datetime.date(2026, 7, 30),
                "FechaAsignacionProveedor": datetime.date(2026, 7, 30),
                "HorasSinRespuesta": 30,
            },
        ]
    if sp_name == "dbo.sp_EncriptDesEncriptPassword":
        if params.get("pUsuario") == "usr_inactivo":
            return [{"clUsrApp": 55, "Nombre": "Usuario Inactivo", "Activo": False}]
        if params.get("pUsuario") == "ijimenez" and params.get("pContraseña") == "clave123":
            return [{"clUsrApp": 42, "Nombre": "Ignacio Jiménez", "Activo": True}]
        return []  # credenciales inválidas
    raise AssertionError(f"SP inesperado: {sp_name} / params={params}")


# Lo que cada prueba mandó a dbo.ST_CP_RegistrarSeguimiento (se limpia en el fixture).
OBSERVACIONES_ENVIADAS_A_BITACORA: list[str] = []


def fake_call_procedure_write(sp_name, params=None):
    if sp_name == "dbo.ST_CP_RegistrarSeguimiento":
        OBSERVACIONES_ENVIADAS_A_BITACORA.append(params["Observaciones"])
        # 42 = viene de una sesión SISE legada (clUsrApp real del token);
        # 0 = placeholder para sesiones RFC (ver CL_USR_APP_PLACEHOLDER_RFC).
        assert params["clUsrApp"] in (42, 0)
        return [{"clSeguimiento": 1, "FechaRegistro": datetime.datetime.now()}]
    raise AssertionError(f"SP inesperado: {sp_name} / params={params}")


@pytest.fixture(autouse=True)
def _patch_sql_server(monkeypatch):
    monkeypatch.setattr(expedientes_repo_module, "call_procedure", fake_call_procedure)
    monkeypatch.setattr(catalogos_repo_module, "call_procedure", fake_call_procedure)
    monkeypatch.setattr(auth_repo_module, "call_procedure", fake_call_procedure)
    monkeypatch.setattr(seguimiento_repo_module, "call_procedure_write", fake_call_procedure_write)

    # calentar_pool() del lifespan (app/main.py) intenta una conexión real a
    # SQL Server al arrancar -- contra el DB_SERVER falso de las pruebas se
    # iría al timeout en cada test. Esta suite no requiere SQL Server real.
    import app.main as main_module

    monkeypatch.setattr(main_module, "calentar_pool", lambda: None)

    # El rate limiter de /auth (app/core/rate_limit.py) guarda su conteo en
    # memoria del proceso -- sin esto, pruebas que hacen login varias veces
    # (o varias pruebas seguidas con el mismo usuario) chocarían entre sí.
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
    # Las pruebas usan el login legado (usuario SISE) para obtener tokens;
    # en la app real está apagado por default (ver app/config.py).
    monkeypatch.setenv("LOGIN_LEGADO_HABILITADO", "true")
    # Las pruebas deben quedar "simuladas" sin importar lo que tenga el .env
    # local de quien las corre -- si no, correr pytest puede mandar correos
    # reales (con las credenciales SMTP reales del .env) sin que nadie lo pida.
    monkeypatch.setenv("SMTP_HOST", "")
    monkeypatch.setenv("SMTP_USER", "")
    monkeypatch.setenv("SMTP_PASSWORD", "")
    monkeypatch.setenv("SMTP_REMITENTE", "")
    monkeypatch.setenv("SMTP_DESTINATARIO_PRUEBA", "")

    from app.config import get_settings

    get_settings.cache_clear()
    OBSERVACIONES_ENVIADAS_A_BITACORA.clear()

    with TestClient(app) as c:
        yield c


def _login(client, usuario="ijimenez", password="clave123"):
    return client.post("/auth/login", json={"usuario": usuario, "password": password})


def _auth_headers(client):
    r = _login(client)
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _auth_headers_proveedor(client):
    """Sesión RFC real de perfil Proveedor (no SISE), para probar los 403 del corte."""
    import app.repositories.accesos_repo as accesos_repo_module

    accesos_repo_module.alta_acceso("RFCPROTEST", "Proveedor de Prueba", accesos_repo_module.PERFIL_PROVEEDOR, "Ciudad de México")
    accesos_repo_module.crear_password("RFCPROTEST", "Proveedor2024")
    r = client.post("/auth/rfc/login", json={"rfc": "RFCPROTEST", "password": "Proveedor2024"})
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _auth_headers_admin(client):
    """Sesión RFC real de perfil Administrador, para probar /admin/accesos."""
    import app.repositories.accesos_repo as accesos_repo_module

    accesos_repo_module.alta_acceso("RFCADMTEST", "Admin de Prueba", accesos_repo_module.PERFIL_ADMINISTRADOR)
    accesos_repo_module.crear_password("RFCADMTEST", "Admin2024xx")
    r = client.post("/auth/rfc/login", json={"rfc": "RFCADMTEST", "password": "Admin2024xx"})
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _auth_headers_cabina(client):
    """Sesión RFC real de perfil Cabina (no SISE)."""
    import app.repositories.accesos_repo as accesos_repo_module

    accesos_repo_module.alta_acceso("RFCCABTEST", "Cabina de Prueba", accesos_repo_module.PERFIL_CABINA)
    accesos_repo_module.crear_password("RFCCABTEST", "Cabina2024xx")
    r = client.post("/auth/rfc/login", json={"rfc": "RFCCABTEST", "password": "Cabina2024xx"})
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_login_legado_apagado_por_default(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("LOGIN_LEGADO_HABILITADO", "false")
    get_settings.cache_clear()
    r = _login(client)
    assert r.status_code == 404
    # El login por RFC sigue funcionando.
    assert "Authorization" in _auth_headers_cabina(client)


def _request_con(xff, host="10.0.0.9"):
    from types import SimpleNamespace

    headers = {"x-forwarded-for": xff} if xff is not None else {}
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=host))


def test_ip_cliente_segun_proxies_confiables(client, monkeypatch):
    from app.config import get_settings
    from app.core.red import ip_cliente

    def con_proxies(n):
        monkeypatch.setenv("PROXIES_CONFIABLES", str(n))
        get_settings.cache_clear()

    # Un proxy (ALB solo o nginx): la IP real es la última; lo anterior lo
    # pudo escribir el usuario para falsear su IP.
    con_proxies(1)
    assert ip_cliente(_request_con("1.1.1.1, 200.10.10.10")) == "200.10.10.10"
    assert ip_cliente(_request_con("200.10.10.10")) == "200.10.10.10"
    # CloudFront + ALB: la penúltima es la del usuario, la última es CloudFront.
    con_proxies(2)
    assert ip_cliente(_request_con("1.1.1.1, 200.10.10.10, 130.176.0.5")) == "200.10.10.10"
    # Sin proxy: se ignora el encabezado.
    con_proxies(0)
    assert ip_cliente(_request_con("1.1.1.1")) == "10.0.0.9"
    # Sin encabezado: la IP de la conexión.
    con_proxies(1)
    assert ip_cliente(_request_con(None)) == "10.0.0.9"


def test_portal_se_sirve_en_la_raiz(client):
    r = client.get("/")
    assert r.status_code == 200
    assert '<script type="module" src="js/app.js">' in r.text

    # Los módulos deben salir como JavaScript: con "nosniff", un .js servido
    # como text/plain (pasa en algunos Windows) el navegador no lo ejecuta.
    r = client.get("/js/app.js")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/javascript")


def test_portal_no_tapa_los_endpoints(client):
    # El mount del frontend en "/" va al final: las rutas de la API ganan.
    r = client.get("/expedientes")
    assert r.status_code == 401


def test_login_ok(client):
    r = _login(client)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["cl_usr_app"] == 42
    assert data["nombre"] == "Ignacio Jiménez"
    assert data["token_type"] == "bearer"
    assert data["access_token"]


def test_login_credenciales_invalidas(client):
    r = _login(client, usuario="ijimenez", password="incorrecta")
    assert r.status_code == 401


def test_login_usuario_inactivo(client):
    r = _login(client, usuario="usr_inactivo", password="clave123")
    assert r.status_code == 403
    assert r.json()["detail"] == "Usuario sin permisos o inactivo, valide con el Supervisor"


def test_login_password_excede_limite_del_sp(client):
    # 14 caracteres: válido para el campo de UI (máx. 20) pero excede lo
    # que soporta el SP legado (varchar(10)) -> debe fallar explícito.
    r = _login(client, usuario="ijimenez", password="clave-de-14ch")
    assert r.status_code == 401
    assert "excede el límite" in r.json()["detail"]


def test_expedientes_requiere_login(client):
    r = client.get("/expedientes")
    assert r.status_code == 401


def test_listar_expedientes_autenticado(client):
    headers = _auth_headers(client)
    r = client.get("/expedientes", params={"cl_expediente": 1001}, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data[0]["expediente"] == 1001
    assert data[0]["estatus"] == "Abierto"
    assert data[0]["tipo_servicio"] == "Servicio Médico"
    assert data[0]["nombre_titular"] == "Juan Pérez López"
    assert data[0]["email"] == "paciente.demo@example.com"


def test_listar_expedientes_nombre_paciente_nulo_no_truena(client):
    """
    Desde que S2_ReferciasMedicas / s2_cPuntoVision / Check_Up pasaron a LEFT
    JOIN en dbo.ST_CP_ObtenerExpedientesSinProveedorMedico, un expediente sin fila
    en ninguna de esas fuentes llega con NombrePaciente en NULL -- antes
    tronaba con un ValidationError de Pydantic porque el campo era obligatorio.
    """
    headers = _auth_headers(client)
    r = client.get("/expedientes", params={"cl_expediente": 1003}, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data[0]["expediente"] == 1003
    assert data[0]["nombre_paciente"] is None


def test_listar_expedientes_filtro_servicio_subservicio(client):
    headers = _auth_headers(client)
    r = client.get(
        "/expedientes",
        params={"cl_servicio": 4, "cl_subservicio": 377},
        headers=headers,
    )
    assert r.status_code == 200, r.text


def test_listar_expedientes_rango_fechas_dentro_del_mes(client):
    headers = _auth_headers(client)
    hoy = datetime.date.today()
    inicio = hoy - datetime.timedelta(days=10)
    fin = hoy - datetime.timedelta(days=3)
    r = client.get(
        "/expedientes",
        params={"fecha_inicio": inicio.isoformat(), "fecha_fin": fin.isoformat()},
        headers=headers,
    )
    assert r.status_code == 200, r.text


def test_listar_expedientes_rango_fechas_dentro_de_3_meses(client):
    headers = _auth_headers(client)
    hoy = datetime.date.today()
    inicio = hoy - datetime.timedelta(days=60)
    fin = hoy - datetime.timedelta(days=5)
    r = client.get(
        "/expedientes",
        params={"fecha_inicio": inicio.isoformat(), "fecha_fin": fin.isoformat()},
        headers=headers,
    )
    assert r.status_code == 200, r.text


def test_listar_expedientes_rango_fechas_excede_3_meses(client):
    headers = _auth_headers(client)
    hoy = datetime.date.today()
    inicio = hoy - datetime.timedelta(days=10)  # reciente, no choca con el piso de antigüedad
    fin = inicio + datetime.timedelta(days=100)  # el span sí excede los 3 meses
    r = client.get(
        "/expedientes",
        params={"fecha_inicio": inicio.isoformat(), "fecha_fin": fin.isoformat()},
        headers=headers,
    )
    assert r.status_code == 400
    assert "no puede ser mayor a 3 meses" in r.json()["detail"]


def test_listar_expedientes_permite_buscar_fechas_viejas_dentro_del_rango(client):
    """
    La regla de 3 meses NO prohíbe buscar años atrás (ej. 2025) -- solo
    limita el span entre fecha_inicio y fecha_fin, no la antigüedad.
    """
    headers = _auth_headers(client)
    r = client.get(
        "/expedientes",
        params={"fecha_inicio": "2025-01-01", "fecha_fin": "2025-02-01"},
        headers=headers,
    )
    assert r.status_code == 200, r.text


def test_listar_expedientes_solo_fecha_fin_exige_fecha_inicio(client):
    """Si solo se manda fecha_fin (sin fecha_inicio), debe rechazarse."""
    headers = _auth_headers(client)
    hoy = datetime.date.today()
    fin = hoy - datetime.timedelta(days=1)
    r = client.get(
        "/expedientes",
        params={"fecha_fin": fin.isoformat()},
        headers=headers,
    )
    assert r.status_code == 400
    assert "fecha inicio" in r.json()["detail"]


def test_listar_expedientes_solo_fecha_inicio_exige_fecha_fin(client):
    """
    Si solo se manda fecha_inicio (ej. "2022") sin fecha_fin, debe rechazarse --
    de lo contrario la regla de 3 meses se brinca por completo y la consulta
    queda sin límite superior.
    """
    headers = _auth_headers(client)
    r = client.get(
        "/expedientes",
        params={"fecha_inicio": "2022-01-01"},
        headers=headers,
    )
    assert r.status_code == 400
    assert "fecha fin" in r.json()["detail"]


def test_listar_expedientes_sin_fechas_no_truena(client):
    """Sin fechas, el backend acota solo a los últimos 3 meses (no debe fallar)."""
    headers = _auth_headers(client)
    r = client.get("/expedientes", headers=headers)
    assert r.status_code == 200, r.text


def test_listar_expedientes_por_clave_ignora_regla_de_fechas(client):
    """
    Buscar por número de expediente es una clave exacta -- no debe exigir
    fecha_fin aunque falte, ni acotarse a los últimos 3 meses (fake_call_procedure
    valida que fechaInicio/fechaFin viajen en None cuando hay clExpediente).
    """
    headers = _auth_headers(client)
    r = client.get(
        "/expedientes",
        params={"cl_expediente": 1001},
        headers=headers,
    )
    assert r.status_code == 200, r.text


def test_listar_expedientes_por_clave_con_fecha_inicio_suelta_no_exige_fecha_fin(client):
    """
    Aun si además se manda fecha_inicio sin fecha_fin, la búsqueda por clave
    no debe rechazarse -- el número de expediente manda sobre el filtro de fechas.
    """
    headers = _auth_headers(client)
    r = client.get(
        "/expedientes",
        params={"cl_expediente": 1001, "fecha_inicio": "2022-01-01"},
        headers=headers,
    )
    assert r.status_code == 200, r.text


def test_listar_expedientes_fecha_fin_anterior_a_inicio(client):
    headers = _auth_headers(client)
    hoy = datetime.date.today()
    inicio = hoy - datetime.timedelta(days=3)
    fin = hoy - datetime.timedelta(days=10)
    r = client.get(
        "/expedientes",
        params={"fecha_inicio": inicio.isoformat(), "fecha_fin": fin.isoformat()},
        headers=headers,
    )
    assert r.status_code == 400
    assert "no puede ser anterior" in r.json()["detail"]


def test_catalogo_servicios(client):
    headers = _auth_headers(client)
    r = client.get("/catalogos/servicios", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json() == [{"clave": 4, "descripcion": "Servicio Médico"}]


def test_catalogo_subservicios(client):
    headers = _auth_headers(client)

    # cl_servicio es opcional (default = 4, único Servicio que existe)
    r = client.get("/catalogos/subservicios", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json() == [{"clave": 377, "descripcion": "Consulta Externa"}]

    r = client.get("/catalogos/subservicios", params={"cl_servicio": 4}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json() == [{"clave": 377, "descripcion": "Consulta Externa"}]


def test_catalogo_cuentas(client):
    headers = _auth_headers(client)
    r = client.get("/catalogos/cuentas", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json() == [{"clave": 2819, "descripcion": "Cuenta Demo"}]


def test_buscar_cuentas_valida_min_3_y_alfabetico(client):
    headers = _auth_headers(client)

    r = client.get("/catalogos/cuentas/buscar", params={"texto": "Cu"}, headers=headers)
    assert r.status_code == 422

    r = client.get("/catalogos/cuentas/buscar", params={"texto": "Cue123"}, headers=headers)
    assert r.status_code == 200
    assert r.json() == []

    r = client.get("/catalogos/cuentas/buscar", params={"texto": "Cuenta Demo"}, headers=headers)
    assert r.status_code == 200
    assert r.json() == [{"cl_cuenta": 2819, "nombre": "Cuenta Demo"}]


def test_actualizar_seguimiento_requiere_login(client):
    r = client.post("/seguimiento/actualizar", json={"cl_expediente": 1001, "comentario": "algo"})
    assert r.status_code == 401


def test_actualizar_seguimiento_vacio_falla(client):
    headers = _auth_headers(client)
    r = client.post(
        "/seguimiento/actualizar",
        json={"cl_expediente": 1001, "comentario": "   "},
        headers=headers,
    )
    assert r.status_code == 400


def test_actualizar_seguimiento_comentario_corto_falla(client):
    """El comentario del Proveedor debe tener al menos 50 caracteres para considerarse lleno."""
    headers = _auth_headers(client)
    r = client.post(
        "/seguimiento/actualizar",
        json={"cl_expediente": 1001, "comentario": "Comentario corto."},
        headers=headers,
    )
    assert r.status_code == 400
    assert "50 caracteres" in r.json()["detail"]


def test_actualizar_seguimiento_ok_usa_usr_app_del_token(client):
    headers = _auth_headers(client)
    r = client.post(
        "/seguimiento/actualizar",
        json={
            "cl_expediente": 1001,
            "comentario": "Se contactó al proveedor y se confirmó la atención del paciente sin novedad.",
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["clSeguimiento"] == 1


def test_actualizar_estatus_y_se_refleja_en_listado(client):
    headers = _auth_headers(client)
    r = client.post(
        "/seguimiento/estatus",
        json={"cl_expediente": 1001, "estatus": "Seguimiento Proveedor"},
        headers=headers,
    )
    assert r.status_code == 200, r.text

    r = client.get("/expedientes", params={"cl_expediente": 1001}, headers=headers)
    assert r.json()[0]["estatus"] == "Seguimiento Proveedor"


def test_enviar_correo_proveedores_requiere_seleccion(client):
    headers = _auth_headers(client)
    r = client.post("/expedientes/enviar-correo-proveedores", json={"expedientes": []}, headers=headers)
    assert r.status_code == 422  # min_length=1 en el esquema


def test_enviar_correo_proveedores_ok(client):
    headers = _auth_headers(client)
    r = client.post(
        "/expedientes/enviar-correo-proveedores",
        json={"expedientes": [1001]},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["enviados"] == 1
    assert data["expedientes"] == [1001]


def test_enviar_correo_proveedores_deja_historial(client):
    """Queda registro de quién mandó el correo, a quién y de qué expedientes."""
    import app.repositories.accesos_repo as accesos_repo_module
    import app.repositories.correos_enviados_repo as correos_enviados_repo_module

    # 1001 es de Campeche: sin un proveedor ahí, no hay a quién mandarle.
    accesos_repo_module.alta_acceso(
        "PROVCAM001", "Proveedor Campeche", accesos_repo_module.PERFIL_PROVEEDOR, "Campeche", "campeche@example.com"
    )
    headers = _auth_headers(client)
    r = client.post(
        "/expedientes/enviar-correo-proveedores", json={"expedientes": [1001]}, headers=headers
    )
    assert r.status_code == 200, r.text

    historial = correos_enviados_repo_module.listar_por_expediente(1001)
    assert len(historial) == 1
    assert historial[0]["tipo"] == "nuevo"
    assert historial[0]["expedientes"] == [1001]
    assert historial[0]["rfc_envio"]
    assert historial[0]["destinatario"] == "campeche@example.com"


def test_correos_enviados_solo_administrador(client):
    headers = _auth_headers(client)  # Cabina
    r = client.get("/correos-enviados", headers=headers)
    assert r.status_code == 403


def test_correos_enviados_lista_para_administrador(client):
    headers_cabina = _auth_headers(client)
    client.post("/expedientes/enviar-correo-proveedores", json={"expedientes": [1001]}, headers=headers_cabina)

    headers_admin = _auth_headers_admin(client)
    r = client.get("/correos-enviados", headers=headers_admin)
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data) == 1
    assert data[0]["expedientes"] == [1001]
    assert data[0]["tipo"] == "nuevo"


def test_correos_enviados_filtra_por_expediente(client):
    headers_cabina = _auth_headers(client)
    client.post("/expedientes/enviar-correo-proveedores", json={"expedientes": [1001]}, headers=headers_cabina)

    headers_admin = _auth_headers_admin(client)
    r = client.get("/correos-enviados", params={"cl_expediente": 9999}, headers=headers_admin)
    assert r.status_code == 200, r.text
    assert r.json() == []


def test_correos_enviados_muestra_nombre_no_rfc(client):
    """El historial debe mostrar el nombre de quien mandó el correo, no su RFC a secas."""
    headers_cabina = _auth_headers_cabina(client)  # RFC "RFCCABTEST" -> nombre "Cabina de Prueba"
    r = client.post(
        "/expedientes/enviar-correo-proveedores", json={"expedientes": [1001]}, headers=headers_cabina
    )
    assert r.status_code == 200, r.text

    headers_admin = _auth_headers_admin(client)
    r = client.get("/correos-enviados", headers=headers_admin)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data[0]["rfc_envio"] == "RFCCABTEST"
    assert data[0]["nombre_envio"] == "Cabina de Prueba"


def test_enviar_correo_proveedores_rechaza_estatus_no_permitido(client):
    """Solo se puede mandar correo en 'Abierto' o 'En Espera de Respuesta'."""
    import app.repositories.estatus_repo as estatus_repo_module
    from app.schemas.expediente import EstatusExpediente

    estatus_repo_module.actualizar_estatus(1001, EstatusExpediente.SEGUIMIENTO_COORDINADOR, "RFCCABTEST")

    headers = _auth_headers(client)
    r = client.post(
        "/expedientes/enviar-correo-proveedores", json={"expedientes": [1001]}, headers=headers
    )
    assert r.status_code == 400, r.text
    assert "1001" in r.json()["detail"]


def test_enviar_correo_proveedores_rechaza_mezcla_de_estatus(client):
    """No se puede mandar un correo mezclando 'Abierto' con 'En Espera de Respuesta'."""
    import app.repositories.estatus_repo as estatus_repo_module
    from app.schemas.expediente import EstatusExpediente

    estatus_repo_module.actualizar_estatus(1002, EstatusExpediente.EN_ESPERA_RESPUESTA, "RFCCABTEST")
    # 1001 se queda en "Abierto" (default).

    headers = _auth_headers(client)
    r = client.post(
        "/expedientes/enviar-correo-proveedores", json={"expedientes": [1001, 1002]}, headers=headers
    )
    assert r.status_code == 400, r.text
    assert "mezclar" in r.json()["detail"]


def test_enviar_correo_proveedores_recordatorio_ok(client):
    """Una selección pareja de 'En Espera de Respuesta' sí se puede mandar (recordatorio)."""
    import app.repositories.estatus_repo as estatus_repo_module
    from app.schemas.expediente import EstatusExpediente

    estatus_repo_module.actualizar_estatus(1001, EstatusExpediente.EN_ESPERA_RESPUESTA, "RFCCABTEST")
    estatus_repo_module.actualizar_estatus(1002, EstatusExpediente.EN_ESPERA_RESPUESTA, "RFCCABTEST")

    headers = _auth_headers(client)
    r = client.post(
        "/expedientes/enviar-correo-proveedores", json={"expedientes": [1001, 1002]}, headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["enviados"] == 2


def test_generar_corte_requiere_seleccion(client):
    headers = _auth_headers(client)
    r = client.post("/expedientes/corte", json={"expedientes": []}, headers=headers)
    assert r.status_code == 422  # min_length=1 en el esquema


def test_generar_corte_no_cambia_estatus(client):
    """A diferencia de 'enviar-correo-proveedores', el corte es solo evidencia."""
    headers = _auth_headers_admin(client)
    r = client.post(
        "/expedientes/corte",
        json={"expedientes": [1001], "tipo_expediente": "normal"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 1
    assert data["expedientes"] == [1001]
    assert data["archivo_nombre"].endswith(".xlsx")

    r = client.get("/expedientes", params={"cl_expediente": 1001}, headers=headers)
    assert r.json()[0]["estatus"] == "Abierto"  # no cambió


def test_corte_descargar_devuelve_xlsx_valido(client):
    import openpyxl

    headers = _auth_headers_admin(client)
    r = client.post(
        "/expedientes/corte",
        json={"expedientes": [1001], "tipo_expediente": "anticipado"},
        headers=headers,
    )
    corte_id = r.json()["corte_id"]

    r = client.get(f"/expedientes/corte/{corte_id}/descargar", headers=headers)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")

    import io

    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    ws = wb.active
    assert ws["A1"].value == "Corte de Expedientes — Pago Anticipado"
    assert ws.cell(row=4, column=1).value == "Expediente"
    assert ws.cell(row=5, column=1).value == 1001
    # El estatus debe verse como texto plano ("Abierto"), no como el repr
    # del Enum de Python ("EstatusExpediente.ABIERTO").
    assert ws.cell(row=4, column=15).value == "Estado"
    assert ws.cell(row=5, column=15).value == "Abierto"
    # 1001 está "Abierto" en este test -> todavía no se le manda a nadie, así
    # que no hay coordinador/fecha de envío que mostrar (no es una regla por
    # estatus, es que de verdad no existe el dato).
    assert ws.cell(row=4, column=16).value == "Coordinador"
    assert ws.cell(row=5, column=16).value == "NA"
    assert ws.cell(row=4, column=17).value == "Fecha Envío a Proveedor"
    assert ws.cell(row=5, column=17).value == "NA"


def test_corte_enviar_marca_simulado_y_no_repite_archivo(client):
    headers = _auth_headers_admin(client)
    r = client.post("/expedientes/corte", json={"expedientes": [1001]}, headers=headers)
    corte_id = r.json()["corte_id"]

    r = client.post(
        f"/expedientes/corte/{corte_id}/enviar", json={"destinatario": "cabina@example.com"}, headers=headers
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["enviados"] == 1
    assert data["simulado"] is True  # no hay SMTP configurado en las pruebas
    assert data["destinatario"] == "cabina@example.com"


def test_corte_descargar_inexistente_404(client):
    headers = _auth_headers_admin(client)
    r = client.get("/expedientes/corte/9999/descargar", headers=headers)
    assert r.status_code == 404


def test_corte_prohibido_para_proveedor(client):
    headers = _auth_headers_proveedor(client)
    r = client.post("/expedientes/corte", json={"expedientes": [1001]}, headers=headers)
    assert r.status_code == 403


def test_corte_prohibido_para_cabina(client):
    """El jefe pidió que el corte quede exclusivo de Administrador."""
    headers = _auth_headers_cabina(client)
    r = client.post("/expedientes/corte", json={"expedientes": [1001]}, headers=headers)
    assert r.status_code == 403


def test_enviar_correo_proveedores_prohibido_para_administrador(client):
    headers = _auth_headers_admin(client)
    r = client.post(
        "/expedientes/enviar-correo-proveedores", json={"expedientes": [1001]}, headers=headers
    )
    assert r.status_code == 403


def test_generar_corte_exige_mismo_estatus(client):
    admin_headers = _auth_headers_admin(client)
    cabina_headers = _auth_headers_cabina(client)
    # 1001 queda "Abierto"; forzamos 1002 a "En Espera de Respuesta" para que difieran
    # (solo Cabina puede asignar ese estatus a mano, ver seguimiento.py).
    r = client.post(
        "/seguimiento/estatus",
        json={
            "cl_expediente": 1002,
            "estatus": "En Espera de Respuesta",
            "comentario": "Faltó información en la respuesta, favor de completarla.",
        },
        headers=cabina_headers,
    )
    assert r.status_code == 200, r.text

    r = client.post(
        "/expedientes/corte",
        json={"expedientes": [1001, 1002]},
        headers=admin_headers,
    )
    assert r.status_code == 400
    assert "mismo estatus" in r.json()["detail"]


def test_corte_en_espera_respuesta_incluye_rfc_y_fecha_envio(client):
    import io

    import openpyxl

    admin_headers = _auth_headers_admin(client)
    cabina_headers = _auth_headers_cabina(client)

    r = client.post(
        "/expedientes/enviar-correo-proveedores", json={"expedientes": [1001]}, headers=cabina_headers
    )
    assert r.status_code == 200, r.text

    r = client.post(
        "/expedientes/corte",
        json={"expedientes": [1001], "tipo_expediente": "anticipado"},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    corte_id = r.json()["corte_id"]

    r = client.get(f"/expedientes/corte/{corte_id}/descargar", headers=admin_headers)
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    ws = wb.active
    # Ya no es el RFC a secas -- se resuelve al nombre de la persona.
    assert ws.cell(row=5, column=16).value == "Cabina de Prueba"
    assert ws.cell(row=5, column=17).value is not None
    assert ws.cell(row=5, column=17).value != "NA"


def test_corte_mantiene_envio_original_aunque_el_estatus_avance(client):
    """
    El corte debe seguir mostrando quién y cuándo se mandó ORIGINALMENTE,
    aunque el expediente ya haya avanzado a otro estatus (ej. el proveedor
    ya respondió) -- no debe mostrar NA ni a quien hizo el cambio más
    reciente (ver correos_enviados_repo.obtener_envio_original).
    """
    import io

    import openpyxl

    admin_headers = _auth_headers_admin(client)
    cabina_headers = _auth_headers_cabina(client)
    proveedor_headers = _auth_headers_proveedor(client)  # perfil Proveedor real -- dispara el cambio a "Seguimiento Proveedor"

    r = client.post(
        "/expedientes/enviar-correo-proveedores", json={"expedientes": [1001]}, headers=cabina_headers
    )
    assert r.status_code == 200, r.text

    r = client.post(
        "/seguimiento/actualizar",
        json={
            "cl_expediente": 1001,
            "comentario": "Se contactó al proveedor y se confirmó la atención del paciente sin novedad.",
        },
        headers=proveedor_headers,
    )
    assert r.status_code == 200, r.text

    r = client.get("/expedientes", params={"cl_expediente": 1001}, headers=admin_headers)
    assert r.json()[0]["estatus"] == "Seguimiento Proveedor"

    r = client.post("/expedientes/corte", json={"expedientes": [1001]}, headers=admin_headers)
    assert r.status_code == 200, r.text
    corte_id = r.json()["corte_id"]

    r = client.get(f"/expedientes/corte/{corte_id}/descargar", headers=admin_headers)
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    ws = wb.active
    # Sigue siendo quien lo mandó originalmente (Cabina), no quien hizo el
    # último cambio de estatus (el proveedor, al responder).
    assert ws.cell(row=5, column=16).value == "Cabina de Prueba"
    assert ws.cell(row=5, column=17).value is not None
    assert ws.cell(row=5, column=17).value != "NA"


def test_alta_proveedor_requiere_correo(client):
    headers = _auth_headers_admin(client)
    r = client.post(
        "/admin/accesos",
        json={"rfc": "PROV000001", "nombre": "Proveedor Sin Correo", "perfil": 3, "entidad": "Jalisco"},
        headers=headers,
    )
    assert r.status_code == 422
    assert "correo" in r.text.lower()


def test_alta_proveedor_correo_invalido(client):
    headers = _auth_headers_admin(client)
    r = client.post(
        "/admin/accesos",
        json={
            "rfc": "PROV000002", "nombre": "Proveedor Correo Mal", "perfil": 3,
            "entidad": "Jalisco", "correo": "no-es-un-correo",
        },
        headers=headers,
    )
    assert r.status_code == 422


def test_alta_proveedor_con_entidad_y_correo_ok(client):
    headers = _auth_headers_admin(client)
    r = client.post(
        "/admin/accesos",
        json={
            "rfc": "PROV000003", "nombre": "Proveedor Válido", "perfil": 3,
            "entidad": "Jalisco", "correo": "proveedor@example.com",
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text

    accesos = client.get("/admin/accesos", headers=headers).json()
    registro = next(a for a in accesos if a["rfc"] == "PROV000003")
    assert registro["entidad"] == "Jalisco"
    assert registro["correo"] == "proveedor@example.com"


def test_alta_no_proveedor_guarda_na_en_entidad_y_correo(client):
    headers = _auth_headers_admin(client)
    r = client.post(
        "/admin/accesos",
        json={"rfc": "CABI000001", "nombre": "Cabina Sin Entidad", "perfil": 2},
        headers=headers,
    )
    assert r.status_code == 200, r.text

    accesos = client.get("/admin/accesos", headers=headers).json()
    registro = next(a for a in accesos if a["rfc"] == "CABI000001")
    assert registro["entidad"] == "NA"
    assert registro["correo"] == "NA"


def test_alta_administrador_exige_rfc_de_11_caracteres(client):
    headers = _auth_headers_admin(client)
    r = client.post(
        "/admin/accesos",
        json={"rfc": "ADMI000001", "nombre": "Admin Corto", "perfil": 1},
        headers=headers,
    )
    assert r.status_code == 422
    assert "11 caracteres" in r.text


def test_alta_administrador_con_homoclave_ok(client):
    headers = _auth_headers_admin(client)
    r = client.post(
        "/admin/accesos",
        json={"rfc": "ADMI000001Z", "nombre": "Admin Completo", "perfil": 1},
        headers=headers,
    )
    assert r.status_code == 200, r.text

    accesos = client.get("/admin/accesos", headers=headers).json()
    registro = next(a for a in accesos if a["rfc"] == "ADMI000001Z")
    assert registro["entidad"] == "NA"
    assert registro["correo"] == "NA"


def test_cambiar_entidad_de_proveedor_ok(client):
    headers = _auth_headers_admin(client)
    client.post(
        "/admin/accesos",
        json={
            "rfc": "PROV000004", "nombre": "Proveedor Cambio", "perfil": 3,
            "entidad": "Jalisco", "correo": "cambio@example.com",
        },
        headers=headers,
    )
    r = client.post("/admin/accesos/PROV000004/entidad", json={"entidad": "Yucatán"}, headers=headers)
    assert r.status_code == 200, r.text

    accesos = client.get("/admin/accesos", headers=headers).json()
    registro = next(a for a in accesos if a["rfc"] == "PROV000004")
    assert registro["entidad"] == "Yucatán"


def test_cambiar_entidad_entidad_invalida(client):
    headers = _auth_headers_admin(client)
    client.post(
        "/admin/accesos",
        json={
            "rfc": "PROV000005", "nombre": "Proveedor Cambio 2", "perfil": 3,
            "entidad": "Jalisco", "correo": "cambio2@example.com",
        },
        headers=headers,
    )
    r = client.post("/admin/accesos/PROV000005/entidad", json={"entidad": "Narnia"}, headers=headers)
    assert r.status_code == 422


def test_cambiar_entidad_prohibido_para_no_proveedor(client):
    headers = _auth_headers_admin(client)
    client.post(
        "/admin/accesos",
        json={"rfc": "CABI000002", "nombre": "Cabina Cambio", "perfil": 2},
        headers=headers,
    )
    r = client.post("/admin/accesos/CABI000002/entidad", json={"entidad": "Jalisco"}, headers=headers)
    assert r.status_code == 400


def test_cambiar_entidad_rfc_inexistente(client):
    headers = _auth_headers_admin(client)
    r = client.post("/admin/accesos/RFCNOEXISTE999/entidad", json={"entidad": "Jalisco"}, headers=headers)
    assert r.status_code == 404


def test_alta_rfc_formato_invalido(client):
    """El RFC debe ser exactamente 4 letras + 6 números (10 caracteres)."""
    headers = _auth_headers_admin(client)
    for rfc_malo in ["ABC123456", "ABCDE12345", "ABCD12345", "1234ABCDEF", "abcd123456!"]:
        r = client.post(
            "/admin/accesos",
            json={"rfc": rfc_malo, "nombre": "Alguien", "perfil": 2},
            headers=headers,
        )
        assert r.status_code == 422, f"{rfc_malo!r} debió rechazarse"


def test_alta_rfc_formato_valido_minusculas_se_normaliza(client):
    headers = _auth_headers_admin(client)
    r = client.post(
        "/admin/accesos",
        json={"rfc": "abcd123456", "nombre": "Alguien", "perfil": 2},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    accesos = client.get("/admin/accesos", headers=headers).json()
    assert any(a["rfc"] == "ABCD123456" for a in accesos)


def test_crear_password_exige_caracter_especial(client):
    import app.repositories.accesos_repo as accesos_repo_module

    accesos_repo_module.alta_acceso("RFCPWDTEST", "Prueba Password", accesos_repo_module.PERFIL_CABINA)

    r = client.post(
        "/auth/rfc/crear-password", json={"rfc": "RFCPWDTEST", "password": "SinEspecial1"}
    )
    assert r.status_code == 422

    r = client.post(
        "/auth/rfc/crear-password", json={"rfc": "RFCPWDTEST", "password": "ConEspecial1!"}
    )
    assert r.status_code == 200, r.text


def test_seguimiento_regresar_exige_comentario(client):
    headers = _auth_headers_cabina(client)
    r = client.post(
        "/seguimiento/estatus",
        json={"cl_expediente": 1001, "estatus": "En Espera de Respuesta"},
        headers=headers,
    )
    assert r.status_code == 400
    assert "comentario" in r.json()["detail"].lower()


def test_seguimiento_regresar_con_comentario_ok(client):
    headers = _auth_headers_cabina(client)
    r = client.post(
        "/seguimiento/estatus",
        json={
            "cl_expediente": 1001,
            "estatus": "En Espera de Respuesta",
            "comentario": "Falta el número de póliza, favor de agregarlo y volver a enviar.",
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text

    r = client.get("/expedientes", params={"cl_expediente": 1001}, headers=headers)
    assert r.json()[0]["estatus"] == "En Espera de Respuesta"

    r = client.get("/seguimiento/comentarios/1001", headers=headers)
    comentarios = r.json()
    encontrado = next(c for c in comentarios if "número de póliza" in c["comentario"])
    assert encontrado["rfc"] == "RFCCABTEST"
    assert encontrado["origen"] == "cabina"


def test_actualizar_seguimiento_guarda_origen_proveedor(client):
    headers = _auth_headers(client)
    client.post(
        "/seguimiento/actualizar",
        json={
            "cl_expediente": 1001,
            "comentario": "Se atendió al paciente correctamente sin ninguna novedad que reportar hoy.",
        },
        headers=headers,
    )
    r = client.get("/seguimiento/comentarios/1001", headers=headers)
    comentarios = r.json()
    encontrado = next(c for c in comentarios if "Se atendió al paciente" in c["comentario"])
    assert encontrado["origen"] == "proveedor"


def test_actualizar_seguimiento_proveedor_fuera_de_espera_respuesta_falla(client):
    """
    Proveedor solo puede ver/actualizar expedientes en 'En Espera de
    Respuesta'. Por default (sin estatus local) el expediente queda
    'Abierto', así que debe rechazarse.
    """
    headers = _auth_headers_proveedor(client)
    r = client.post(
        "/seguimiento/actualizar",
        json={
            "cl_expediente": 1001,
            "comentario": "Se atendió al paciente correctamente sin ninguna novedad que reportar hoy.",
        },
        headers=headers,
    )
    assert r.status_code == 400
    assert "en espera de respuesta" in r.json()["detail"].lower()


def test_actualizar_seguimiento_proveedor_no_puede_reenviar_dos_veces(client):
    """Tras el primer envío el expediente queda 'Seguimiento Proveedor' -- un segundo envío debe rechazarse."""
    import app.repositories.estatus_repo as estatus_repo_module
    from app.schemas.expediente import EstatusExpediente

    estatus_repo_module.actualizar_estatus(1001, EstatusExpediente.EN_ESPERA_RESPUESTA, "RFCCABTEST")

    headers = _auth_headers_proveedor(client)
    comentario = "Se atendió al paciente correctamente sin ninguna novedad que reportar hoy."
    r = client.post(
        "/seguimiento/actualizar",
        json={"cl_expediente": 1001, "comentario": comentario},
        headers=headers,
    )
    assert r.status_code == 200, r.text

    r = client.post(
        "/seguimiento/actualizar",
        json={"cl_expediente": 1001, "comentario": comentario},
        headers=headers,
    )
    assert r.status_code == 400


def test_pago_anticipado_default_no_marcado(client):
    headers = _auth_headers_cabina(client)
    r = client.get("/seguimiento/pago-anticipado/1001", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json() == {"es_anticipado": False, "bloqueado": False}


def test_pago_anticipado_marcar_prohibido_para_cabina(client):
    headers = _auth_headers_cabina(client)
    r = client.post("/seguimiento/pago-anticipado/1001", json={"es_anticipado": True}, headers=headers)
    assert r.status_code == 403


def test_pago_anticipado_proveedor_puede_marcar_y_desmarcar_antes_de_enviar(client):
    import app.repositories.estatus_repo as estatus_repo_module
    from app.schemas.expediente import EstatusExpediente

    # Proveedor solo puede marcar pago anticipado en expedientes que le
    # corresponde atender (ver _verificar_proveedor_puede_ver).
    estatus_repo_module.actualizar_estatus(1001, EstatusExpediente.EN_ESPERA_RESPUESTA, "RFCCABTEST")

    headers = _auth_headers_proveedor(client)
    r = client.post("/seguimiento/pago-anticipado/1001", json={"es_anticipado": True}, headers=headers)
    assert r.status_code == 200, r.text
    r = client.get("/seguimiento/pago-anticipado/1001", headers=headers)
    assert r.json() == {"es_anticipado": True, "bloqueado": False}

    r = client.post("/seguimiento/pago-anticipado/1001", json={"es_anticipado": False}, headers=headers)
    assert r.status_code == 200, r.text
    r = client.get("/seguimiento/pago-anticipado/1001", headers=headers)
    assert r.json() == {"es_anticipado": False, "bloqueado": False}


def test_pago_anticipado_se_bloquea_tras_primer_envio(client):
    import app.repositories.estatus_repo as estatus_repo_module
    from app.schemas.expediente import EstatusExpediente

    estatus_repo_module.actualizar_estatus(1001, EstatusExpediente.EN_ESPERA_RESPUESTA, "RFCCABTEST")

    headers = _auth_headers_proveedor(client)
    client.post("/seguimiento/pago-anticipado/1001", json={"es_anticipado": True}, headers=headers)

    comentario = "Se atendió al paciente correctamente sin ninguna novedad que reportar hoy."
    r = client.post(
        "/seguimiento/actualizar", json={"cl_expediente": 1001, "comentario": comentario}, headers=headers
    )
    assert r.status_code == 200, r.text

    r = client.get("/seguimiento/pago-anticipado/1001", headers=headers)
    assert r.json() == {"es_anticipado": True, "bloqueado": True}

    r = client.post("/seguimiento/pago-anticipado/1001", json={"es_anticipado": False}, headers=headers)
    assert r.status_code == 400


def test_seguimiento_de_cita_exige_marca_pago_anticipado(client):
    headers = _auth_headers_cabina(client)
    r = client.post(
        "/seguimiento/estatus",
        json={"cl_expediente": 1001, "estatus": "Seguimiento de Cita", "comentario": "Se acepta la cita."},
        headers=headers,
    )
    assert r.status_code == 400
    assert "pago anticipado" in r.json()["detail"].lower()


def test_seguimiento_de_cita_flujo_completo(client):
    import io

    import app.repositories.estatus_repo as estatus_repo_module
    from app.schemas.expediente import EstatusExpediente

    prov_headers = _auth_headers_proveedor(client)
    cabina_headers = _auth_headers_cabina(client)

    # Proveedor marca el expediente como pago anticipado y manda su primer comentario.
    estatus_repo_module.actualizar_estatus(1001, EstatusExpediente.EN_ESPERA_RESPUESTA, "RFCCABTEST")
    client.post("/seguimiento/pago-anticipado/1001", json={"es_anticipado": True}, headers=prov_headers)
    comentario1 = "Se atendió al paciente correctamente sin ninguna novedad que reportar hoy."
    r = client.post(
        "/seguimiento/actualizar", json={"cl_expediente": 1001, "comentario": comentario1}, headers=prov_headers
    )
    assert r.status_code == 200, r.text

    # Cabina revisa: la cita fue aceptada -> lo regresa como "Seguimiento de Cita".
    r = client.post(
        "/seguimiento/estatus",
        json={"cl_expediente": 1001, "estatus": "Seguimiento de Cita", "comentario": "Se acepta la cita."},
        headers=cabina_headers,
    )
    assert r.status_code == 200, r.text

    r = client.get("/seguimiento/comentarios/1001", headers=cabina_headers)
    encontrado = next(c for c in r.json() if "Se acepta la cita" in c["comentario"])
    assert encontrado["origen"] == "cabina"

    # Proveedor intenta mandar sin comprobante -> rechazado.
    comentario2 = "Se sube el comprobante de pago correspondiente a esta atencion medica."
    r = client.post(
        "/seguimiento/actualizar", json={"cl_expediente": 1001, "comentario": comentario2}, headers=prov_headers
    )
    assert r.status_code == 400
    assert "comprobante" in r.json()["detail"].lower()

    # Sube el comprobante y ahora sí puede mandar -> regresa a "Seguimiento Proveedor".
    r = client.post(
        "/seguimiento/comprobante",
        data={"cl_expediente": 1001},
        files={"archivo": ("comprobante.pdf", io.BytesIO(b"%PDF-1.4 contenido"), "application/pdf")},
        headers=prov_headers,
    )
    assert r.status_code == 200, r.text

    r = client.post(
        "/seguimiento/actualizar", json={"cl_expediente": 1001, "comentario": comentario2}, headers=prov_headers
    )
    assert r.status_code == 200, r.text

    r = client.get("/expedientes", params={"cl_expediente": 1001}, headers=cabina_headers)
    assert r.json()[0]["estatus"] == "Seguimiento Proveedor"


COMENTARIO_PROVEEDOR = "Se atendió al paciente correctamente sin ninguna novedad que reportar hoy."


def test_bitacora_recibe_encabezado_del_proveedor(client):
    import app.repositories.estatus_repo as estatus_repo_module
    from app.schemas.expediente import EstatusExpediente

    prov_headers = _auth_headers_proveedor(client)
    estatus_repo_module.actualizar_estatus(1001, EstatusExpediente.EN_ESPERA_RESPUESTA, "RFCCABTEST")
    r = client.post(
        "/seguimiento/actualizar", json={"cl_expediente": 1001, "comentario": COMENTARIO_PROVEEDOR}, headers=prov_headers
    )
    assert r.status_code == 200, r.text
    assert OBSERVACIONES_ENVIADAS_A_BITACORA[-1] == f"Proveedores --> Proveedor de Prueba\n{COMENTARIO_PROVEEDOR}"

    # La copia local (la que muestra el portal) va sin el encabezado, pero
    # trae el nombre para que el portal lo muestre igual que en el sistema central.
    r = client.get("/seguimiento/comentarios/1001", headers=prov_headers)
    comentario = next(c for c in r.json() if c["comentario"] == COMENTARIO_PROVEEDOR)
    assert comentario["nombre"] == "Proveedor de Prueba"
    assert comentario["rfc"] == "RFCPROTEST"


def test_bitacora_pago_anticipado_lleva_prefijo_pa(client):
    import app.repositories.estatus_repo as estatus_repo_module
    from app.schemas.expediente import EstatusExpediente

    prov_headers = _auth_headers_proveedor(client)
    estatus_repo_module.actualizar_estatus(1001, EstatusExpediente.EN_ESPERA_RESPUESTA, "RFCCABTEST")
    client.post("/seguimiento/pago-anticipado/1001", json={"es_anticipado": True}, headers=prov_headers)

    # Aunque el comentario llegue sin "PA-" (ej. lo borraron a mano), se agrega.
    r = client.post(
        "/seguimiento/actualizar", json={"cl_expediente": 1001, "comentario": COMENTARIO_PROVEEDOR}, headers=prov_headers
    )
    assert r.status_code == 200, r.text
    assert OBSERVACIONES_ENVIADAS_A_BITACORA[-1] == f"Proveedores --> Proveedor de Prueba\nPA-{COMENTARIO_PROVEEDOR}"


def test_bitacora_pago_anticipado_no_duplica_prefijo(client):
    import app.repositories.estatus_repo as estatus_repo_module
    from app.schemas.expediente import EstatusExpediente

    prov_headers = _auth_headers_proveedor(client)
    estatus_repo_module.actualizar_estatus(1001, EstatusExpediente.EN_ESPERA_RESPUESTA, "RFCCABTEST")
    client.post("/seguimiento/pago-anticipado/1001", json={"es_anticipado": True}, headers=prov_headers)
    r = client.post(
        "/seguimiento/actualizar",
        json={"cl_expediente": 1001, "comentario": "PA-" + COMENTARIO_PROVEEDOR},
        headers=prov_headers,
    )
    assert r.status_code == 200, r.text
    assert OBSERVACIONES_ENVIADAS_A_BITACORA[-1] == f"Proveedores --> Proveedor de Prueba\nPA-{COMENTARIO_PROVEEDOR}"


def test_bitacora_recibe_encabezado_del_coordinador(client):
    import app.repositories.estatus_repo as estatus_repo_module
    from app.schemas.expediente import EstatusExpediente

    cabina_headers = _auth_headers_cabina(client)
    estatus_repo_module.actualizar_estatus(1001, EstatusExpediente.SEGUIMIENTO_PROVEEDOR, "RFCPROTEST")
    r = client.post(
        "/seguimiento/estatus",
        json={"cl_expediente": 1001, "estatus": "En Espera de Respuesta", "comentario": "Falta el número de póliza."},
        headers=cabina_headers,
    )
    assert r.status_code == 200, r.text
    assert OBSERVACIONES_ENVIADAS_A_BITACORA[-1] == "Cabina Médica --> Cabina de Prueba\nFalta el número de póliza."

    r = client.get("/seguimiento/comentarios/1001", headers=cabina_headers)
    comentario = next(c for c in r.json() if c["origen"] == "cabina")
    assert comentario["nombre"] == "Cabina de Prueba"


def test_bitacora_rechaza_comentario_que_no_cabe_con_encabezado(client):
    import app.repositories.estatus_repo as estatus_repo_module
    from app.schemas.expediente import EstatusExpediente

    prov_headers = _auth_headers_proveedor(client)
    estatus_repo_module.actualizar_estatus(1001, EstatusExpediente.EN_ESPERA_RESPUESTA, "RFCCABTEST")
    r = client.post(
        "/seguimiento/actualizar", json={"cl_expediente": 1001, "comentario": "x" * 1500}, headers=prov_headers
    )
    assert r.status_code == 400
    assert "demasiado largo" in r.json()["detail"]
    assert OBSERVACIONES_ENVIADAS_A_BITACORA == []


def test_configuracion_cuentas_ciclo_completo(client):
    headers = _auth_headers_admin(client)

    assert client.get("/configuracion/cuentas", headers=headers).json() == []

    r = client.post(
        "/configuracion/cuentas", json={"cl_cuenta": 2819, "nombre": "Cuenta Demo"}, headers=headers
    )
    assert r.status_code == 200

    r = client.post(
        "/configuracion/cuentas", json={"cl_cuenta": 2819, "nombre": "Cuenta Demo"}, headers=headers
    )
    assert r.status_code == 400  # duplicado

    r = client.delete("/configuracion/cuentas/2819", headers=headers)
    assert r.status_code == 200
    assert client.get("/configuracion/cuentas", headers=headers).json() == []

    r = client.post("/configuracion/cuentas/limpiar", headers=headers)
    assert r.status_code == 200


def test_estatus_abierto_no_se_puede_asignar_a_mano(client):
    import app.repositories.estatus_repo as estatus_repo_module
    from app.schemas.expediente import EstatusExpediente

    cabina_headers = _auth_headers_cabina(client)
    estatus_repo_module.actualizar_estatus(1001, EstatusExpediente.EN_ESPERA_RESPUESTA, "RFCCABTEST")
    r = client.post(
        "/seguimiento/estatus",
        json={"cl_expediente": 1001, "estatus": "Abierto"},
        headers=cabina_headers,
    )
    assert r.status_code == 400
    assert "abierto" in r.json()["detail"].lower()
    r = client.get("/expedientes", params={"cl_expediente": 1001}, headers=cabina_headers)
    assert r.json()[0]["estatus"] == "En Espera de Respuesta"  # no cambió


def test_comprobante_acepta_comentario_de_20_caracteres_y_primer_envio_sigue_en_50(client):
    import app.repositories.estatus_repo as estatus_repo_module
    from app.schemas.expediente import EstatusExpediente

    prov_headers = _auth_headers_proveedor(client)
    estatus_repo_module.actualizar_estatus(1001, EstatusExpediente.EN_ESPERA_RESPUESTA, "RFCCABTEST")
    corto = "x" * 20

    # Primer envío (En Espera de Respuesta): 20 caracteres NO alcanzan.
    r = client.post("/seguimiento/actualizar", json={"cl_expediente": 1001, "comentario": corto}, headers=prov_headers)
    assert r.status_code == 400
    assert "al menos 50" in r.json()["detail"]

    # Regresó como Seguimiento de Cita: 19 siguen sin alcanzar, 20 pasan la
    # validación de longitud (y topan con el siguiente requisito: el comprobante).
    client.post("/seguimiento/pago-anticipado/1001", json={"es_anticipado": True}, headers=prov_headers)
    estatus_repo_module.actualizar_estatus(1001, EstatusExpediente.SEGUIMIENTO_CITA, "RFCCABTEST")
    r = client.post(
        "/seguimiento/actualizar", json={"cl_expediente": 1001, "comentario": "x" * 19}, headers=prov_headers
    )
    assert r.status_code == 400
    assert "al menos 20" in r.json()["detail"]
    r = client.post("/seguimiento/actualizar", json={"cl_expediente": 1001, "comentario": corto}, headers=prov_headers)
    assert r.status_code == 400
    assert "comprobante" in r.json()["detail"].lower()


def test_listar_subservicios_filtra_a_los_que_soporta_la_pantalla_expedientes(monkeypatch):
    """
    El combo Subservicio debe mostrar exactamente los 8 subservicios que
    trabaja dbo.ST_CP_ObtenerExpedientesSinProveedorMedico -- cualquier
    otro (ej. Ambulancia) siempre daría 0 resultados en esa pantalla.
    """
    import app.repositories.catalogos_repo as catalogos_repo

    monkeypatch.setattr(
        catalogos_repo,
        "call_procedure",
        lambda *a, **k: [
            {"clSubServicio": 226, "dsSubServicio": "Referencias Médicas"},
            {"clSubServicio": 223, "dsSubServicio": "Ambulancia"},  # no soportado por esa pantalla
            {"clSubServicio": 377, "dsSubServicio": "Check Up"},
        ],
    )
    assert [s.clave for s in catalogos_repo.listar_subservicios(4)] == [226, 377]


# ---------- Hallazgos del escaneo de seguridad (Checkmarx, 13-oct-2026) ----------
# Cada prueba de aquí abajo fija una de las correcciones; si alguien quita la
# validación o el manejador, la prueba vuelve a fallar.


def test_error_de_validacion_no_refleja_el_dato_recibido(client):
    """
    CWE-359: Pydantic mete el valor recibido en la clave "input" de cada
    error y FastAPI lo regresaba tal cual, así que una contraseña rechazada
    terminaba escrita en el body del 422.
    """
    import app.repositories.accesos_repo as accesos_repo_module

    accesos_repo_module.alta_acceso("RFCLEAKTST", "Prueba Fuga", accesos_repo_module.PERFIL_CABINA)
    secreto = "SinCaracterEspecial1"

    r = client.post("/auth/rfc/crear-password", json={"rfc": "RFCLEAKTST", "password": secreto})

    assert r.status_code == 422
    assert secreto not in r.text
    error = r.json()["detail"][0]
    assert "input" not in error
    # El frontend solo usa detail[].msg (ver frontend/js/core/api.js), así
    # que el mensaje de por qué falló sí debe seguir llegando.
    assert error["loc"] == ["body", "password"]
    assert "contraseña" in error["msg"]


def test_password_queda_enmascarada_en_el_modelo():
    """CWE-359: SecretStr evita que la contraseña salga por un repr o un dump."""
    from app.schemas.acceso import RfcLoginInput

    secreto = "Clave2026!"
    modelo = RfcLoginInput(rfc="ABCD123456", password=secreto)

    assert secreto not in repr(modelo)
    assert secreto not in modelo.model_dump_json()
    assert modelo.password.get_secret_value() == secreto


def test_corte_acota_cuantos_expedientes_se_pueden_mandar(client):
    """
    CWE-606: el corte consulta el SP una vez por expediente de la lista; sin
    tope, un body con cientos de miles de claves deja al servidor iterando.
    """
    from app.schemas.correo import MAXIMO_EXPEDIENTES_POR_OPERACION

    headers = _auth_headers_admin(client)

    r = client.post(
        "/expedientes/corte",
        json={"expedientes": list(range(1, MAXIMO_EXPEDIENTES_POR_OPERACION + 2))},
        headers=headers,
    )
    assert r.status_code == 422
    assert r.json()["detail"][0]["type"] == "too_long"


def test_enviar_correo_proveedores_acota_cuantos_expedientes_se_pueden_mandar(client):
    """CWE-606: mismo tope que el corte, por el mismo motivo."""
    from app.schemas.correo import MAXIMO_EXPEDIENTES_POR_OPERACION

    headers = _auth_headers_cabina(client)

    r = client.post(
        "/expedientes/enviar-correo-proveedores",
        json={"expedientes": list(range(1, MAXIMO_EXPEDIENTES_POR_OPERACION + 2))},
        headers=headers,
    )
    assert r.status_code == 422
    assert r.json()["detail"][0]["type"] == "too_long"


def test_busqueda_de_cuentas_acota_el_largo_del_texto(client):
    """CWE-606: el typeahead valida el texto carácter por carácter."""
    from app.routers.catalogos import LARGO_MAXIMO_BUSQUEDA_CUENTA

    headers = _auth_headers(client)

    r = client.get(
        "/catalogos/cuentas/buscar",
        params={"texto": "a" * (LARGO_MAXIMO_BUSQUEDA_CUENTA + 1)},
        headers=headers,
    )
    assert r.status_code == 422


def test_catalogos_acotan_el_rango_de_cl_servicio(client):
    """CWE-606: cl_servicio llegaba sin rango y lo que regrese el SP se recorre completo."""
    headers = _auth_headers(client)

    for ruta in ("/catalogos/servicios", "/catalogos/subservicios"):
        assert client.get(ruta, params={"cl_servicio": 0}, headers=headers).status_code == 422
        assert client.get(ruta, params={"cl_servicio": 10**9}, headers=headers).status_code == 422
        # El valor que de verdad usa el portal sigue pasando.
        assert client.get(ruta, params={"cl_servicio": 4}, headers=headers).status_code == 200


def test_configuracion_cuentas_rechaza_sesion_sin_perfil(client):
    """
    Revisión de seguridad del 19-oct-2026: el guard era una lista negra
    (rechazaba Cabina y Proveedor), así que una sesión SISE legada -- cuyo
    token no trae 'perfil' -- entraba a configuración global del portal.
    Ahora es lista blanca, igual que el resto de secciones de Administrador.
    """
    headers = _auth_headers(client)  # login legado de SISE: token sin 'perfil'

    assert client.get("/configuracion/cuentas", headers=headers).status_code == 403
    r = client.post(
        "/configuracion/cuentas", json={"cl_cuenta": 2819, "nombre": "Cuenta Demo"}, headers=headers
    )
    assert r.status_code == 403
    assert client.delete("/configuracion/cuentas/2819", headers=headers).status_code == 403
    assert client.post("/configuracion/cuentas/limpiar", headers=headers).status_code == 403


def test_carga_del_catalogo_de_proveedores_rechaza_sesion_sin_perfil(client):
    """Misma regla compartida (verificar_rol_administrador): la carga del
    Excel también escribe configuración global, así que tampoco debe
    aceptar un token sin perfil."""
    headers = _auth_headers(client)

    assert client.get("/proveedores-catalogo", headers=headers).status_code == 403
    assert client.get("/proveedores-catalogo/plantilla", headers=headers).status_code == 403


def test_sanear_para_log_no_deja_forjar_renglones():
    """CWE-117: un salto de línea en un valor permitía inventar entradas en el log."""
    from app.core.log_seguro import sanear_para_log

    saneado = sanear_para_log("corte.xlsx\r\n2026-10-13 INFO Acceso concedido a ADMIN\x1b[2J")

    assert "\n" not in saneado
    assert "\r" not in saneado
    assert "\x1b" not in saneado
    assert saneado.startswith("corte.xlsx\\r\\n")


def test_modo_simulado_sanea_el_nombre_del_adjunto(client, caplog):
    """CWE-117: el nombre del archivo del corte llega al log del modo simulado."""
    import logging

    from app.services import email_service

    with caplog.at_level(logging.INFO, logger="email_service"):
        email_service._enviar(
            ["alguien@ike.com"],
            "Corte",
            "<p>cuerpo</p>",
            adjunto=email_service.Adjunto("corte.xlsx\n2026-10-13 INFO renglon forjado", b"x"),
        )

    registros = [r for r in caplog.records if r.name == "email_service"]
    assert registros, "no se registró nada en el log del modo simulado"
    mensaje = registros[-1].getMessage()
    assert "\n" not in mensaje
    assert "corte.xlsx\\n2026-10-13" in mensaje


def test_seed_usuarios_prueba_con_password_permite_login_de_los_3_perfiles(client):
    from scripts.seed_usuarios_prueba import USUARIOS_PRUEBA, ejecutar

    ejecutar(password="Qwer1234$")
    perfiles = []
    for rfc, _nombre, perfil, *_ in USUARIOS_PRUEBA:
        r = client.post("/auth/rfc/login", json={"rfc": rfc, "password": "Qwer1234$"})
        assert r.status_code == 200, (rfc, r.text)
        perfiles.append(r.json()["perfil"])
        assert client.post("/auth/rfc/login", json={"rfc": rfc, "password": "Otra1234$"}).status_code == 401
    assert sorted(perfiles) == [1, 2, 3]


def test_seed_usuarios_prueba_rechaza_password_debil(client):
    from scripts.seed_usuarios_prueba import ejecutar

    with pytest.raises(SystemExit):
        ejecutar(password="debil")


# ---------- Colores de Cuentas (color y prefijo por cuenta) ----------
def test_colores_de_cuentas_solo_administrador(client):
    for headers in (_auth_headers_cabina(client), _auth_headers_proveedor(client)):
        assert client.get("/admin/cuentas-etiquetas", headers=headers).status_code == 403
        assert client.get("/admin/cuentas-etiquetas/paleta", headers=headers).status_code == 403
        r = client.put("/admin/cuentas-etiquetas", json={"cl_cuenta": 2819, "nombre": "Cuenta Demo", "prefijo": "DEM", "color": "rosa"}, headers=headers)
        assert r.status_code == 403
        assert client.delete("/admin/cuentas-etiquetas/2819", headers=headers).status_code == 403


def test_colores_de_cuentas_alta_cambio_y_baja(client):
    headers = _auth_headers_admin(client)
    client.post("/configuracion/cuentas", json={"cl_cuenta": 2819, "nombre": "Cuenta Demo"}, headers=headers)
    assert client.get("/admin/cuentas-etiquetas", headers=headers).json() == []
    claves = [c["clave"] for c in client.get("/admin/cuentas-etiquetas/paleta", headers=headers).json()]
    assert "rosa" in claves and "morado" in claves

    r = client.put("/admin/cuentas-etiquetas", json={"cl_cuenta": 2819, "nombre": "Cuenta Demo", "prefijo": " DEM ", "color": "Rosa"}, headers=headers)
    assert r.status_code == 200 and r.json()["actualizada"] is False
    fila = client.get("/admin/cuentas-etiquetas", headers=headers).json()[0]
    assert (fila["cl_cuenta"], fila["prefijo"], fila["color"]) == (2819, "DEM", "rosa")
    assert fila["actualizado_por"] == "Admin de Prueba"

    # Se puede cambiar en cualquier momento (misma cuenta, no se duplica)
    r = client.put("/admin/cuentas-etiquetas", json={"cl_cuenta": 2819, "nombre": "Cuenta Demo", "prefijo": "", "color": "azul"}, headers=headers)
    assert r.json()["actualizada"] is True
    filas = client.get("/admin/cuentas-etiquetas", headers=headers).json()
    assert len(filas) == 1 and filas[0]["color"] == "azul" and filas[0]["prefijo"] == ""

    assert client.delete("/admin/cuentas-etiquetas/2819", headers=headers).status_code == 200
    assert client.delete("/admin/cuentas-etiquetas/2819", headers=headers).status_code == 404


def test_colores_de_cuentas_rechaza_color_y_prefijo_invalidos(client):
    headers = _auth_headers_admin(client)
    base = {"cl_cuenta": 2819, "nombre": "Cuenta Demo", "prefijo": "DEM", "color": "rosa"}
    assert client.put("/admin/cuentas-etiquetas", json={**base, "color": "#ff0000"}, headers=headers).status_code == 422
    assert client.put("/admin/cuentas-etiquetas", json={**base, "color": "rojo-fuerte"}, headers=headers).status_code == 422
    assert client.put("/admin/cuentas-etiquetas", json={**base, "prefijo": "<b>x</b>"}, headers=headers).status_code == 422
    assert client.put("/admin/cuentas-etiquetas", json={**base, "prefijo": "A" * 13}, headers=headers).status_code == 422
    assert client.get("/admin/cuentas-etiquetas", headers=headers).json() == []


def test_expedientes_traen_color_y_prefijo_de_su_cuenta(client):
    admin = _auth_headers_admin(client)
    cabina = _auth_headers_cabina(client)
    client.post("/configuracion/cuentas", json={"cl_cuenta": 2819, "nombre": "Cuenta Demo"}, headers=admin)
    sin = client.get("/expedientes", headers=cabina).json()
    assert sin and all(e["cuenta_color"] is None and e["cuenta_prefijo"] is None for e in sin)

    client.put("/admin/cuentas-etiquetas", json={"cl_cuenta": 2819, "nombre": "cuenta  DEMO", "prefijo": "DEM", "color": "morado"}, headers=admin)
    con = client.get("/expedientes", headers=cabina).json()
    # el nombre se compara sin importar mayúsculas ni espacios de más
    assert all(e["cuenta_color"] == "morado" and e["cuenta_prefijo"] == "DEM" for e in con)

    client.put("/admin/cuentas-etiquetas", json={"cl_cuenta": 2819, "nombre": "Cuenta Demo", "prefijo": "", "color": "azul"}, headers=admin)
    sin_prefijo = client.get("/expedientes", headers=cabina).json()
    assert all(e["cuenta_color"] == "azul" and e["cuenta_prefijo"] is None for e in sin_prefijo)


def test_colores_de_cuentas_rechaza_una_cuenta_fuera_del_catalogo(client):
    headers = _auth_headers_admin(client)
    # 999 no está en el catálogo simulado (solo existe la 2819)
    r = client.put("/admin/cuentas-etiquetas", json={"cl_cuenta": 999, "nombre": "Cuenta Ajena", "prefijo": "AJ", "color": "rosa"}, headers=headers)
    assert r.status_code == 400
    assert "Agregar cuenta" in r.json()["detail"]
    assert client.get("/admin/cuentas-etiquetas", headers=headers).json() == []
    # una del catálogo (las que ya se jalan en Expedientes) sí, sin configurar nada antes
    r = client.put("/admin/cuentas-etiquetas", json={"cl_cuenta": 2819, "nombre": "Cuenta Demo", "prefijo": "DEM", "color": "rosa"}, headers=headers)
    assert r.status_code == 200


def test_colores_de_cuentas_permite_editar_una_ya_etiquetada_aunque_salga_del_catalogo(client, monkeypatch):
    import app.repositories.catalogos_repo as catalogos_repo

    headers = _auth_headers_admin(client)
    client.put("/admin/cuentas-etiquetas", json={"cl_cuenta": 2819, "nombre": "Cuenta Demo", "prefijo": "DEM", "color": "rosa"}, headers=headers)
    monkeypatch.setattr(catalogos_repo, "call_procedure", lambda *a, **k: [])  # el catálogo ya no la trae
    r = client.put("/admin/cuentas-etiquetas", json={"cl_cuenta": 2819, "nombre": "Cuenta Demo", "prefijo": "DEM", "color": "azul"}, headers=headers)
    assert r.status_code == 200
    assert client.get("/admin/cuentas-etiquetas", headers=headers).json()[0]["color"] == "azul"


def test_combo_de_cuentas_suma_las_adicionales_a_las_de_siempre(client, monkeypatch):
    import app.repositories.catalogos_repo as catalogos_repo
    from app.config import get_settings

    llamadas = []

    def falso(sp_name, params=None):
        llamadas.append([c[0] for c in params["CuentasPermitidas"]])
        return [{"clCuenta": 2819, "Nombre": "Cuenta Demo"}]

    monkeypatch.setattr(catalogos_repo, "call_procedure", falso)
    admin = _auth_headers_admin(client)
    ajustes = get_settings()
    base = ajustes.parse_int_list(ajustes.cuentas_permitidas)

    # Sin adicionales: las de siempre (CUENTAS_PERMITIDAS)
    assert client.get("/catalogos/cuentas", headers=admin).status_code == 200
    assert llamadas[-1] == base

    # Con adicionales: las de siempre MÁS las agregadas (sin duplicar una que ya estaba)
    client.post("/configuracion/cuentas", json={"cl_cuenta": 555, "nombre": "Otra Cuenta"}, headers=admin)
    client.post("/configuracion/cuentas", json={"cl_cuenta": base[0], "nombre": "Ya estaba"}, headers=admin)
    client.get("/catalogos/cuentas", headers=admin)
    assert llamadas[-1] == base + [555]

    # Al quitar la adicional, vuelve a las de siempre
    client.delete("/configuracion/cuentas/555", headers=admin)
    client.get("/catalogos/cuentas", headers=admin)
    assert llamadas[-1] == base

    # Si CUENTAS_PERMITIDAS está vacía no hay restricción: se manda vacío (todas) aunque haya adicionales
    monkeypatch.setenv("CUENTAS_PERMITIDAS", "")
    get_settings.cache_clear()
    client.post("/configuracion/cuentas", json={"cl_cuenta": 555, "nombre": "Otra Cuenta"}, headers=admin)
    client.get("/catalogos/cuentas", headers=admin)
    assert llamadas[-1] == []
