"""
Validación de RFC y cédula del "Alta de médico" y sus documentos opcionales
(constancia de situación fiscal y cédula profesional). NO requiere SQL
Server: todo vive en SQLite local.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import validacion_rfc_cedula_service as validacion

PDF = b"%PDF-1.4\n% prueba\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20


# ---------- RFC: formato ----------

@pytest.mark.parametrize("rfc, tipo", [
    ("GODE561231GR8", validacion.TIPO_FISICA),   # ejemplo oficial del SAT, persona física
    ("MAB9307148T4", validacion.TIPO_MORAL),     # ejemplo oficial del SAT, persona moral
])
def test_rfc_oficiales_validos_con_digito_correcto(rfc, tipo):
    revision = validacion.revisar_rfc(rfc)
    assert revision.tipo == tipo
    assert revision.digito_correcto is True


def test_rfc_se_normaliza():
    assert validacion.revisar_rfc(" gode-561231 gr8 ").rfc == "GODE561231GR8"


def test_rfc_con_digito_que_no_cuadra_es_advertencia_no_rechazo():
    revision = validacion.revisar_rfc("GODE561231GR9")
    assert revision.tipo == validacion.TIPO_FISICA
    assert revision.digito_correcto is False


@pytest.mark.parametrize("rfc, fragmento", [
    ("", "obligatorio"),
    ("GODE5612", "13 caracteres"),
    ("GODE561231GR8X", "tiene 14"),
    ("GOD1561231GR8", "4 letras"),          # 13 caracteres pero con un número entre las letras
    ("GODE561331GR8", "fecha"),             # mes 13
    ("GODE560230GR8", "fecha"),             # 30 de febrero
    ("XAXX010101000", "genérico"),
    ("XEXX010101000", "genérico"),
])
def test_rfc_mal_formado_se_rechaza(rfc, fragmento):
    with pytest.raises(validacion.DatoInvalido) as e:
        validacion.revisar_rfc(rfc)
    assert fragmento in str(e.value)


def test_29_de_febrero_vale_si_existe_en_algun_siglo():
    # 2000 fue bisiesto: 000229 existe aunque 1900 no lo fuera.
    validacion.revisar_rfc("GODE000229GR8")


# ---------- Cédula: formato ----------

@pytest.mark.parametrize("cedula", ["1234567", "12345678", " 1234 5678 "])
def test_cedula_valida(cedula):
    assert validacion.revisar_cedula(cedula).isdigit()


@pytest.mark.parametrize("cedula", ["", "123456", "123456789", "12A45678"])
def test_cedula_invalida(cedula):
    with pytest.raises(validacion.DatoInvalido):
        validacion.revisar_cedula(cedula)


# ---------- API ----------

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


def _login(client, rfc, perfil, password="Prueba2024$"):
    import app.repositories.accesos_repo as accesos

    accesos.alta_acceso(rfc, "Usuario " + rfc, perfil)
    accesos.crear_password(rfc, password)
    r = client.post("/auth/rfc/login", json={"rfc": rfc, "password": password})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _admin(client):
    from app.repositories.accesos_repo import PERFIL_ADMINISTRADOR
    return _login(client, "RFCADMTEST", PERFIL_ADMINISTRADOR)


def _proveedor(client, rfc="RFCPROTEST"):
    from app.repositories.accesos_repo import PERFIL_PROVEEDOR
    return _login(client, rfc, PERFIL_PROVEEDOR)


SOLICITUD = {
    "nombre": "Dr. Emilio Gómez", "especialidad": "Cardiología", "cedula": "12345678",
    "rfc": "gode561231gr8", "estado": "Jalisco", "municipio": "Guadalajara",
    "calle_num_ext_int": "Av. Vallarta 1450", "colonia": "Americana", "codigo_postal": "44100",
    "consultorio": "Consultorio 302", "horario": "Lun-Vie 09:00-14:00; Sáb 09:00-13:00", "costo_consulta": "600-900",
    "telefono": "3312345678", "email": "emilio@correo.mx",
}


def _crear(client, headers, **cambios):
    return client.post("/solicitudes-alta-medico", headers=headers, json={**SOLICITUD, **cambios})


def test_rfc_es_obligatorio(client):
    sin_rfc = {k: v for k, v in SOLICITUD.items() if k != "rfc"}
    assert client.post("/solicitudes-alta-medico", headers=_admin(client), json=sin_rfc).status_code == 422


@pytest.mark.parametrize("cambios, fragmento", [
    ({"rfc": "GODE561331GR8"}, "fecha"),
    ({"rfc": "XAXX010101000"}, "genérico"),
    ({"cedula": "12AB5678"}, "7 u 8 dígitos"),
])
def test_crear_rechaza_rfc_o_cedula_mal_formados(client, cambios, fragmento):
    r = _crear(client, _admin(client), **cambios)
    assert r.status_code == 400
    assert fragmento in r.json()["detail"]


@pytest.mark.parametrize("campo", [
    "nombre", "especialidad", "cedula", "rfc", "estado", "municipio",
    "calle_num_ext_int", "colonia", "codigo_postal", "consultorio", "horario", "costo_consulta", "telefono", "email",
])
def test_todos_los_campos_son_obligatorios(client, campo):
    admin = _admin(client)
    sin_campo = {k: v for k, v in SOLICITUD.items() if k != campo}
    assert client.post("/solicitudes-alta-medico", headers=admin, json=sin_campo).status_code == 422
    en_blanco = {**SOLICITUD, campo: "   "}
    assert client.post("/solicitudes-alta-medico", headers=admin, json=en_blanco).status_code == 400


@pytest.mark.parametrize("cambios, fragmento", [
    ({"telefono": "331234567"}, "10 dígitos"),
    ({"telefono": "33123456789"}, "10 dígitos"),
    ({"telefono": "33123abc78"}, "10 dígitos"),
    ({"codigo_postal": "4410"}, "5 dígitos"),
    ({"codigo_postal": "44A00"}, "5 dígitos"),
    ({"email": "sin-arroba.com"}, "formato"),
    ({"email": "a@b"}, "formato"),
])
def test_telefono_codigo_postal_y_correo_con_formato(client, cambios, fragmento):
    r = client.post("/solicitudes-alta-medico", headers=_admin(client), json={**SOLICITUD, **cambios})
    assert r.status_code == 400
    assert fragmento in r.json()["detail"]


@pytest.mark.parametrize("horario", [
    "Lun 09:00-14:00",
    "Lun-Vie 09:00-14:00",
    "Lun, Mié, Vie 16:00-19:30",
    "Lun-Vie 09:00-14:00; Sáb 09:00-13:00; Dom 10:00-12:00",
])
def test_horarios_validos(horario):
    assert validacion.revisar_horario(horario) == horario


@pytest.mark.parametrize("horario, fragmento", [
    ("Lun-Vie 14:00-09:00", "anterior"),
    ("Lun-Vie 09:00-09:00", "anterior"),
    ("Vie-Lun 09:00-14:00", "en orden"),
    ("Lun-Vie 9:00-14:00", "formato"),
    ("Lun-Vie 09:00-25:00", "formato"),
    ("Lunes 09:00-14:00", "formato"),
    ("Lun-Vie", "formato"),
    ("de lunes a viernes por la mañana", "formato"),
    ("Lun-Vie 09:00-14:00;Sáb 09:00-13:00", "formato"),
    ("", "obligatorio"),
])
def test_horarios_invalidos(horario, fragmento):
    with pytest.raises(validacion.DatoInvalido) as e:
        validacion.revisar_horario(horario)
    assert fragmento in str(e.value)


def test_horario_invalido_se_rechaza_en_la_api(client):
    r = _crear(client, _admin(client), horario="Lun-Vie 14:00-09:00")
    assert r.status_code == 400
    assert "horario" in r.json()["detail"].lower()


def test_consultorio_y_horario_pasan_al_padron_al_aprobar(client):
    admin = _admin(client)
    folio = _crear(client, admin).json()["folio"]
    assert client.post(f"/solicitudes-alta-medico/{folio}/estatus", headers=admin, json={"estatus": "Aprobada"}).status_code == 200
    medico = client.get("/directorio-proveedores", headers=admin).json()[0]
    assert medico["consultorio"] == "Consultorio 302"
    assert medico["horario"] == "Lun-Vie 09:00-14:00; Sáb 09:00-13:00"


# ---------- Costo aproximado ----------

@pytest.mark.parametrize("costo", ["0-600", "600-900", "900-1200", "1200+"])
def test_costo_aproximado_por_rango(client, costo):
    admin = _admin(client)
    assert _crear(client, admin, costo_consulta=costo).status_code == 200
    assert client.get("/solicitudes-alta-medico", headers=admin).json()[0]["costo_consulta"] == costo


@pytest.mark.parametrize("costo", ["800", "$800", "500-700", "barato"])
def test_costo_fuera_de_los_rangos_se_rechaza(client, costo):
    r = _crear(client, _admin(client), costo_consulta=costo)
    assert r.status_code == 400 and "rangos" in r.json()["detail"]


def test_el_costo_pasa_al_padron_al_aprobar(client):
    admin = _admin(client)
    folio = _crear(client, admin, costo_consulta="900-1200").json()["folio"]
    client.post(f"/solicitudes-alta-medico/{folio}/estatus", headers=admin, json={"estatus": "Aprobada"})
    assert client.get("/directorio-proveedores", headers=admin).json()[0]["costo_consulta"] == "900-1200"


# ---------- Duplicados: un RFC puede tener varias altas, no la misma especialidad en el mismo domicilio ----------

def test_mismo_rfc_misma_especialidad_mismo_domicilio_se_rechaza(client):
    admin = _admin(client)
    assert _crear(client, admin).status_code == 200
    # Aunque el domicilio venga escrito distinto (mayúsculas, acentos, signos).
    r = _crear(client, admin, calle_num_ext_int="AV VALLARTA #1450", especialidad="cardiologia")
    assert r.status_code == 409
    assert "otra especialidad o en otro domicilio" in r.json()["detail"]


def test_mismo_rfc_con_otra_especialidad_o_en_otra_sucursal_si_se_permite(client):
    admin = _admin(client)
    assert _crear(client, admin).status_code == 200
    assert _crear(client, admin, especialidad="Medicina General").status_code == 200
    assert _crear(client, admin, calle_num_ext_int="Av. Patria 200", codigo_postal="45110").status_code == 200


def test_una_solicitud_rechazada_no_impide_volver_a_intentarlo(client):
    admin = _admin(client)
    folio = _crear(client, admin).json()["folio"]
    client.post(f"/solicitudes-alta-medico/{folio}/estatus", headers=admin, json={"estatus": "Rechazada"})
    assert _crear(client, admin).status_code == 200


def test_tampoco_se_repite_lo_que_ya_esta_en_el_padron(client):
    admin = _admin(client)
    folio = _crear(client, admin).json()["folio"]
    client.post(f"/solicitudes-alta-medico/{folio}/estatus", headers=admin, json={"estatus": "Aprobada"})
    assert _crear(client, admin).status_code == 409


def test_editar_una_solicitud_no_choca_consigo_misma_pero_si_con_otra(client):
    admin = _admin(client)
    folio = _crear(client, admin).json()["folio"]
    assert client.put(f"/solicitudes-alta-medico/{folio}", headers=admin, json={**SOLICITUD, "nombre": "Dr. Otro"}).status_code == 200
    otra = _crear(client, admin, especialidad="Pediatría").json()["folio"]
    r = client.put(f"/solicitudes-alta-medico/{otra}", headers=admin, json=SOLICITUD)
    assert r.status_code == 409


def test_telefono_con_separadores_se_guarda_solo_con_digitos(client):
    admin = _admin(client)
    r = client.post("/solicitudes-alta-medico", headers=admin, json={**SOLICITUD, "telefono": "(33) 1234-5678"})
    assert r.status_code == 200, r.text
    assert client.get("/solicitudes-alta-medico", headers=admin).json()[0]["telefono"] == "3312345678"


def test_editar_tambien_valida(client):
    admin = _admin(client)
    folio = _crear(client, admin).json()["folio"]
    r = client.put(f"/solicitudes-alta-medico/{folio}", headers=admin, json={**SOLICITUD, "rfc": "ABC"})
    assert r.status_code == 400


def test_rfc_se_guarda_normalizado_y_la_lista_trae_su_revision(client):
    admin = _admin(client)
    _crear(client, admin)
    _crear(client, admin, rfc="MAB9307148T4")
    _crear(client, admin, rfc="GODE561231GR9")
    filas = {f["rfc"]: f for f in client.get("/solicitudes-alta-medico", headers=admin).json()}
    assert filas["GODE561231GR8"]["rfc_revision"] == {"tipo": "fisica", "formato_valido": True, "digito_correcto": True}
    assert filas["MAB9307148T4"]["rfc_revision"]["tipo"] == "moral"
    assert filas["GODE561231GR9"]["rfc_revision"]["digito_correcto"] is False
    assert all(f["documentos"] == {} for f in filas.values())


def test_la_revision_del_rfc_solo_la_recibe_el_administrador(client):
    proveedor = _proveedor(client)
    _crear(client, proveedor, rfc="GODE561231GR9")
    fila = client.get("/solicitudes-alta-medico", headers=proveedor).json()[0]
    assert "rfc_revision" not in fila
    assert "rfc_revision" in client.get("/solicitudes-alta-medico", headers=_admin(client)).json()[0]


def test_solicitud_vieja_sin_rfc_se_sigue_listando(client):
    from app.repositories import solicitudes_alta_medico_repo

    admin = _admin(client)
    solicitudes_alta_medico_repo.crear_solicitud({**SOLICITUD, "rfc": None}, "RFCADMTEST")
    fila = client.get("/solicitudes-alta-medico", headers=admin).json()[0]
    assert fila["rfc_revision"]["formato_valido"] is False


# ---------- Documentos ----------

def _subir(client, headers, folio, tipo, contenido=PDF, nombre="constancia.pdf", mime="application/pdf"):
    return client.post(
        f"/solicitudes-alta-medico/{folio}/documentos/{tipo}", headers=headers,
        files={"archivo": (nombre, contenido, mime)},
    )


def test_quien_captura_sube_y_el_administrador_lo_ve(client):
    proveedor = _proveedor(client)
    folio = _crear(client, proveedor).json()["folio"]
    assert _subir(client, proveedor, folio, "constancia_fiscal").status_code == 200
    assert _subir(client, proveedor, folio, "cedula", PNG, "cédula.png", "image/png").status_code == 200

    admin = _admin(client)
    fila = client.get("/solicitudes-alta-medico", headers=admin).json()[0]
    assert set(fila["documentos"]) == {"constancia_fiscal", "cedula"}
    assert fila["documentos"]["cedula"]["nombre_archivo"] == "cédula.png"

    r = client.get(f"/solicitudes-alta-medico/{folio}/documentos/cedula", headers=admin)
    assert r.status_code == 200
    assert r.content == PNG
    assert r.headers["content-type"] == "image/png"


def test_otro_proveedor_no_ve_ni_sube_documentos_ajenos(client):
    duenio = _proveedor(client)
    folio = _crear(client, duenio).json()["folio"]
    _subir(client, duenio, folio, "constancia_fiscal")
    otro = _proveedor(client, "RFCPROOTRO")
    assert client.get(f"/solicitudes-alta-medico/{folio}/documentos/constancia_fiscal", headers=otro).status_code == 403
    assert _subir(client, otro, folio, "constancia_fiscal").status_code == 403


def test_subir_otra_vez_reemplaza(client):
    admin = _admin(client)
    folio = _crear(client, admin).json()["folio"]
    _subir(client, admin, folio, "cedula", PDF, "vieja.pdf")
    _subir(client, admin, folio, "cedula", PNG, "nueva.png", "image/png")
    fila = client.get("/solicitudes-alta-medico", headers=admin).json()[0]
    assert fila["documentos"]["cedula"]["nombre_archivo"] == "nueva.png"


@pytest.mark.parametrize("contenido, nombre, mime, fragmento", [
    (b"PK\x03\x04", "cedula.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "Formato no permitido"),
    (b"no soy un pdf", "falso.pdf", "application/pdf", "no corresponde"),
    (b"%PDF" + b"0" * (5 * 1024 * 1024), "grande.pdf", "application/pdf", "5 MB"),
], ids=["word", "contenido-falso", "mas-de-5mb"])
def test_rechaza_formatos_contenido_falso_y_tamano(client, contenido, nombre, mime, fragmento):
    admin = _admin(client)
    folio = _crear(client, admin).json()["folio"]
    r = _subir(client, admin, folio, "cedula", contenido, nombre, mime)
    assert r.status_code == 400
    assert fragmento in r.json()["detail"]


def test_tipo_de_documento_desconocido(client):
    admin = _admin(client)
    folio = _crear(client, admin).json()["folio"]
    assert _subir(client, admin, folio, "pasaporte").status_code == 404


def test_quitar_documento(client):
    admin = _admin(client)
    folio = _crear(client, admin).json()["folio"]
    _subir(client, admin, folio, "constancia_fiscal")
    assert client.delete(f"/solicitudes-alta-medico/{folio}/documentos/constancia_fiscal", headers=admin).status_code == 200
    assert client.get(f"/solicitudes-alta-medico/{folio}/documentos/constancia_fiscal", headers=admin).status_code == 404


def test_resuelta_ya_no_cambia_sus_documentos_pero_se_siguen_viendo(client):
    admin = _admin(client)
    folio = _crear(client, admin).json()["folio"]
    _subir(client, admin, folio, "constancia_fiscal")
    client.post(f"/solicitudes-alta-medico/{folio}/estatus", headers=admin, json={"estatus": "Aprobada"})

    assert _subir(client, admin, folio, "cedula").status_code == 409
    assert client.delete(f"/solicitudes-alta-medico/{folio}/documentos/constancia_fiscal", headers=admin).status_code == 409
    assert client.get(f"/solicitudes-alta-medico/{folio}/documentos/constancia_fiscal", headers=admin).status_code == 200
