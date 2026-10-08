"""
Servidor de DESARROLLO con datos de ejemplo (no toca SQL Server).

Sirve para probar visualmente el portal (frontend/) y el
flujo de login de punta a punta ANTES de tener la base de datos real
conectada — así puedes confirmar que la parte visual funciona bien,
por separado de si la conexión a SQL Server funciona bien.

Uso:
    python dev_server_datos_prueba.py

Luego abre http://127.0.0.1:8000 en tu navegador e inicia sesión con
cualquiera de estos RFC de prueba (se dan de alta solos al arrancar; la
primera vez el portal te pide crear una contraseña):
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
        "TipoServicio": "Servicio Médico",
        "TipoSubservicio": "Consulta Externa",
        "NombreTitular": "Juan Pérez López",
        "NombrePaciente": "Paciente de Prueba",
        "Especialidad": "Medicina General",
        "Entidad": "Campeche",
        "Municipio": "Campeche",
        "FechaAperturaServicio": datetime.date(2026, 8, 1),
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

from app.main import app  # noqa: E402

if __name__ == "__main__":
    from scripts.seed_usuarios_prueba import USUARIOS_PRUEBA, ejecutar as seed_usuarios_prueba

    seed_usuarios_prueba()
    print("Servidor de DATOS DE PRUEBA (sin SQL Server) en http://127.0.0.1:8000")
    print("RFC de prueba: " + ", ".join(f"{rfc} ({nombre})" for rfc, nombre, *_ in USUARIOS_PRUEBA))
    print("Abre http://127.0.0.1:8000 en tu navegador para probarlo.")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
