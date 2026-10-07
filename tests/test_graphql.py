"""
Pruebas de la capa GraphQL (app/graphql/). Mismo patrón que
tests/test_smoke.py: se sustituyen call_procedure/call_procedure_write
por datos falsos, no se requiere SQL Server real.

Ejecutar con:
    pytest tests/test_graphql.py -v
"""
import datetime

import pytest
from fastapi.testclient import TestClient

import app.repositories.auth_repo as auth_repo_module
import app.repositories.catalogos_repo as catalogos_repo_module
import app.repositories.expedientes_repo as expedientes_repo_module
import app.repositories.seguimiento_repo as seguimiento_repo_module
from app.main import app


def fake_call_procedure(sp_name, params=None):
    if sp_name == "dbo.ObtenerExpedientesSinProveedorMedico":
        return [
            {
                "Expediente": 1001,
                "Cuenta": "Cuenta Demo",
                "TipoServicio": "Servicio Médico",
                "TipoSubservicio": "Consulta Externa",
                "NombreTitular": "Juan Pérez",
                "NombrePaciente": "Paciente Demo",
                "Especialidad": "Medicina General",
                "Entidad": "Campeche",
                "Municipio": "Campeche",
                "FechaAperturaServicio": datetime.date(2026, 8, 1),
                "FechaAsignacionProveedor": datetime.date(2026, 8, 1),
                "FechaCita": datetime.date(2026, 8, 3),
                "Telefono": "9811234567",
                "Email": "demo@example.com",
            }
        ]
    if sp_name == "dbo.ObtenerCatalogoServicio":
        return [{"clServicio": 4, "dsServicio": "Servicio Médico"}]
    if sp_name == "dbo.ObtenerServicioMedico":
        return [{"clSubServicio": 377, "dsSubServicio": "Consulta Externa"}]
    if sp_name == "dbo.ObtenerCatalogoCuentas":
        return [{"clCuenta": 2819, "Nombre": "Cuenta Demo"}]
    if sp_name == "dbo.sp_S2_BuscaCuenta":
        return [{"clCuenta": 2819, "Nombre": "Cuenta Demo"}]
    if sp_name == "dbo.sp_EncriptDesEncriptPassword":
        if params.get("pUsuario") == "ijimenez" and params.get("pContraseña") == "clave123":
            return [{"clUsrApp": 42, "Nombre": "Ignacio Jiménez", "Activo": True}]
        return []
    raise AssertionError(f"SP inesperado: {sp_name} / params={params}")


def fake_call_procedure_write(sp_name, params=None):
    if sp_name == "dbo.RegistrarSeguimiento":
        assert params["clUsrApp"] == 42  # debe venir del token, no del input
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

    # El rate limiter (app/core/rate_limit.py, usado también por la mutation
    # login -- ver app/graphql/mutation.py) guarda su conteo en memoria del
    # proceso -- sin esto, pruebas que hacen login varias veces chocarían
    # entre sí.
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

    from app.config import get_settings

    get_settings.cache_clear()

    with TestClient(app) as c:
        yield c


def _graphql(client, query, headers=None):
    return client.post("/graphql", json={"query": query}, headers=headers or {})


