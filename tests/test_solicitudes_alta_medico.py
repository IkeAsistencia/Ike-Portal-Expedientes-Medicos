"""
Pruebas de /solicitudes-alta-medico (Alta de médico, pantalla "Proveedores"
del Directorio de Proveedores) y de cómo una solicitud aprobada se vuelve
visible en GET /directorio-proveedores -- NO requiere SQL Server real: todo
vive en SQLite local, nunca se manda a Core.
"""
import pytest
from fastapi.testclient import TestClient

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


def _auth_headers_admin(client):
    import app.repositories.accesos_repo as accesos_repo_module

    accesos_repo_module.alta_acceso("RFCADMTEST", "Admin de Prueba", accesos_repo_module.PERFIL_ADMINISTRADOR)
    accesos_repo_module.crear_password("RFCADMTEST", "Admin2024xx")
    r = client.post("/auth/rfc/login", json={"rfc": "RFCADMTEST", "password": "Admin2024xx"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _auth_headers_proveedor(client):
    import app.repositories.accesos_repo as accesos_repo_module

    accesos_repo_module.alta_acceso("RFCPROTEST", "Proveedor de Prueba", accesos_repo_module.PERFIL_PROVEEDOR)
    accesos_repo_module.crear_password("RFCPROTEST", "Proveedor2024")
    r = client.post("/auth/rfc/login", json={"rfc": "RFCPROTEST", "password": "Proveedor2024"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _auth_headers_cabina(client):
    import app.repositories.accesos_repo as accesos_repo_module

    accesos_repo_module.alta_acceso("RFCCABTEST", "Cabina de Prueba", accesos_repo_module.PERFIL_CABINA)
    accesos_repo_module.crear_password("RFCCABTEST", "Cabina2024xx")
    r = client.post("/auth/rfc/login", json={"rfc": "RFCCABTEST", "password": "Cabina2024xx"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


SOLICITUD_VALIDA = {
    "nombre": "Dr. Nuevo Médico", "especialidad": "Cardiología", "cedula": "12345678",
    "rfc": "NUME900101AB1", "estado": "Jalisco", "municipio": "Guadalajara",
    "direccion": "Av. Siempre Viva 123", "telefono": "33 0000 0000", "email": "nuevo@correo.mx",
}


# ---------- Permisos (Cabina no usa esta pantalla) ----------

def test_crear_solicitud_rechaza_cabina(client):
    r = client.post("/solicitudes-alta-medico", headers=_auth_headers_cabina(client), json=SOLICITUD_VALIDA)
    assert r.status_code == 403


def test_listar_solicitudes_rechaza_cabina(client):
    r = client.get("/solicitudes-alta-medico", headers=_auth_headers_cabina(client))
    assert r.status_code == 403


def test_proveedor_y_administrador_pueden_crear_solicitud(client):
    assert client.post("/solicitudes-alta-medico", headers=_auth_headers_proveedor(client), json=SOLICITUD_VALIDA).status_code == 200
    assert client.post("/solicitudes-alta-medico", headers=_auth_headers_admin(client), json=SOLICITUD_VALIDA).status_code == 200


# ---------- Flujo completo ----------

def test_crear_solicitud_queda_en_revision_y_con_folio(client):
    r = client.post("/solicitudes-alta-medico", headers=_auth_headers_proveedor(client), json=SOLICITUD_VALIDA)
    assert r.status_code == 200
    folio = r.json()["folio"]
    assert folio.startswith("ALT-")

    listado = client.get("/solicitudes-alta-medico", headers=_auth_headers_admin(client)).json()
    assert len(listado) == 1
    assert listado[0]["folio"] == folio
    assert listado[0]["estatus"] == "En revisión"
    assert listado[0]["nombre"] == SOLICITUD_VALIDA["nombre"]


def test_solicitud_aprobada_no_aparece_en_el_directorio_antes_de_aprobarse(client):
    headers = _auth_headers_proveedor(client)
    client.post("/solicitudes-alta-medico", headers=headers, json=SOLICITUD_VALIDA)
    directorio = client.get("/directorio-proveedores", headers=headers).json()
    assert directorio == []


def test_solicitud_aprobada_aparece_en_el_directorio_marcada_origen_portal(client):
    admin = _auth_headers_admin(client)
    r = client.post("/solicitudes-alta-medico", headers=admin, json=SOLICITUD_VALIDA)
    folio = r.json()["folio"]

    aprobar = client.post(f"/solicitudes-alta-medico/{folio}/estatus", headers=admin, json={"estatus": "Aprobada"})
    assert aprobar.status_code == 200

    directorio = client.get("/directorio-proveedores", headers=_auth_headers_proveedor(client)).json()
    assert len(directorio) == 1
    assert directorio[0]["origen"] == "portal"
    assert directorio[0]["folio"] == folio
    assert directorio[0]["cl_proveedor"] is None
    assert directorio[0]["nombre"] == SOLICITUD_VALIDA["nombre"]


def test_rechazar_solicitud_no_la_vuelve_visible_en_el_directorio(client):
    admin = _auth_headers_admin(client)
    folio = client.post("/solicitudes-alta-medico", headers=admin, json=SOLICITUD_VALIDA).json()["folio"]
    client.post(f"/solicitudes-alta-medico/{folio}/estatus", headers=admin, json={"estatus": "Rechazada"})

    directorio = client.get("/directorio-proveedores", headers=_auth_headers_proveedor(client)).json()
    assert directorio == []

    listado = client.get("/solicitudes-alta-medico", headers=admin).json()
    assert listado[0]["estatus"] == "Rechazada"


def test_un_catalogo_de_excel_no_borra_las_solicitudes_aprobadas(client):
    """Son tablas separadas a propósito: recargar el catálogo de Core no
    debe perder a los médicos dados de alta desde el portal."""
    from io import BytesIO

    from openpyxl import Workbook

    from app.services.proveedores_catalogo_excel_service import COLUMNAS

    admin = _auth_headers_admin(client)
    folio = client.post("/solicitudes-alta-medico", headers=admin, json=SOLICITUD_VALIDA).json()["folio"]
    client.post(f"/solicitudes-alta-medico/{folio}/estatus", headers=admin, json={"estatus": "Aprobada"})

    fila_excel = {
        "cl_proveedor": 999, "nombre": "Dr. Del Catálogo", "especialidad": "Pediatría",
    }
    wb = Workbook()
    ws = wb.active
    for col_idx, (encabezado, _clave, _ancho, obligatorio) in enumerate(COLUMNAS, start=1):
        ws.cell(row=1, column=col_idx, value=encabezado + (" *" if obligatorio else ""))
    for col_idx, (_encabezado, clave, _ancho, _obligatorio) in enumerate(COLUMNAS, start=1):
        ws.cell(row=2, column=col_idx, value=fila_excel.get(clave))
    buffer = BytesIO()
    wb.save(buffer)

    client.post(
        "/proveedores-catalogo/cargar", headers=admin,
        files={"archivo": ("catalogo.xlsx", buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    directorio = client.get("/directorio-proveedores", headers=_auth_headers_proveedor(client)).json()
    origenes = {d["origen"] for d in directorio}
    assert origenes == {"core", "portal"}
    assert len(directorio) == 2


def test_estatus_invalido_se_rechaza(client):
    admin = _auth_headers_admin(client)
    folio = client.post("/solicitudes-alta-medico", headers=admin, json=SOLICITUD_VALIDA).json()["folio"]
    r = client.post(f"/solicitudes-alta-medico/{folio}/estatus", headers=admin, json={"estatus": "Lo que sea"})
    assert r.status_code == 400


def test_estatus_de_folio_inexistente_regresa_404(client):
    admin = _auth_headers_admin(client)
    r = client.post("/solicitudes-alta-medico/ALT-00000/estatus", headers=admin, json={"estatus": "Aprobada"})
    assert r.status_code == 404
