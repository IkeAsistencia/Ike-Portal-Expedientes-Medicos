"""
Servidor de DESARROLLO con datos de ejemplo (no toca SQL Server).

Sirve para probar visualmente el portal (frontend/) y el
flujo de login de punta a punta ANTES de tener la base de datos real
conectada — así puedes confirmar que la parte visual funciona bien,
por separado de si la conexión a SQL Server funciona bien.

Uso:
    python dev_server_datos_prueba.py

Luego abre http://127.0.0.1:8000 en tu navegador e inicia sesión con
cualquiera de estos RFC de prueba (se dan de alta solos al arrancar, todos
con la contraseña de prueba Qwer1234$):
    ADMI000001 -> Administrador
    CABI000001 -> Cabina
    PROV000001 -> Proveedor (entidad Campeche)

NO usar en producción ni contra la base real — todos los datos que
regresa este servidor son inventados en este mismo archivo.
"""

import datetime
import os

# Valores dummy: este servidor nunca llama realmente a SQL Server (las
# funciones call_procedure/call_procedure_write quedan sustituidas más
# abajo), así que no hace falta un .env real para correr esta prueba.
os.environ.setdefault("DB_AUTH_MODE", "sql")
os.environ.setdefault("DB_SERVER", "no-se-usa")
os.environ.setdefault("DB_NAME", "no-se-usa")
os.environ.setdefault("DB_USER", "no-se-usa")
os.environ.setdefault("DB_PASSWORD", "no-se-usa")
os.environ.setdefault("JWT_SECRET_KEY", "clave-de-desarrollo-no-usar-en-produccion")
os.environ.setdefault("LOCAL_DB_PATH", "./data/app_local.db")

import uvicorn

import app.repositories.auth_repo as auth_repo_module
import app.repositories.catalogos_repo as catalogos_repo_module
import app.repositories.expedientes_repo as expedientes_repo_module
import app.repositories.seguimiento_repo as seguimiento_repo_module

EXPEDIENTES_DEMO = [
    {
        "Expediente": 1001,
        "Cuenta": "Cuenta Demo",
        "ClCuenta": 2819,
        "TipoServicio": "Servicio Médico",
        "TipoSubservicio": "Consulta Externa",
        # ClSubServicio y FechaAperturaCompleta los usa el semáforo de tiempos
        # (ver expedientes_repo.listar_expedientes y semaforo_service); sin
        # ellos el listado de Expedientes truena con KeyError.
        "ClSubServicio": 377,
        "NombreTitular": "Juan Pérez López",
        "NombrePaciente": "Paciente de Prueba",
        "Especialidad": "Medicina General",
        "Entidad": "Campeche",
        "Municipio": "Campeche",
        "FechaAperturaServicio": datetime.date(2026, 8, 1),
        "FechaAperturaCompleta": datetime.datetime(2026, 8, 1, 9, 30),
        "FechaAsignacionProveedor": datetime.date(2026, 8, 1),
        "FechaCita": datetime.date(2026, 8, 3),
        "Telefono": "9811234567",
        "Email": "paciente.demo@example.com",
    },
    {
        "Expediente": 1002,
        "Cuenta": "Cuenta Demo",
        "ClCuenta": 2819,
        "TipoServicio": "Servicio Médico",
        "TipoSubservicio": "Hospitalización",
        "ClSubServicio": 420,
        "NombreTitular": "María García Ruiz",
        "NombrePaciente": "Paciente Dos",
        "Especialidad": "Pediatría",
        "Entidad": "Yucatán",
        "Municipio": "Mérida",
        "FechaAperturaServicio": datetime.date(2026, 8, 2),
        "FechaAperturaCompleta": datetime.datetime(2026, 8, 2, 11, 15),
        "FechaAsignacionProveedor": None,
        "FechaCita": None,
        "Telefono": "9997654321",
        "Email": "paciente2.demo@example.com",
    },
]


def fake_call_procedure(sp_name, params=None):
    if sp_name == "dbo.ST_CP_ObtenerExpedientesSinProveedorMedico":
        # Igual que el SP real: si se pide un expediente puntual, regresa solo
        # ése (sin esto, el backend tomaba siempre el primero de la lista, ej.
        # "Enviar correo" sobre el 1002 terminaba marcando el 1001).
        cl_expediente = (params or {}).get("clExpediente")
        if cl_expediente is not None:
            return [e for e in EXPEDIENTES_DEMO if e["Expediente"] == int(cl_expediente)]
        return EXPEDIENTES_DEMO
    if sp_name == "dbo.ST_CP_ObtenerCatalogoServicio":
        return [{"clServicio": 4, "dsServicio": "Servicio Médico"}]
    if sp_name == "dbo.ST_CP_ObtenerServicioMedico":
        return [
            {"clSubServicio": 377, "dsSubServicio": "Consulta Externa"},
            {"clSubServicio": 420, "dsSubServicio": "Hospitalización"},
        ]
    if sp_name == "dbo.ST_CP_ObtenerCatalogoCuentas":
        return [{"clCuenta": 2819, "Nombre": "Cuenta Demo"}]
    if sp_name == "dbo.sp_S2_BuscaCuenta":
        return [{"clCuenta": 2819, "Nombre": "Cuenta Demo"}]
    if sp_name == "dbo.ST_CP_ObtenerExpedientesSinRespuestaProveedor":
        return [
            {
                "Expediente": 1003,
                "Cuenta": "Cuenta Demo",
                "NombrePaciente": "Paciente Sin Respuesta",
                "FechaApertura": datetime.date(2026, 8, 1),
                "FechaAsignacionProveedor": datetime.date(2026, 8, 1),
                "HorasSinRespuesta": 30,
            }
        ]
    if sp_name == "dbo.sp_GetMun":
        # Municipios de la entidad pedida -- solo se simulan unos cuantos por
        # entidad (los suficientes para probar "Buscar fuera de la red" y el
        # Alta de médico sin SQL Server).
        municipios = {
            "JC": [
                {"CodMD": "00039", "dsMunDel": "Guadalajara", "CodEnt": "JC"},
                {"CodMD": "00120", "dsMunDel": "Zapopan", "CodEnt": "JC"},
            ],
            "DF": [
                {"CodMD": "00015", "dsMunDel": "Ciudad de México", "CodEnt": "DF"},
            ],
            "CM": [
                {"CodMD": "00002", "dsMunDel": "Campeche", "CodEnt": "CM"},
            ],
        }
        return municipios.get((params or {}).get("CodEnt"), [])
    if sp_name == "dbo.sp_EncriptDesEncriptPassword":
        if params.get("pUsuario") == "ijimenez" and params.get("pContraseña") == "clave123":
            return [{"clUsrApp": 42, "Nombre": "Ignacio Jiménez", "Activo": True}]
        return []
    raise AssertionError(f"SP inesperado: {sp_name}")


