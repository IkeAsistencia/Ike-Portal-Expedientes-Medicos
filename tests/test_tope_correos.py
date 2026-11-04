"""
"Enviar correo a proveedores" y corte: a quién le llega el correo, el tope
diario, el aviso antes de llegar al tope y el freno de reenvío (ver
app/services/envio_correo_service.py y app/services/cuota_correos_service.py).

No requiere SQL Server ni SMTP: los expedientes salen de un SP falso y los
correos quedan simulados (o se intercepta la función que los manda).
"""

import datetime

import pytest
from fastapi.testclient import TestClient

import app.repositories.expedientes_repo as expedientes_repo_module
from app.main import app
from app.repositories import accesos_repo

# Las entidades vienen como las manda SQL Server: MAYÚSCULAS, sin acentos, y
# el Estado de México como "MEXICO".
EXPEDIENTES = {
    3001: "CAMPECHE",
    3002: "YUCATAN",
    3003: "MEXICO",
    3004: None,
    3005: "CAMPECHE",
}


def _fila(expediente: int, entidad: str | None) -> dict:
    return {
        "Expediente": expediente,
        "Cuenta": "Cuenta Demo",
        "TipoServicio": "Servicio Médico",
        "TipoSubservicio": "Consulta Externa",
        "NombreTitular": "Titular",
        "NombrePaciente": f"Paciente {expediente}",
        "Especialidad": "Medicina General",
        "Entidad": entidad,
        "Municipio": None,
        "FechaAperturaServicio": datetime.date(2026, 10, 1),
        "FechaAperturaCompleta": datetime.datetime(2026, 10, 1, 8, 0, 0),
        "ClSubServicio": 383,
        "FechaAsignacionProveedor": None,
        "FechaCita": None,
        "Telefono": None,
        "Email": None,
    }


def _fake_call_procedure(sp_name, params=None):
    assert sp_name == "dbo.ST_CP_ObtenerExpedientesSinProveedorMedico", sp_name
    clave = (params or {}).get("clExpediente")
    return [_fila(e, ent) for e, ent in EXPEDIENTES.items() if clave in (None, e)]


@pytest.fixture(autouse=True)
def _sin_sql_server(monkeypatch):
    monkeypatch.setattr(expedientes_repo_module, "call_procedure", _fake_call_procedure)
    import app.main as main_module

    monkeypatch.setattr(main_module, "calentar_pool", lambda: None)
    from app.core.rate_limit import limpiar_todo

    limpiar_todo()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    for nombre, valor in {
        "DB_AUTH_MODE": "sql", "DB_SERVER": "servidor-fake", "DB_NAME": "bd-fake",
        "DB_USER": "usuario-fake", "DB_PASSWORD": "password-fake",
        "LOCAL_DB_PATH": str(tmp_path / "test_local.db"), "JWT_SECRET_KEY": "clave-de-prueba",
        # Simulado siempre: correr las pruebas nunca debe mandar correos reales.
        "SMTP_HOST": "", "SMTP_USER": "", "SMTP_PASSWORD": "", "SMTP_REMITENTE": "",
        "SMTP_DESTINATARIO_PRUEBA": "",
        "SMTP_LIMITE_DIARIO": "100", "SMTP_AVISO_LIMITE": "80",
        "SMTP_CUENTA_POR_DESTINATARIO": "true", "CORREO_REENVIO_HORAS": "8",
    }.items():
        monkeypatch.setenv(nombre, valor)
    from app.config import get_settings

    get_settings.cache_clear()
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def _configurar(monkeypatch, **valores):
    from app.config import get_settings

    for nombre, valor in valores.items():
        monkeypatch.setenv(nombre, str(valor))
    get_settings.cache_clear()


