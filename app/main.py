from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_arranque_settings, get_settings, validar_jwt_secret
from app.db.local_store import init_local_db
from app.graphql.schema import graphql_router
from app.routers import admin_accesos, auth, catalogos, configuracion_cuentas, expedientes, seguimiento


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Falla rápido y claro si nadie configuró un JWT_SECRET_KEY real -- mejor
    # que arrancar "funcionando" con un secreto público conocido.
    validar_jwt_secret(get_settings())
    init_local_db()
    yield


app = FastAPI(
    title="API Expedientes Médicos",
    version="1.0.0",
    description=(
        "Backend para el sistema de gestión de Expedientes Médicos, expuesto "
        "tanto por REST como por GraphQL (/graphql). Lectura/escritura contra "
        "SQL Server vía Stored Procedures; el estatus de negocio y la "
        "configuración de cuentas se manejan en una base local propia de esta app."
    ),
    lifespan=lifespan,
)

# CORS: por default abierto ("*", ver CORS_ALLOWED_ORIGINS en .env) para poder
# probar el frontend (frontend/index.html, abierto como archivo local o
# servido en otro puerto) contra esta API en desarrollo. ANTES de pasar a un
# ambiente real, pon la URL exacta donde viva el frontend definitivo.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_arranque_settings().cors_allowed_origins_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def agregar_headers_seguridad(request, call_next):
    """X-Content-Type-Options: nosniff en toda respuesta -- evita que el
    navegador intente "adivinar" el tipo real de un archivo (ej. un
    comprobante de pago subido con un Content-Type que no corresponde a su
    contenido) en vez de respetar el que manda el servidor."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


app.include_router(auth.router)
app.include_router(expedientes.router)
app.include_router(catalogos.router)
app.include_router(seguimiento.router)
app.include_router(configuracion_cuentas.router)
app.include_router(admin_accesos.router)
app.include_router(graphql_router, prefix="/graphql", tags=["GraphQL"])


@app.get("/health", tags=["Salud"])
def health():
    return {"status": "ok"}