def _login_headers(client):
    m = """
    mutation {
      login(datos: {usuario: "ijimenez", password: "clave123"}) { accessToken }
    }
    """
    r = _graphql(client, m)
    token = r.json()["data"]["login"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def _headers_con_perfil(client, rfc, nombre, perfil, password):
    """Sesión RFC real (no SISE) con un perfil específico -- mismo patrón
    que tests/test_smoke.py, para probar que GraphQL respeta los mismos
    roles que el REST."""
    import app.repositories.accesos_repo as accesos_repo_module

    accesos_repo_module.alta_acceso(rfc, nombre, perfil, "Ciudad de México")
    accesos_repo_module.crear_password(rfc, password)
    r = client.post("/auth/rfc/login", json={"rfc": rfc, "password": password})
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _headers_proveedor(client):
    import app.repositories.accesos_repo as accesos_repo_module

    return _headers_con_perfil(client, "RFCPROVGQL", "Proveedor GraphQL", accesos_repo_module.PERFIL_PROVEEDOR, "Proveedor2024")


def _headers_cabina(client):
    import app.repositories.accesos_repo as accesos_repo_module

    return _headers_con_perfil(client, "RFCCABGQL", "Cabina GraphQL", accesos_repo_module.PERFIL_CABINA, "Cabina2024xx")


def _headers_admin(client):
    import app.repositories.accesos_repo as accesos_repo_module

    return _headers_con_perfil(client, "RFCADMGQL", "Admin GraphQL", accesos_repo_module.PERFIL_ADMINISTRADOR, "Admin2024xx")


def test_query_sin_sesion_da_error(client):
    r = _graphql(client, "{ servicios { clave descripcion } }")
    assert r.status_code == 200  # GraphQL siempre regresa 200; el error va en "errors"
    body = r.json()
    assert body["data"] is None
    assert "iniciar sesión" in body["errors"][0]["message"]


def test_login_ok(client):
    m = """
    mutation {
      login(datos: {usuario: "ijimenez", password: "clave123"}) {
        accessToken tokenType clUsrApp usuario nombre
      }
    }
    """
    r = _graphql(client, m)
    data = r.json()["data"]["login"]
    assert data["clUsrApp"] == 42
    assert data["nombre"] == "Ignacio Jiménez"
    assert data["tokenType"] == "bearer"
    assert data["accessToken"]


def test_login_credenciales_invalidas(client):
    m = 'mutation { login(datos: {usuario: "ijimenez", password: "mala"}) { accessToken } }'
    r = _graphql(client, m)
    body = r.json()
    assert body["data"] is None
    assert "errors" in body


def test_expedientes_con_sesion(client):
    headers = _login_headers(client)
    q = """
    query {
      expedientes(filtro: {clExpediente: 1001}) {
        expediente cuenta tipoServicio nombrePaciente estatus fechaCita
      }
    }
    """
    r = _graphql(client, q, headers)
    data = r.json()["data"]["expedientes"]
    assert data[0]["expediente"] == 1001
    assert data[0]["estatus"] == "ABIERTO"


def test_catalogo_servicios_y_subservicios(client):
    headers = _login_headers(client)
    r = _graphql(client, "{ servicios { clave descripcion } }", headers)
    assert r.json()["data"]["servicios"] == [{"clave": 4, "descripcion": "Servicio Médico"}]

    r = _graphql(client, "{ subservicios(clServicio: 4) { clave descripcion } }", headers)
    assert r.json()["data"]["subservicios"] == [{"clave": 377, "descripcion": "Consulta Externa"}]


def test_actualizar_seguimiento_usa_usr_app_del_token(client):
    headers = _login_headers(client)
    # >= 50 caracteres: misma regla que el REST (ver
    # app/services/seguimiento_service.py:LONGITUD_MINIMA_COMENTARIO_PROVEEDOR).
    comentario = "Prueba de actualización de seguimiento con suficiente longitud."
    m = f'mutation {{ actualizarSeguimiento(datos: {{clExpediente: 1001, comentario: "{comentario}"}}) {{ ok mensaje }} }}'
    r = _graphql(client, m, headers)
    assert r.json()["data"]["actualizarSeguimiento"]["ok"] is True


def test_actualizar_seguimiento_vacio_falla(client):
    headers = _login_headers(client)
    m = 'mutation { actualizarSeguimiento(datos: {clExpediente: 1001, comentario: "   "}) { ok } }'
    r = _graphql(client, m, headers)
    assert r.json()["data"] is None
    assert "errors" in r.json()


def test_actualizar_estatus_se_refleja_en_listado(client):
    headers = _login_headers(client)
    m = "mutation { actualizarEstatus(datos: {clExpediente: 1001, estatus: SEGUIMIENTO_PROVEEDOR}) { ok } }"
    r = _graphql(client, m, headers)
    assert r.json()["data"]["actualizarEstatus"]["ok"] is True

    q = "query { expedientes(filtro: {clExpediente: 1001}) { estatus } }"
    r = _graphql(client, q, headers)
    assert r.json()["data"]["expedientes"][0]["estatus"] == "SEGUIMIENTO_PROVEEDOR"


def test_configuracion_cuentas_ciclo_completo(client):
    headers = _login_headers(client)

    r = _graphql(client, "{ cuentasConfiguradas { clCuenta nombre } }", headers)
    assert r.json()["data"]["cuentasConfiguradas"] == []

    m = 'mutation { agregarCuenta(datos: {clCuenta: 2819, nombre: "Cuenta Demo"}) { ok } }'
    r = _graphql(client, m, headers)
    assert r.json()["data"]["agregarCuenta"]["ok"] is True

    # duplicado -> error
    r = _graphql(client, m, headers)
    assert r.json()["data"] is None

    r = _graphql(client, "{ cuentasConfiguradas { clCuenta nombre } }", headers)
    assert len(r.json()["data"]["cuentasConfiguradas"]) == 1

    m = "mutation { eliminarCuenta(clCuenta: 2819) { ok } }"
    r = _graphql(client, m, headers)
    assert r.json()["data"]["eliminarCuenta"]["ok"] is True

    r = _graphql(client, "{ cuentasConfiguradas { clCuenta nombre } }", headers)
    assert r.json()["data"]["cuentasConfiguradas"] == []


def test_enviar_correo_proveedores(client):
    headers = _login_headers(client)
    m = "mutation { enviarCorreoProveedores(datos: {expedientes: [1001]}) { enviados expedientes } }"
    r = _graphql(client, m, headers)
    data = r.json()["data"]["enviarCorreoProveedores"]
    assert data["enviados"] == 1
    assert data["expedientes"] == [1001]


# --- Regresión: control de acceso roto en mutations (ver SECURITY-REVIEW.md) ---
# Antes, estas mutations solo exigían una sesión iniciada (cualquier perfil),
# sin aplicar las reglas de rol que sí tiene el REST -- lo siguiente prueba
# que GraphQL ahora las respeta exactamente igual.


def test_actualizar_estatus_proveedor_no_puede_cambiar_estatus(client):
    headers = _headers_proveedor(client)
    m = "mutation { actualizarEstatus(datos: {clExpediente: 1001, estatus: SEGUIMIENTO_PROVEEDOR}) { ok } }"
    r = _graphql(client, m, headers)
    body = r.json()
    assert body["data"] is None
    assert "no puede cambiar el estado manualmente" in body["errors"][0]["message"]


def test_actualizar_estatus_regreso_requiere_perfil_cabina(client):
    headers = _headers_admin(client)
    m = 'mutation { actualizarEstatus(datos: {clExpediente: 1001, estatus: EN_ESPERA_RESPUESTA, comentario: "Corrección necesaria"}) { ok } }'
    r = _graphql(client, m, headers)
    body = r.json()
    assert body["data"] is None
    assert "no se puede asignar a mano desde este perfil" in body["errors"][0]["message"]


def test_actualizar_seguimiento_cabina_bloqueado(client):
    headers = _headers_cabina(client)
    comentario = "Comentario de prueba con la longitud suficiente para pasar la validación."
    m = f'mutation {{ actualizarSeguimiento(datos: {{clExpediente: 1001, comentario: "{comentario}"}}) {{ ok }} }}'
    r = _graphql(client, m, headers)
    body = r.json()
    assert body["data"] is None
    assert "no tiene acceso a Registrar seguimiento" in body["errors"][0]["message"]


def test_configuracion_cuentas_rechaza_proveedor_y_cabina(client):
    headers_proveedor = _headers_proveedor(client)
    headers_cabina = _headers_cabina(client)
    m = 'mutation { agregarCuenta(datos: {clCuenta: 2819, nombre: "Cuenta Demo"}) { ok } }'

    for headers in (headers_proveedor, headers_cabina):
        r = _graphql(client, m, headers)
        body = r.json()
        assert body["data"] is None
        assert "exclusiva del perfil Administrador" in body["errors"][0]["message"]

    r = _graphql(client, "mutation { limpiarCuentasConfiguradas { ok } }", headers_cabina)
    assert r.json()["data"] is None

    r = _graphql(client, "mutation { eliminarCuenta(clCuenta: 2819) { ok } }", headers_proveedor)
    assert r.json()["data"] is None


def test_configuracion_cuentas_permite_administrador(client):
    headers = _headers_admin(client)
    m = 'mutation { agregarCuenta(datos: {clCuenta: 2819, nombre: "Cuenta Demo"}) { ok } }'
    r = _graphql(client, m, headers)
    assert r.json()["data"]["agregarCuenta"]["ok"] is True


def test_login_graphql_aplica_limite_de_intentos(client):
    m = 'mutation {{ login(datos: {{usuario: "ijimenez", password: "mala-{i}"}}) {{ accessToken }} }}'
    for i in range(10):
        r = _graphql(client, m.format(i=i))
        assert "errors" in r.json()

    # Intento número 11: ya no debe ni intentar validar la contraseña --
    # el rate limiter (app/core/rate_limit.py) lo detiene antes, igual que
    # en /auth/login (ver tests/test_smoke.py).
    r = _graphql(client, m.format(i=10))
    body = r.json()
    assert body["data"] is None
    assert "Demasiados intentos" in body["errors"][0]["message"]
