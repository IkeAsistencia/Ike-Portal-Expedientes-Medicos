"""
Pruebas de las citas del Directorio de Proveedores
(/directorio-proveedores/citas y /{clave}/agenda) -- NO requiere SQL Server
real: todo vive en SQLite local.

Antes de esto, "Agendar cita" era una simulación del frontend: los horarios
se inventaban con un hash y nada quedaba registrado. Ahora la cita se guarda
contra la clave del proveedor (PRV-000001), que es la que no cambia entre
cargas del Excel.
"""
from datetime import date, timedelta
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.agenda_proveedores_service import DIAS_AGENDA_MAXIMO, HORARIOS_BASE
from app.services.proveedores_excel_service import COLUMNAS

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


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


def _auth_headers_cabina(client):
    import app.repositories.accesos_repo as accesos_repo_module

    accesos_repo_module.alta_acceso("RFCCABTEST", "Cabina de Prueba", accesos_repo_module.PERFIL_CABINA)
    accesos_repo_module.crear_password("RFCCABTEST", "Cabina2024xx")
    r = client.post("/auth/rfc/login", json={"rfc": "RFCCABTEST", "password": "Cabina2024xx"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def proveedor(client):
    """Un proveedor ya cargado, con su clave del portal lista para agendar."""
    from openpyxl import Workbook

    headers = _auth_headers_admin(client)
    fila = {
        "nombre": "Dra. Laura Méndez Ruiz", "especialidad": "Cardiología", "cedula": "8453219",
        "estado": "Jalisco", "municipio": "Guadalajara", "horario": "Lun-Vie 09:00-14:00",
    }
    wb = Workbook()
    ws = wb.active
    for col_idx, (encabezado, _clave, _ancho, obligatorio) in enumerate(COLUMNAS, start=1):
        ws.cell(row=1, column=col_idx, value=encabezado + (" *" if obligatorio else ""))
    for col_idx, (_encabezado, clave, _ancho, _obligatorio) in enumerate(COLUMNAS, start=1):
        ws.cell(row=2, column=col_idx, value=fila.get(clave))
    buffer = BytesIO()
    wb.save(buffer)
    client.post(
        "/proveedores-catalogo/cargar", headers=headers,
        files={"archivo": ("catalogo.xlsx", buffer.getvalue(), XLSX_MIME)},
    )
    padron = client.get("/directorio-proveedores", headers=headers).json()
    return {"headers": headers, "clave": padron[0]["clave"]}


HOY = date.today().isoformat()


# ---------- Agendar ----------

def test_agendar_cita_queda_registrada_con_folio(client, proveedor):
    r = client.post("/directorio-proveedores/citas", headers=proveedor["headers"], json={
        "clave_proveedor": proveedor["clave"], "fecha": HOY, "hora": "09:00", "paciente": "Juan Pérez",
    })
    assert r.status_code == 200, r.text
    assert r.json()["folio"].startswith("CITA-")

    citas = client.get("/directorio-proveedores/citas", headers=proveedor["headers"]).json()
    assert len(citas) == 1
    assert citas[0]["clave_proveedor"] == proveedor["clave"]
    assert citas[0]["hora"] == "09:00"
    assert citas[0]["paciente"] == "Juan Pérez"
    assert citas[0]["estatus"] == "Agendada"
    assert citas[0]["rfc_agendo"] == "RFCADMTEST"


def test_la_cita_sobrevive_al_reinicio_del_navegador(client, proveedor):
    """Lo que se perdía antes: el agendado vivía solo en el estado del
    navegador. Ahora una consulta nueva lo sigue encontrando."""
    client.post("/directorio-proveedores/citas", headers=proveedor["headers"], json={
        "clave_proveedor": proveedor["clave"], "fecha": HOY, "hora": "12:00",
    })
    assert len(client.get("/directorio-proveedores/citas", headers=proveedor["headers"]).json()) == 1


def test_no_se_puede_apartar_dos_veces_el_mismo_horario(client, proveedor):
    cuerpo = {"clave_proveedor": proveedor["clave"], "fecha": HOY, "hora": "10:30"}
    assert client.post("/directorio-proveedores/citas", headers=proveedor["headers"], json=cuerpo).status_code == 200
    repetida = client.post("/directorio-proveedores/citas", headers=proveedor["headers"], json=cuerpo)
    assert repetida.status_code == 409
    assert "ya fue apartado" in repetida.json()["detail"]


def test_agendar_con_proveedor_inexistente_regresa_404(client, proveedor):
    r = client.post("/directorio-proveedores/citas", headers=proveedor["headers"], json={
        "clave_proveedor": "PRV-999999", "fecha": HOY, "hora": "09:00",
    })
    assert r.status_code == 404


def test_no_se_agenda_en_el_pasado(client, proveedor):
    ayer = (date.today() - timedelta(days=1)).isoformat()
    r = client.post("/directorio-proveedores/citas", headers=proveedor["headers"], json={
        "clave_proveedor": proveedor["clave"], "fecha": ayer, "hora": "09:00",
    })
    assert r.status_code == 400


def test_no_se_agenda_mas_alla_de_la_ventana_permitida(client, proveedor):
    lejos = (date.today() + timedelta(days=DIAS_AGENDA_MAXIMO + 1)).isoformat()
    r = client.post("/directorio-proveedores/citas", headers=proveedor["headers"], json={
        "clave_proveedor": proveedor["clave"], "fecha": lejos, "hora": "09:00",
    })
    assert r.status_code == 400


def test_rechaza_un_horario_fuera_de_la_agenda(client, proveedor):
    r = client.post("/directorio-proveedores/citas", headers=proveedor["headers"], json={
        "clave_proveedor": proveedor["clave"], "fecha": HOY, "hora": "03:15",
    })
    assert r.status_code == 400


# ---------- Agenda (disponibilidad real) ----------

def test_la_agenda_deja_de_ofrecer_el_horario_ya_apartado(client, proveedor):
    agenda = client.get(
        f"/directorio-proveedores/{proveedor['clave']}/agenda", headers=proveedor["headers"]
    ).json()
    assert agenda[0]["fecha"] == HOY
    assert "09:00" in agenda[0]["horarios"]

    client.post("/directorio-proveedores/citas", headers=proveedor["headers"], json={
        "clave_proveedor": proveedor["clave"], "fecha": HOY, "hora": "09:00",
    })

    agenda = client.get(
        f"/directorio-proveedores/{proveedor['clave']}/agenda", headers=proveedor["headers"]
    ).json()
    assert "09:00" not in agenda[0]["horarios"]
    assert len(agenda[0]["horarios"]) == len(HORARIOS_BASE) - 1
    assert agenda[0]["ocupados"] == 1


def test_la_agenda_de_un_proveedor_no_afecta_la_de_otro(client, proveedor):
    """Cada renglón del padrón tiene su propia agenda -- incluido el mismo
    médico con otra especialidad."""
    from openpyxl import Workbook

    headers = proveedor["headers"]
    wb = Workbook()
    ws = wb.active
    fila = {"nombre": "Dr. Segundo", "especialidad": "Pediatría", "cedula": "1112223"}
    for col_idx, (encabezado, _clave, _ancho, obligatorio) in enumerate(COLUMNAS, start=1):
        ws.cell(row=1, column=col_idx, value=encabezado + (" *" if obligatorio else ""))
    for col_idx, (_encabezado, clave, _ancho, _obligatorio) in enumerate(COLUMNAS, start=1):
        ws.cell(row=2, column=col_idx, value=fila.get(clave))
    buffer = BytesIO()
    wb.save(buffer)
    client.post(
        "/proveedores-catalogo/cargar", headers=headers,
        files={"archivo": ("catalogo.xlsx", buffer.getvalue(), XLSX_MIME)},
    )
    otra_clave = next(
        p["clave"] for p in client.get("/directorio-proveedores", headers=headers).json()
        if p["clave"] != proveedor["clave"]
    )

    client.post("/directorio-proveedores/citas", headers=headers, json={
        "clave_proveedor": proveedor["clave"], "fecha": HOY, "hora": "09:00",
    })

    agenda_otro = client.get(f"/directorio-proveedores/{otra_clave}/agenda", headers=headers).json()
    assert "09:00" in agenda_otro[0]["horarios"]


def test_agenda_de_proveedor_inexistente_regresa_404(client, proveedor):
    r = client.get("/directorio-proveedores/PRV-999999/agenda", headers=proveedor["headers"])
    assert r.status_code == 404


# ---------- Cancelar ----------

def test_cancelar_libera_el_horario(client, proveedor):
    folio = client.post("/directorio-proveedores/citas", headers=proveedor["headers"], json={
        "clave_proveedor": proveedor["clave"], "fecha": HOY, "hora": "16:00",
    }).json()["folio"]

    assert client.post(
        f"/directorio-proveedores/citas/{folio}/cancelar", headers=proveedor["headers"]
    ).status_code == 200

    agenda = client.get(
        f"/directorio-proveedores/{proveedor['clave']}/agenda", headers=proveedor["headers"]
    ).json()
    assert "16:00" in agenda[0]["horarios"]


def test_cancelar_una_cita_inexistente_regresa_404(client, proveedor):
    r = client.post("/directorio-proveedores/citas/CITA-99999/cancelar", headers=proveedor["headers"])
    assert r.status_code == 404


# ---------- Permisos ----------

def test_cabina_no_puede_agendar(client, proveedor):
    r = client.post("/directorio-proveedores/citas", headers=_auth_headers_cabina(client), json={
        "clave_proveedor": proveedor["clave"], "fecha": HOY, "hora": "09:00",
    })
    assert r.status_code == 403