def _sesion(client, rfc: str, perfil: int, entidad: str | None = None, correo: str | None = None) -> dict:
    accesos_repo.alta_acceso(rfc, f"Usuario {rfc}", perfil, entidad, correo)
    accesos_repo.crear_password(rfc, "Clave2024xx")
    r = client.post("/auth/rfc/login", json={"rfc": rfc, "password": "Clave2024xx"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _cabina(client) -> dict:
    return _sesion(client, "RFCCABTEST", accesos_repo.PERFIL_CABINA)


def _admin(client) -> dict:
    return _sesion(client, "RFCADMTEST", accesos_repo.PERFIL_ADMINISTRADOR)


def _proveedor(rfc: str, entidad: str, correo: str) -> None:
    accesos_repo.alta_acceso(rfc, f"Proveedor {rfc}", accesos_repo.PERFIL_PROVEEDOR, entidad, correo)


def _enviar(client, headers, expedientes, confirmar=False):
    return client.post(
        "/expedientes/enviar-correo-proveedores",
        json={"expedientes": expedientes, "confirmar_limite": confirmar},
        headers=headers,
    )


def _estatus(client, headers, expediente) -> str:
    return client.get("/expedientes", params={"cl_expediente": expediente}, headers=headers).json()[0]["estatus"]


def _usados(client, headers) -> int:
    return client.get("/correos-enviados/cuota", headers=headers).json()["usados"]


@pytest.fixture()
def capturados(monkeypatch):
    """Lo que se le pasó a email_service.enviar_correo_proveedores en cada envío."""
    from app.services import email_service

    llamadas = []
    original = email_service.enviar_correo_proveedores

    def espia(expedientes, usuario_nombre, destinatarios, es_recordatorio=False):
        llamadas.append({"expedientes": [e["expediente"] for e in expedientes], "destinatarios": destinatarios})
        return original(expedientes, usuario_nombre, destinatarios, es_recordatorio)

    monkeypatch.setattr(email_service, "enviar_correo_proveedores", espia)
    return llamadas


# ---------- A quién le llega ----------

def test_un_solo_correo_con_toda_la_lista_a_los_proveedores_de_esas_entidades(client, capturados):
    _proveedor("PROVCAM001", "Campeche", "campeche1@example.com")
    _proveedor("PROVCAM002", "Campeche", "campeche2@example.com")
    _proveedor("PROVYUC001", "Yucatán", "yucatan@example.com")
    _proveedor("PROVJAL001", "Jalisco", "jalisco@example.com")  # Jalisco no viene en la selección
    headers = _cabina(client)

    r = _enviar(client, headers, [3001, 3002])

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["correo_enviado"] is True
    assert data["destinatarios"] == 3
    assert data["entidades_sin_proveedor"] == []
    assert len(capturados) == 1  # UN correo, no uno por entidad
    assert capturados[0]["expedientes"] == [3001, 3002]  # con la lista completa
    assert capturados[0]["destinatarios"] == [
        "campeche1@example.com", "campeche2@example.com", "yucatan@example.com"
    ]


def test_estado_de_mexico_coincide_con_mexico_de_sql_server(client, capturados):
    _proveedor("PROVMEX001", "Estado de México", "edomex@example.com")
    _proveedor("PROVCDM001", "Ciudad de México", "cdmx@example.com")
    headers = _cabina(client)

    r = _enviar(client, headers, [3003])

    assert r.status_code == 200, r.text
    assert capturados[0]["destinatarios"] == ["edomex@example.com"]


def test_proveedor_inactivo_no_recibe_correo(client, capturados):
    _proveedor("PROVCAM001", "Campeche", "activo@example.com")
    _proveedor("PROVCAM002", "Campeche", "inactivo@example.com")
    accesos_repo.inactivar_acceso("PROVCAM002")
    headers = _cabina(client)

    _enviar(client, headers, [3001])

    assert capturados[0]["destinatarios"] == ["activo@example.com"]


def test_avisa_que_entidades_no_tienen_proveedor(client):
    _proveedor("PROVCAM001", "Campeche", "campeche@example.com")
    headers = _cabina(client)

    data = _enviar(client, headers, [3001, 3002, 3004]).json()

    assert data["correo_enviado"] is True
    assert data["entidades_sin_proveedor"] == ["Sin entidad", "Yucatán"]
    assert "Yucatán" in data["mensaje"]


def test_sin_ningun_proveedor_no_sale_correo_pero_si_cambia_el_estatus(client, capturados):
    headers = _cabina(client)

    r = _enviar(client, headers, [3002])

    assert r.status_code == 200, r.text
    data = r.json()
    assert data["correo_enviado"] is False
    assert data["motivo_sin_correo"] == "sin_proveedores"
    assert capturados == []
    assert _estatus(client, headers, 3002) == "En Espera de Respuesta"
    assert _usados(client, headers) == 0


def test_proveedor_no_puede_enviar_correo(client):
    headers = _sesion(client, "RFCPROTEST", accesos_repo.PERFIL_PROVEEDOR, "Campeche", "p@example.com")
    assert _enviar(client, headers, [3001]).status_code == 403


# ---------- Contador y tope diario ----------

def test_el_contador_cuenta_un_lugar_por_destinatario(client):
    _proveedor("PROVCAM001", "Campeche", "c1@example.com")
    _proveedor("PROVCAM002", "Campeche", "c2@example.com")
    headers = _cabina(client)

    _enviar(client, headers, [3001])

    assert _usados(client, headers) == 2


def test_el_contador_puede_contar_un_lugar_por_mensaje(client, monkeypatch):
    _configurar(monkeypatch, SMTP_CUENTA_POR_DESTINATARIO="false")
    _proveedor("PROVCAM001", "Campeche", "c1@example.com")
    _proveedor("PROVCAM002", "Campeche", "c2@example.com")
    headers = _cabina(client)

    _enviar(client, headers, [3001])

    assert _usados(client, headers) == 1


def test_cerca_del_tope_pide_confirmacion_sin_hacer_nada(client, monkeypatch, capturados):
    _configurar(monkeypatch, SMTP_LIMITE_DIARIO=10, SMTP_AVISO_LIMITE=8)
    from app.services import cuota_correos_service

    cuota_correos_service.reservar("corte", 7)
    _proveedor("PROVCAM001", "Campeche", "c1@example.com")
    headers = _cabina(client)

    data = _enviar(client, headers, [3001]).json()

    assert data["requiere_confirmacion"] is True
    assert "a punto de alcanzar" in data["mensaje"]
    assert capturados == []
    assert _estatus(client, headers, 3001) == "Abierto"  # no se tocó nada
    assert _usados(client, headers) == 7

    data = _enviar(client, headers, [3001], confirmar=True).json()

    assert data["correo_enviado"] is True
    assert _usados(client, headers) == 8
    assert _estatus(client, headers, 3001) == "En Espera de Respuesta"


def test_en_el_tope_no_sale_correo_pero_los_expedientes_pasan_a_espera(client, monkeypatch, capturados):
    _configurar(monkeypatch, SMTP_LIMITE_DIARIO=3, SMTP_AVISO_LIMITE=2)
    from app.services import cuota_correos_service

    cuota_correos_service.reservar("corte", 3)
    _proveedor("PROVCAM001", "Campeche", "c1@example.com")
    headers = _cabina(client)

    data = _enviar(client, headers, [3001]).json()
    assert data["requiere_confirmacion"] is True
    assert "Ya se alcanzó el límite" in data["mensaje"]

    data = _enviar(client, headers, [3001], confirmar=True).json()

    assert data["correo_enviado"] is False
    assert data["motivo_sin_correo"] == "limite"
    assert "límite" in data["mensaje"]
    assert capturados == []
    assert _usados(client, headers) == 3
    assert _estatus(client, headers, 3001) == "En Espera de Respuesta"

    historial = client.get("/correos-enviados", headers=_admin(client)).json()
    assert historial[0]["motivo_sin_correo"] == "limite"


def test_si_el_envio_no_cabe_completo_no_sale_a_medias(client, monkeypatch, capturados):
    _configurar(monkeypatch, SMTP_LIMITE_DIARIO=3, SMTP_AVISO_LIMITE=3)
    from app.services import cuota_correos_service

    cuota_correos_service.reservar("corte", 2)
    _proveedor("PROVCAM001", "Campeche", "c1@example.com")
    _proveedor("PROVCAM002", "Campeche", "c2@example.com")
    headers = _cabina(client)

    data = _enviar(client, headers, [3001]).json()
    assert data["requiere_confirmacion"] is True
    assert "solo quedan 1" in data["mensaje"]

    data = _enviar(client, headers, [3001], confirmar=True).json()
    assert data["motivo_sin_correo"] == "limite"
    assert capturados == []
    assert _usados(client, headers) == 2


def test_si_falla_el_servidor_de_correo_no_cambia_nada(client, monkeypatch):
    from app.services import email_service

    def falla(*args, **kwargs):
        raise email_service.ErrorEnvioCorreo("timeout")

    monkeypatch.setattr(email_service, "_enviar", falla)
    _proveedor("PROVCAM001", "Campeche", "c1@example.com")
    headers = _cabina(client)

    r = _enviar(client, headers, [3001])

    assert r.status_code == 503
    assert _usados(client, headers) == 0  # lo apartado se liberó
    assert _estatus(client, headers, 3001) == "Abierto"
    assert client.get("/correos-enviados", headers=_admin(client)).json() == []


def test_cuota_la_ven_cabina_y_administrador_pero_no_proveedor(client):
    data = client.get("/correos-enviados/cuota", headers=_cabina(client)).json()
    assert data == {"usados": 0, "limite": 100, "aviso": 80, "restantes": 100, "nivel": "normal", "reenvio_horas": 8}
    assert client.get("/correos-enviados/cuota", headers=_admin(client)).status_code == 200
    proveedor = _sesion(client, "RFCPROTEST", accesos_repo.PERFIL_PROVEEDOR, "Campeche", "p@example.com")
    assert client.get("/correos-enviados/cuota", headers=proveedor).status_code == 403


# ---------- Freno de reenvío ----------

def test_no_se_puede_reenviar_antes_de_8_horas(client):
    _proveedor("PROVCAM001", "Campeche", "c1@example.com")
    headers = _cabina(client)
    assert _enviar(client, headers, [3001]).json()["correo_enviado"] is True

    r = _enviar(client, headers, [3001])  # ya está en Espera: sería un recordatorio

    assert r.status_code == 400
    assert "3001" in r.json()["detail"]
    assert "a partir de" in r.json()["detail"]


def test_si_un_expediente_esta_frenado_no_se_manda_ninguno(client, capturados):
    _proveedor("PROVCAM001", "Campeche", "c1@example.com")
    headers = _cabina(client)
    _enviar(client, headers, [3001])
    from app.repositories import estatus_repo
    from app.schemas.expediente import EstatusExpediente

    estatus_repo.actualizar_estatus(3005, EstatusExpediente.EN_ESPERA_RESPUESTA, "RFCCABTEST")

    r = _enviar(client, headers, [3001, 3005])

    assert r.status_code == 400
    assert len(capturados) == 1  # solo el primer envío


def test_pasadas_8_horas_ya_se_puede_reenviar(client):
    _proveedor("PROVCAM001", "Campeche", "c1@example.com")
    headers = _cabina(client)
    _enviar(client, headers, [3001])
    from app.db.local_store import get_local_connection

    hace_9_horas = (datetime.datetime.now() - datetime.timedelta(hours=9)).strftime("%Y-%m-%d %H:%M:%S")
    with get_local_connection() as conn:
        conn.execute("UPDATE correos_enviados SET fecha = ?", (hace_9_horas,))
        conn.commit()

    r = _enviar(client, headers, [3001])

    assert r.status_code == 200, r.text
    assert r.json()["correo_enviado"] is True


def test_si_no_salio_correo_el_freno_no_aplica(client):
    headers = _cabina(client)
    assert _enviar(client, headers, [3001]).json()["motivo_sin_correo"] == "sin_proveedores"
    _proveedor("PROVCAM001", "Campeche", "c1@example.com")

    r = _enviar(client, headers, [3001])

    assert r.status_code == 200, r.text
    assert r.json()["correo_enviado"] is True


# ---------- Corte ----------

def _corte(client, headers) -> int:
    r = client.post("/expedientes/corte", json={"expedientes": [3001]}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["corte_id"]


def test_corte_exige_una_direccion_valida(client):
    headers = _admin(client)
    corte_id = _corte(client, headers)

    assert client.post(f"/expedientes/corte/{corte_id}/enviar", json={}, headers=headers).status_code == 422
    r = client.post(f"/expedientes/corte/{corte_id}/enviar", json={"destinatario": "no-es-correo"}, headers=headers)
    assert r.status_code == 422
    r = client.post(
        f"/expedientes/corte/{corte_id}/enviar", json={"destinatario": "a@example.com, b@example.com"}, headers=headers
    )
    assert r.status_code == 422  # una sola dirección


def test_corte_cuenta_contra_el_tope_y_se_bloquea_al_llegar(client, monkeypatch):
    _configurar(monkeypatch, SMTP_LIMITE_DIARIO=1, SMTP_AVISO_LIMITE=1)
    headers = _admin(client)
    corte_id = _corte(client, headers)

    r = client.post(f"/expedientes/corte/{corte_id}/enviar", json={"destinatario": "cabina@example.com"}, headers=headers)
    assert r.status_code == 200, r.text
    assert _usados(client, headers) == 1

    r = client.post(f"/expedientes/corte/{corte_id}/enviar", json={"destinatario": "cabina@example.com"}, headers=headers)
    assert r.status_code == 409
    assert "límite" in r.json()["detail"]
    # El Excel se puede seguir descargando.
    assert client.get(f"/expedientes/corte/{corte_id}/descargar", headers=headers).status_code == 200


# ---------- GraphQL usa las mismas reglas ----------

def test_graphql_tambien_pide_confirmacion_cerca_del_tope(client, monkeypatch):
    _configurar(monkeypatch, SMTP_LIMITE_DIARIO=2, SMTP_AVISO_LIMITE=1)
    _proveedor("PROVCAM001", "Campeche", "c1@example.com")
    headers = _cabina(client)
    consulta = (
        "mutation { enviarCorreoProveedores(datos: {expedientes: [3001]%s}) "
        "{ enviados requiereConfirmacion correoEnviado } }"
    )

    r = client.post("/graphql", json={"query": consulta % ""}, headers=headers)
    assert r.json()["data"]["enviarCorreoProveedores"] == {
        "enviados": 0, "requiereConfirmacion": True, "correoEnviado": False
    }

    r = client.post("/graphql", json={"query": consulta % ", confirmarLimite: true"}, headers=headers)
    assert r.json()["data"]["enviarCorreoProveedores"]["correoEnviado"] is True
