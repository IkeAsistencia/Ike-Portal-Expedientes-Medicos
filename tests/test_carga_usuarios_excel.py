"""
Carga masiva de usuarios desde Excel dentro del portal (POST /admin/accesos/carga-excel
y app/services/carga_usuarios_service.py), con archivos armados como los que mandan las
áreas: el de Cabina trae el encabezado en el renglón 2, una columna A vacía y dos hojas;
el de Proveedores no trae ROL ni entidad y los RFC llevan homoclave (13 caracteres).
"""

import io

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.core.rate_limit import limpiar_todo
from app.main import app
from app.repositories import accesos_repo
from app.repositories.accesos_repo import PERFIL_ADMINISTRADOR, PERFIL_CABINA, PERFIL_PROVEEDOR
from app.services.carga_usuarios_service import ErrorCargaUsuarios, leer_filas

RFC_ADMIN = "ROCM940213"
PASSWORD = "Clave#2026"
TIPO_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    for nombre, valor in {
        "DB_AUTH_MODE": "sql", "DB_SERVER": "servidor-fake", "DB_NAME": "bd-fake",
        "DB_USER": "usuario-fake", "DB_PASSWORD": "password-fake", "JWT_SECRET_KEY": "clave-de-prueba",
        "LOCAL_DB_PATH": str(tmp_path / "carga.db"),
    }.items():
        monkeypatch.setenv(nombre, valor)
    get_settings.cache_clear()

    import app.main as main_module

    monkeypatch.setattr(main_module, "calentar_pool", lambda: None)
    limpiar_todo()
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def _admin(client) -> dict:
    accesos_repo.alta_acceso(RFC_ADMIN, "Carlos Pineda", PERFIL_ADMINISTRADOR)
    accesos_repo.establecer_password(RFC_ADMIN, PASSWORD)
    r = client.post("/auth/rfc/login", json={"rfc": RFC_ADMIN, "password": PASSWORD})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _bytes(libro: openpyxl.Workbook) -> bytes:
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def excel_cabina(extra_en_cami: tuple = ()) -> bytes:
    """Como "usuarios cabina.xlsx": renglón 1 vacío, columna A vacía, encabezado en el 2, dos hojas."""
    libro = openpyxl.Workbook()
    medicos = libro.active
    medicos.title = "Médicos"
    medicos.append([])
    medicos.append([None, "RFC", "NOMBRE DEL COORDINADOR", "POSICIÓN", "TURNO", "CABINA POR GRUPO"])
    medicos.append([None, "MIMA9911294BA", "MIRANDA MARTINEZ ANA KAREN", "MEDICO", "MATUTINO", "MEDICA"])
    medicos.append([None, "GAUL920124CM1", "GARCIA URIBE LUIS FRANCISCO", "VETERINARIO", "VESPERTINO", "MEDICA"])
    cami = libro.create_sheet("CAMI")
    cami.append([])
    cami.append([None, "RFC", "NOMBRE DEL COORDINADOR", "POSICIÓN", "TURNO", "CABINA POR GRUPO"])
    cami.append([None, "SEAL641014DH4", "STEVENS AVILA LEONARDO", "COORDINADOR", "VESPERTINO", "CAMI"])
    for fila in extra_en_cami:
        cami.append(list(fila))
    return _bytes(libro)


def excel_proveedores(filas: tuple | None = None) -> bytes:
    """Como "usuariosproveedores.xlsx": renglón 1 vacío; Usuario, Correo y RFC (con homoclave)."""
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.title = "Hoja1"
    hoja.append([])
    hoja.append(["Usuario", "Correo", "RFC"])
    for fila in filas or (
        ("José Cupertino Quintanar Hernandez", "jquintanar@ikeasistencia.com", "QUHC890125IZ6"),
        ("Luis Angel Solares Hernandez", "lusolares@ikeasistencia.com", "SOGL980913L6A"),
    ):
        hoja.append(list(fila))
    return _bytes(libro)


def _cargar(client, headers, contenido: bytes, tipo: str, aplicar: bool, nombre: str = "usuarios.xlsx"):
    return client.post(
        "/admin/accesos/carga-excel",
        data={"tipo": tipo, "aplicar": "true" if aplicar else "false"},
        files={"archivo": (nombre, contenido, TIPO_XLSX)},
        headers=headers,
    )


# ---------- Lectura del archivo ----------

