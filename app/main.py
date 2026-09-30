from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.local_store import init_local_db
from app.graphql.schema import graphql_router
from app.routers import admin_accesos, auth, catalogos, configuracion_cuentas, expedientes, seguimiento


@asynccontextmanager
async def lifespan(_: FastAPI):
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

# CORS: habilitado permisivo para poder probar el frontend (frontend/index.html,
# abierto como archivo local o servido en otro puerto) contra esta API en
# desarrollo. ANTES de pasar a un ambiente real, restringe allow_origins a la
# URL exacta donde viva el frontend definitivo.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
