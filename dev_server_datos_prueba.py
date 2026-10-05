"""
Servidor de DESARROLLO con datos de ejemplo (no toca SQL Server).

Sirve para probar visualmente el frontend (frontend/index.html) y el
flujo de login de punta a punta ANTES de tener la base de datos real
conectada — así puedes confirmar que la parte visual funciona bien,
por separado de si la conexión a SQL Server funciona bien.

Uso:
    python dev_server_datos_prueba.py

Luego abre frontend/index.html en tu navegador e inicia sesión con:
    usuario:    ijimenez
    contraseña: clave123

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
    if sp_name == "dbo.ObtenerExpedientesSinProveedorMedico":
        return EXPEDIENTES_DEMO
    if sp_name == "dbo.ObtenerCatalogoServicio":
        return [{"clServicio": 4, "dsServicio": "Servicio Médico"}]
    if sp_name == "dbo.ObtenerServicioMedico":
        return [
            {"clSubServicio": 377, "dsSubServicio": "Consulta Externa"},
            {"clSubServicio": 420, "dsSubServicio": "Hospitalización"},
        ]
    if sp_name == "dbo.ObtenerCatalogoCuentas":
        return [{"clCuenta": 2819, "Nombre": "Cuenta Demo"}]
    if sp_name == "dbo.sp_S2_BuscaCuenta":
        return [{"clCuenta": 2819, "Nombre": "Cuenta Demo"}]
    if sp_name == "dbo.ObtenerExpedientesSinRespuestaProveedor":
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
    if sp_name == "dbo.RegistrarSeguimiento":
        return [{"clSeguimiento": 1, "FechaRegistro": datetime.datetime.now()}]
    raise AssertionError(f"SP inesperado: {sp_name}")


expedientes_repo_module.call_procedure = fake_call_procedure
catalogos_repo_module.call_procedure = fake_call_procedure
auth_repo_module.call_procedure = fake_call_procedure
seguimiento_repo_module.call_procedure_write = fake_call_procedure_write

from app.main import app  # noqa: E402

if __name__ == "__main__":
    print("Servidor de DATOS DE PRUEBA (sin SQL Server) en http://127.0.0.1:8000")
    print("Usuario: ijimenez / Contraseña: clave123")
    print("Abre frontend/index.html en tu navegador para probarlo.")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