def test_lee_el_formato_de_cabina_con_encabezado_en_el_renglon_2_y_dos_hojas():
    filas = leer_filas(io.BytesIO(excel_cabina()), rol_por_defecto="CABINA")

    assert [(f["hoja"], f["rfc"], f["nombre"], f["rol"]) for f in filas] == [
        ("Médicos", "MIMA991129", "MIRANDA MARTINEZ ANA KAREN", "CABINA"),  # homoclave fuera: solo 10
        ("Médicos", "GAUL920124", "GARCIA URIBE LUIS FRANCISCO", "CABINA"),
        ("CAMI", "SEAL641014", "STEVENS AVILA LEONARDO", "CABINA"),
    ]
    assert filas[0]["renglon"] == 3


def test_lee_el_formato_de_proveedores_con_usuario_correo_y_rfc():
    filas = leer_filas(io.BytesIO(excel_proveedores()), rol_por_defecto="PROVEEDOR")

    assert filas[0]["rfc"] == "QUHC890125"
    assert filas[0]["nombre"] == "José Cupertino Quintanar Hernandez"
    assert filas[0]["correo"] == "jquintanar@ikeasistencia.com"
    assert filas[0]["entidad"] is None


def test_el_tipo_elegido_manda_sobre_la_columna_rol():
    libro = openpyxl.Workbook()
    libro.active.append(["RFC", "NOMBRE", "ROL"])
    libro.active.append(["MIMA991129", "Miranda", "ADMINISTRADOR"])

    assert leer_filas(io.BytesIO(_bytes(libro)), rol_por_defecto="CABINA")[0]["rol"] == "CABINA"
    assert leer_filas(io.BytesIO(_bytes(libro)))[0]["rol"] == "ADMINISTRADOR"


def test_sin_columna_rfc_o_sin_nombre_avisa():
    libro = openpyxl.Workbook()
    libro.active.append(["CLAVE", "NOMBRE"])
    libro.active.append(["MIMA991129", "Miranda"])
    with pytest.raises(ErrorCargaUsuarios, match="RFC"):
        leer_filas(io.BytesIO(_bytes(libro)), rol_por_defecto="CABINA")

    libro = openpyxl.Workbook()
    libro.active.append(["RFC", "TELEFONO"])
    libro.active.append(["MIMA991129", "5555"])
    with pytest.raises(ErrorCargaUsuarios, match="NOMBRE"):
        leer_filas(io.BytesIO(_bytes(libro)), rol_por_defecto="CABINA")


# ---------- Desde la pantalla ----------

def test_la_vista_previa_no_escribe_nada(client):
    headers = _admin(client)

    r = _cargar(client, headers, excel_cabina(), "cabina", aplicar=False)

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["aplicado"] is False
    assert (data["total"], data["nuevos"], data["rechazadas"]) == (3, 3, 0)
    assert accesos_repo.buscar_acceso("MIMA991129") is None


def test_carga_de_cabina_da_de_alta_con_rfc_de_10_y_sin_contrasena(client):
    headers = _admin(client)

    r = _cargar(client, headers, excel_cabina(), "cabina", aplicar=True)

    assert r.status_code == 200, r.text
    assert r.json()["aplicado"] is True
    acceso = accesos_repo.buscar_acceso("MIMA991129")
    assert acceso["nombre"] == "MIRANDA MARTINEZ ANA KAREN"
    assert acceso["perfiles"] == [PERFIL_CABINA]
    assert acceso["password_hash"] is None  # la crea la persona al entrar
    assert accesos_repo.buscar_acceso("SEAL641014") is not None  # la segunda hoja también


def test_carga_de_proveedores_les_pone_ciudad_de_mexico(client):
    headers = _admin(client)

    r = _cargar(client, headers, excel_proveedores(), "proveedor", aplicar=True)

    assert r.status_code == 200, r.text
    acceso = accesos_repo.buscar_acceso("QUHC890125")
    assert acceso["perfiles"] == [PERFIL_PROVEEDOR]
    assert acceso["entidad"] == "Ciudad de México"
    assert acceso["correo"] == "jquintanar@ikeasistencia.com"


def test_repetir_la_carga_no_duplica_ni_cambia_nada(client):
    headers = _admin(client)
    _cargar(client, headers, excel_cabina(), "cabina", aplicar=True)
    accesos_repo.establecer_password("MIMA991129", PASSWORD)
    antes = accesos_repo.buscar_acceso("MIMA991129")["password_hash"]

    data = _cargar(client, headers, excel_cabina(), "cabina", aplicar=True).json()

    assert (data["nuevos"], data["perfiles_agregados"], data["ya_existian"]) == (0, 0, 3)
    assert accesos_repo.buscar_acceso("MIMA991129")["password_hash"] == antes  # su contraseña sigue
    assert len([a for a in accesos_repo.listar_accesos() if a["perfil"] == PERFIL_CABINA]) == 3