def fake_call_procedure_write(sp_name, params=None):
    if sp_name == "dbo.ST_CP_RegistrarSeguimiento":
        return [{"clSeguimiento": 1, "FechaRegistro": datetime.datetime.now()}]
    raise AssertionError(f"SP inesperado: {sp_name}")


expedientes_repo_module.call_procedure = fake_call_procedure
catalogos_repo_module.call_procedure = fake_call_procedure
auth_repo_module.call_procedure = fake_call_procedure
seguimiento_repo_module.call_procedure_write = fake_call_procedure_write

# listar_entidades() NO usa un SP: lee dbo.cEntFed con SQL directo (ver
# catalogos_repo.py), así que no pasa por fake_call_procedure. Sin esto, el
# combo de Estado del Alta de médico y de "Buscar fuera de la red" quedaba
# vacío en el servidor de prueba.
def _entidades_demo():
    return [
        catalogos_repo_module.EntidadFederativa(clave="JC", descripcion="JALISCO", clave_inegi="14"),
        catalogos_repo_module.EntidadFederativa(clave="DF", descripcion="CIUDAD DE MEXICO", clave_inegi="09"),
        catalogos_repo_module.EntidadFederativa(clave="CM", descripcion="CAMPECHE", clave_inegi="04"),
    ]


catalogos_repo_module.listar_entidades = _entidades_demo


def _sembrar_estatus_demo():
    """Los expedientes de demo necesitan estatus en la base local (SQLite):
    el perfil Proveedor solo ve los que están en "En Espera de Respuesta" o
    "Seguimiento de Cita" (ver ESTATUS_ACCIONABLES_PROVEEDOR en
    frontend/js/core/reglas-expedientes.js). Sin esto, la tabla de
    Expedientes sale vacía aunque el SP devuelva filas."""
    from app.repositories import estatus_repo
    from app.schemas.expediente import EstatusExpediente

    estatus_repo.actualizar_estatus(1001, EstatusExpediente.EN_ESPERA_RESPUESTA, "ADMI000001")
    estatus_repo.actualizar_estatus(1002, EstatusExpediente.SEGUIMIENTO_CITA, "ADMI000001")


def preparar_datos_prueba(password: str = "Qwer1234$") -> None:
    """
    Deja el servidor de prueba listo para usarse: crea las tablas de la base
    local, da de alta los tres usuarios y siembra los estatus de los
    expedientes de demo.

    Es idempotente y se llama al arrancar. Antes habia que acordarse de
    correr init_local_db() a mano si se borraba data/app_local.db, y si se
    olvidaba el portal tronaba con "no such table: usuarios_acceso" (login)
    o "no such table: cuentas_etiqueta" (Expedientes).
    """
    from app.db.local_store import init_local_db
    from scripts.seed_usuarios_prueba import ejecutar as seed_usuarios_prueba

    init_local_db()
    seed_usuarios_prueba(password)
    _sembrar_estatus_demo()


from app.main import app  # noqa: E402

if __name__ == "__main__":
    from scripts.seed_usuarios_prueba import USUARIOS_PRUEBA

    # Contraseña común de prueba (este servidor solo sirve datos inventados).
    preparar_datos_prueba()
    print("Servidor de DATOS DE PRUEBA (sin SQL Server) en http://127.0.0.1:8000")
    print("RFC de prueba: " + ", ".join(f"{rfc} ({nombre})" for rfc, nombre, *_ in USUARIOS_PRUEBA))
    print("Contraseña de prueba para los tres: Qwer1234$")
    print("Abre http://127.0.0.1:8000 en tu navegador para probarlo.")
    # HOST configurable: dentro de Docker hay que escuchar en 0.0.0.0 para
    # que el puerto publicado (-p 8000:8000) llegue al contenedor; en la
    # máquina local 127.0.0.1 es lo correcto (no expone el puerto a la red).
    uvicorn.run(app, host=os.environ.get("HOST", "127.0.0.1"), port=8000, log_level="info")
