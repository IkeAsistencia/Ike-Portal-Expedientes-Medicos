"""
Pruebas de las citas del Directorio de Proveedores
(/directorio-proveedores/citas y /{clave}/agenda) -- NO requiere SQL Server
real: todo vive en SQLite local.

Antes de esto, "Agendar cita" era una simulación del frontend: los horarios
se inventaban con un hash y nada quedaba registrado. Ahora la cita se guarda
contra la clave del proveedor (PRV-000001), que es la que no cambia entre
cargas del Excel.
"""
from datetime import date, datetime, time, timedelta
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import agenda_proveedores_service
from app.services.agenda_proveedores_service import DIAS_AGENDA_MAXIMO, DIAS_CITA_MAXIMO, HORARIOS_BASE
from app.services.proveedores_excel_service import COLUMNAS

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture(autouse=True)
def _sin_sql_server(monkeypatch):
    import app.main as main_module

    monkeypatch.setattr(main_module, "calentar_pool", lambda: None)

    from app.core.rate_limit import limpiar_todo

    limpiar_todo()


@pytest.fixture(autouse=True)
def _reloj_fijo(monkeypatch):
    """Las pruebas agendan "para hoy": con el reloj real fallarían según la hora
    a la que se corran (una hora de hoy que ya pasó se rechaza). Se fija a las
    06:00 de hoy; las pruebas de "hora pasada" lo cambian a lo que necesiten."""
    monkeypatch.setattr(
        agenda_proveedores_service, "ahora", lambda: datetime.combine(date.today(), time(6, 0))
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
    lejos = (date.today() + timedelta(days=DIAS_CITA_MAXIMO + 1)).isoformat()
    r = client.post("/directorio-proveedores/citas", headers=proveedor["headers"], json={
        "clave_proveedor": proveedor["clave"], "fecha": lejos, "hora": "09:00",
    })
    assert r.status_code == 400


def test_se_puede_agendar_a_cualquier_hora_y_no_solo_a_las_sugeridas(client, proveedor):
    """El médico puede aceptar por teléfono las 12:45 aunque la lista sugiera 12:00 y 13:30."""
    manana = (date.today() + timedelta(days=1)).isoformat()   # mañana cualquier hora vale
    for hora in ("12:45", "00:00", "03:15", "23:59"):
        r = client.post("/directorio-proveedores/citas", headers=proveedor["headers"], json={
            "clave_proveedor": proveedor["clave"], "fecha": manana, "hora": hora,
        })
        assert r.status_code == 200, (hora, r.text)
    horas = {c["hora"] for c in client.get("/directorio-proveedores/citas", headers=proveedor["headers"]).json()}
    assert horas == {"12:45", "00:00", "03:15", "23:59"}


def test_rechaza_una_hora_mal_escrita(client, proveedor):
    for hora in ("25:00", "12:60", "ab:cd", "12-45"):
        r = client.post("/directorio-proveedores/citas", headers=proveedor["headers"], json={
            "clave_proveedor": proveedor["clave"], "fecha": HOY, "hora": hora,
        })
        assert r.status_code == 400, hora
        assert "HH:MM" in r.json()["detail"]
    # Con menos de 5 caracteres ni siquiera llega a esa regla: lo frena el formato.
    assert client.post("/directorio-proveedores/citas", headers=proveedor["headers"], json={
        "clave_proveedor": proveedor["clave"], "fecha": HOY, "hora": "9:30",
    }).status_code == 422


def test_se_puede_agendar_en_una_fecha_lejana_dentro_del_limite(client, proveedor):
    lejos = (date.today() + timedelta(days=100)).isoformat()   # antes el tope era de 30 días
    r = client.post("/directorio-proveedores/citas", headers=proveedor["headers"], json={
        "clave_proveedor": proveedor["clave"], "fecha": lejos, "hora": "12:45",
    })
    assert r.status_code == 200, r.text


def test_una_hora_de_hoy_que_ya_paso_se_rechaza_pero_mañana_a_esa_hora_si(client, proveedor, monkeypatch):
    monkeypatch.setattr(
        agenda_proveedores_service, "ahora", lambda: datetime.combine(date.today(), time(15, 0))
    )
    ya_paso = client.post("/directorio-proveedores/citas", headers=proveedor["headers"], json={
        "clave_proveedor": proveedor["clave"], "fecha": HOY, "hora": "09:00",
    })
    assert ya_paso.status_code == 400 and "ya pasó" in ya_paso.json()["detail"]
    ahorita = client.post("/directorio-proveedores/citas", headers=proveedor["headers"], json={
        "clave_proveedor": proveedor["clave"], "fecha": HOY, "hora": "15:00",
    })
    assert ahorita.status_code == 400   # justo la hora actual tampoco: ya empezó
    despues = client.post("/directorio-proveedores/citas", headers=proveedor["headers"], json={
        "clave_proveedor": proveedor["clave"], "fecha": HOY, "hora": "15:01",
    })
    assert despues.status_code == 200
    manana = (date.today() + timedelta(days=1)).isoformat()
    assert client.post("/directorio-proveedores/citas", headers=proveedor["headers"], json={
        "clave_proveedor": proveedor["clave"], "fecha": manana, "hora": "09:00",
    }).status_code == 200


def test_dos_citas_en_el_mismo_minuto_con_el_mismo_medico_se_rechazan_pero_a_otro_minuto_no(client, proveedor):
    cuerpo = {"clave_proveedor": proveedor["clave"], "fecha": HOY, "hora": "12:45"}
    assert client.post("/directorio-proveedores/citas", headers=proveedor["headers"], json=cuerpo).status_code == 200
    assert client.post("/directorio-proveedores/citas", headers=proveedor["headers"], json=cuerpo).status_code == 409
    assert client.post("/directorio-proveedores/citas", headers=proveedor["headers"], json={**cuerpo, "hora": "12:50"}).status_code == 200


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


# ---------- Coordinar cita desde un expediente (botón del Proveedor en Seguimiento) ----------

def _auth_headers_proveedor(client):
    import app.repositories.accesos_repo as accesos_repo_module

    accesos_repo_module.alta_acceso(
        "RFCPROTEST", "Proveedor de Prueba", accesos_repo_module.PERFIL_PROVEEDOR, "Jalisco", "prov@ejemplo.com"
    )
    accesos_repo_module.crear_password("RFCPROTEST", "Proveedor2024")
    r = client.post("/auth/rfc/login", json={"rfc": "RFCPROTEST", "password": "Proveedor2024"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _falso_expediente(monkeypatch, estatus="En Espera de Respuesta", existe=True):
    """El expediente viene de SQL Server en producción; aquí se simula."""
    import app.repositories.expedientes_repo as expedientes_repo
    from app.schemas.expediente import EstatusExpediente, Expediente

    def listar(filtro):
        if not existe:
            return []
        return [Expediente(
            expediente=filtro.cl_expediente, cuenta="Cuenta Demo", tipo_servicio="Asistencia Médica",
            tipo_subservicio="Consulta Médica en Consultorio", nombre_paciente="Juan de Dios Peralta",
            especialidad="CARDIOLOGIA", entidad="JALISCO", municipio="GUADALAJARA",
            fecha_apertura_servicio=date.today(), fecha_apertura_completa=date.today().isoformat() + "T08:00:00",
            estatus=EstatusExpediente(estatus),
        )]

    monkeypatch.setattr(expedientes_repo, "listar_expedientes", listar)


@pytest.fixture()
def prov_headers(client):
    return _auth_headers_proveedor(client)


def _cita_de_expediente(client, headers, proveedor, expediente=5001, hora="09:00", fecha=None):
    return client.post("/directorio-proveedores/citas", headers=headers, json={
        "clave_proveedor": proveedor["clave"], "fecha": fecha or HOY, "hora": hora, "cl_expediente": expediente,
    })


def test_coordinar_cita_toma_el_paciente_del_expediente_y_devuelve_el_texto(client, proveedor, prov_headers, monkeypatch):
    _falso_expediente(monkeypatch)
    r = client.post("/directorio-proveedores/citas", headers=prov_headers, json={
        "clave_proveedor": proveedor["clave"], "fecha": HOY, "hora": "10:30", "cl_expediente": 5001,
        "paciente": "Nombre que mandó el navegador",
    })
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["cl_expediente"] == 5001
    texto = cuerpo["observaciones_sugeridas"]
    # El paciente sale del expediente, no de lo que manda el navegador.
    assert "Paciente: Juan de Dios Peralta" in texto
    assert "Nombre que mandó el navegador" not in texto
    # Trae el médico, su especialidad, el contacto, la fecha y hora y el folio.
    assert texto.startswith(f"CITA COORDINADA - Folio {cuerpo['folio']}")
    assert "Médico: Dra. Laura Méndez Ruiz" in texto
    assert "Especialidad: Cardiología" in texto
    assert "Teléfono: No registrado" in texto and "Correo: No registrado" in texto
    assert "10:30 hrs" in texto
    assert "Horario de atención: Lun-Vie 09:00-14:00" in texto
    assert proveedor["clave"] in texto
    # Lo que no se capturó no se imprime como renglón vacío.
    assert "Costo de consulta" not in texto and "Convenio:" not in texto

    guardada = client.get("/directorio-proveedores/citas", headers=prov_headers).json()[0]
    assert guardada["cl_expediente"] == 5001 and guardada["paciente"] == "Juan de Dios Peralta"


def test_un_expediente_solo_puede_tener_una_cita_activa(client, proveedor, prov_headers, monkeypatch):
    _falso_expediente(monkeypatch)
    assert _cita_de_expediente(client, prov_headers, proveedor, hora="09:00").status_code == 200
    segunda = _cita_de_expediente(client, prov_headers, proveedor, hora="12:00")
    assert segunda.status_code == 409
    assert "ya tiene una cita agendada" in segunda.json()["detail"]
    assert "Dra. Laura Méndez Ruiz" in segunda.json()["detail"]
    # La segunda no dejó nada guardado ni apartó el horario.
    assert len(client.get("/directorio-proveedores/citas", headers=prov_headers).json()) == 1
    agenda = client.get(f"/directorio-proveedores/{proveedor['clave']}/agenda", headers=prov_headers).json()
    assert "12:00" in agenda[0]["horarios"]


def test_para_cambiar_la_cita_primero_se_cancela_y_luego_se_agenda_otra(client, proveedor, prov_headers, monkeypatch):
    _falso_expediente(monkeypatch)
    primera = _cita_de_expediente(client, prov_headers, proveedor, hora="09:00").json()
    assert client.post(f"/directorio-proveedores/citas/{primera['folio']}/cancelar", headers=prov_headers).status_code == 200
    vigente = client.get("/directorio-proveedores/citas/expediente/5001", headers=prov_headers).json()
    assert vigente["cita"] is None

    nueva = _cita_de_expediente(client, prov_headers, proveedor, hora="12:00")
    assert nueva.status_code == 200
    assert nueva.json()["folio"] != primera["folio"]
    vigente = client.get("/directorio-proveedores/citas/expediente/5001", headers=prov_headers).json()["cita"]
    assert vigente["folio"] == nueva.json()["folio"]
    assert vigente["hora"] == "12:00"
    assert "Folio " + nueva.json()["folio"] in vigente["observaciones_sugeridas"]


def test_dos_expedientes_distintos_si_pueden_tener_cada_uno_su_cita(client, proveedor, prov_headers, monkeypatch):
    _falso_expediente(monkeypatch)
    assert _cita_de_expediente(client, prov_headers, proveedor, expediente=5001, hora="09:00").status_code == 200
    assert _cita_de_expediente(client, prov_headers, proveedor, expediente=5002, hora="10:30").status_code == 200


def test_el_expediente_tiene_que_seguir_en_una_etapa_donde_el_proveedor_actua(client, proveedor, prov_headers, monkeypatch):
    for estatus in ("Seguimiento Proveedor", "Finalizado", "Abierto"):
        _falso_expediente(monkeypatch, estatus=estatus)
        r = _cita_de_expediente(client, prov_headers, proveedor)
        assert r.status_code == 400, estatus
    # También en "Seguimiento de Cita" (segunda vuelta) se puede coordinar.
    _falso_expediente(monkeypatch, estatus="Seguimiento de Cita")
    assert _cita_de_expediente(client, prov_headers, proveedor).status_code == 200


def test_coordinar_con_un_expediente_inexistente_regresa_404(client, proveedor, prov_headers, monkeypatch):
    _falso_expediente(monkeypatch, existe=False)
    assert _cita_de_expediente(client, prov_headers, proveedor).status_code == 404


def test_solo_el_proveedor_coordina_desde_un_expediente(client, proveedor, monkeypatch):
    _falso_expediente(monkeypatch)
    # Administrador puede agendar una cita suelta, pero no ligarla a un expediente.
    r = _cita_de_expediente(client, proveedor["headers"], proveedor)
    assert r.status_code == 403
    # Cabina no entra al directorio.
    assert _cita_de_expediente(client, _auth_headers_cabina(client), proveedor).status_code == 403


def test_no_se_cancela_una_cita_de_expediente_que_ya_salio_de_sus_manos(client, proveedor, prov_headers, monkeypatch):
    _falso_expediente(monkeypatch)
    cita = _cita_de_expediente(client, prov_headers, proveedor).json()
    # El Proveedor ya mandó su seguimiento: el expediente pasó a revisión del coordinador.
    _falso_expediente(monkeypatch, estatus="Seguimiento Proveedor")
    r = client.post(f"/directorio-proveedores/citas/{cita['folio']}/cancelar", headers=prov_headers)
    assert r.status_code == 400
    assert client.get("/directorio-proveedores/citas", headers=prov_headers).json()[0]["estatus"] == "Agendada"


def test_consultar_la_cita_de_un_expediente_no_filtra_el_paciente_a_quien_no_tiene_acceso(client, proveedor, prov_headers, monkeypatch):
    _falso_expediente(monkeypatch)
    _cita_de_expediente(client, prov_headers, proveedor)
    _falso_expediente(monkeypatch, estatus="Finalizado")   # ya no es de su incumbencia
    r = client.get("/directorio-proveedores/citas/expediente/5001", headers=prov_headers)
    assert r.status_code == 400 and "Juan" not in r.text


def test_la_cita_suelta_del_directorio_sigue_funcionando_sin_expediente(client, proveedor):
    r = client.post("/directorio-proveedores/citas", headers=proveedor["headers"], json={
        "clave_proveedor": proveedor["clave"], "fecha": HOY, "hora": "13:30", "paciente": "Ana",
    })
    assert r.status_code == 200
    assert "observaciones_sugeridas" not in r.json() and r.json()["cl_expediente"] is None


def test_el_texto_de_la_cita_es_lo_mas_completo_posible(client):
    from app.services.cita_texto_service import observaciones_de_cita

    proveedor = {
        "clave": "PRV-000007", "nombre": "Dr. Completo", "especialidad": "CARDIOLOGIA", "consultorio": "Consultorio 302",
        "calle_num_ext_int": "Av. Vallarta 1450, Int. 302", "colonia": "Americana", "codigo_postal": "6700",
        "municipio": "Guadalajara", "estado": "Jalisco", "telefono": "33 1234 5678", "email": "dr@correo.mx",
        "horario": "Lun-Vie 09:00-14:00", "costo_consulta": "800", "convenio": "GNP", "teleconsulta": 1,
    }
    cita = {"folio": "CITA-00009", "fecha": "2026-10-26", "hora": "10:30"}
    texto = observaciones_de_cita(proveedor, cita, "Juan Pérez")
    for esperado in (
        "Folio CITA-00009", "Paciente: Juan Pérez", "Médico: Dr. Completo", "Especialidad: CARDIOLOGIA",
        "Consultorio: Consultorio 302", "Domicilio: Av. Vallarta 1450, Int. 302, Americana, C.P. 06700, Guadalajara, Jalisco",
        "Teléfono: 33 1234 5678", "Correo: dr@correo.mx", "Fecha y hora de la cita: Lun 26/10/2026, 10:30 hrs",
        "Horario de atención: Lun-Vie 09:00-14:00", "Costo de consulta: $800", "Convenio: GNP", "Teleconsulta: Sí",
        "Clave del proveedor: PRV-000007",
    ):
        assert esperado in texto, esperado
    assert len(texto) < 1000


def test_la_agenda_de_un_dia_lejano_se_consulta_con_desde(client, proveedor):
    dia = (date.today() + timedelta(days=90)).isoformat()
    r = client.get(
        f"/directorio-proveedores/{proveedor['clave']}/agenda", params={"desde": dia, "dias": 1},
        headers=proveedor["headers"],
    )
    assert r.status_code == 200
    cuerpo = r.json()
    assert len(cuerpo) == 1 and cuerpo[0]["fecha"] == dia
    assert cuerpo[0]["horarios"] == list(HORARIOS_BASE)
    fuera = (date.today() + timedelta(days=DIAS_CITA_MAXIMO + 1)).isoformat()
    assert client.get(
        f"/directorio-proveedores/{proveedor['clave']}/agenda", params={"desde": fuera}, headers=proveedor["headers"]
    ).status_code == 400


def test_la_agenda_de_hoy_ya_no_ofrece_los_horarios_que_pasaron(client, proveedor, monkeypatch):
    monkeypatch.setattr(
        agenda_proveedores_service, "ahora", lambda: datetime.combine(date.today(), time(12, 15))
    )
    hoy = client.get(f"/directorio-proveedores/{proveedor['clave']}/agenda", headers=proveedor["headers"]).json()[0]
    assert hoy["fecha"] == HOY
    assert hoy["horarios"] == ["13:30", "16:00", "17:30", "19:00"]