def test_quien_ya_tiene_acceso_solo_recibe_el_perfil_que_le_falta(client):
    headers = _admin(client)
    _cargar(client, headers, excel_cabina(), "cabina", aplicar=True)
    # Un proveedor con el mismo RFC que alguien de Cabina.
    proveedores = excel_proveedores((("Miranda Martinez", "miranda@ikeasistencia.com", "MIMA9911294BA"),))

    data = _cargar(client, headers, proveedores, "proveedor", aplicar=True).json()

    assert (data["nuevos"], data["perfiles_agregados"]) == (0, 1)
    acceso = accesos_repo.buscar_acceso("MIMA991129")
    assert acceso["perfiles"] == [PERFIL_CABINA, PERFIL_PROVEEDOR]
    assert acceso["nombre"] == "MIRANDA MARTINEZ ANA KAREN"  # no se le cambió el nombre
    assert acceso["entidad"] == "Ciudad de México"


def test_las_filas_malas_se_rechazan_con_su_motivo_y_las_buenas_se_cargan(client):
    headers = _admin(client)
    contenido = excel_proveedores((
        ("Bueno", "bueno@ikeasistencia.com", "BUEN900101ABC"),
        ("Correo ajeno", "ajeno@gmail.com", "AJEN900101ABC"),
        ("RFC corto", "corto@ikeasistencia.com", "COR900101"),
        ("", "sinnombre@ikeasistencia.com", "SINN900101ABC"),
    ))

    data = _cargar(client, headers, contenido, "proveedor", aplicar=True).json()

    assert (data["total"], data["nuevos"], data["rechazadas"]) == (4, 1, 3)
    rechazadas = {f["rfc"]: f for f in data["filas"] if f["resultado"] == "rechazada"}
    assert "dominio @ikeasistencia.com" in rechazadas["AJEN900101"]["motivo"]
    assert "RFC inválido" in rechazadas["COR900101"]["motivo"]
    assert rechazadas["SINN900101"]["motivo"] == "falta el nombre"
    assert accesos_repo.buscar_acceso("BUEN900101") is not None
    assert accesos_repo.buscar_acceso("AJEN900101") is None


def test_segun_archivo_respeta_la_columna_rol_y_la_entidad_del_archivo(client):
    headers = _admin(client)
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.append(["RFC", "NOMBRE", "ROL", "ENTIDAD", "CORREO"])
    hoja.append(["ADMI900101", "Admin Nuevo", "ADMINISTRADOR", None, None])
    hoja.append(["PROV900101", "Prov Jalisco", "PROVEEDOR", "jalisco", "j@ikeasistencia.com"])

    data = _cargar(client, headers, _bytes(libro), "segun_archivo", aplicar=True).json()

    assert (data["nuevos"], data["rechazadas"]) == (2, 0)
    assert accesos_repo.buscar_acceso("ADMI900101")["perfiles"] == [PERFIL_ADMINISTRADOR]
    assert accesos_repo.buscar_acceso("PROV900101")["entidad"] == "Jalisco"  # normalizada al catálogo


def test_solo_el_administrador_puede_cargar(client):
    accesos_repo.alta_acceso("MIMA991129", "Miranda", PERFIL_CABINA)
    accesos_repo.establecer_password("MIMA991129", PASSWORD)
    token = client.post("/auth/rfc/login", json={"rfc": "MIMA991129", "password": PASSWORD}).json()["access_token"]

    r = _cargar(client, {"Authorization": f"Bearer {token}"}, excel_cabina(), "cabina", aplicar=True)

    assert r.status_code == 403
    assert _cargar(client, {}, excel_cabina(), "cabina", aplicar=True).status_code == 401
    assert accesos_repo.buscar_acceso("SEAL641014") is None


def test_rechaza_archivos_que_no_son_excel_ni_tipos_raros(client):
    headers = _admin(client)

    assert _cargar(client, headers, b"hola", "cabina", True, nombre="usuarios.csv").status_code == 400
    assert _cargar(client, headers, b"no es un zip", "cabina", True).status_code == 400
    assert _cargar(client, headers, b"PK\x03\x04roto", "cabina", True).status_code == 400
    assert _cargar(client, headers, excel_cabina(), "administrador", True).status_code == 400
    grande = b"PK\x03\x04" + b"0" * (2 * 1024 * 1024)
    assert _cargar(client, headers, grande, "cabina", True).status_code == 400
