import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_arranque_settings, get_settings, validar_jwt_secret
from app.db.connection import calentar_pool
from app.db.local_store import init_local_db
from app.graphql.schema import graphql_router
from app.routers import (
    admin_accesos,
    auth,
    catalogos,
    configuracion_cuentas,
    correos_enviados,
    expedientes,
    seguimiento,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Falla rápido y claro si nadie configuró un JWT_SECRET_KEY real -- mejor
    # que arrancar "funcionando" con un secreto público conocido.
    validar_jwt_secret(get_settings())
    init_local_db()
    # La primera conexión a SQL Server siempre es "fría" (~0.6-0.9s, ver
    # app/db/connection.py); mejor que la pague el arranque del proceso y
    # no el primer usuario real que entre.
    calentar_pool()
    yield


app = FastAPI(
    title="Portal Promédico",
    version="1.0.0",
    description=(
        "Backend del Portal Promédico (gestión de Expedientes Médicos), expuesto "
        "tanto por REST como por GraphQL (/graphql). Lectura/escritura contra "
        "SQL Server vía Stored Procedures; el estatus de negocio y la "
        "configuración de cuentas se manejan en una base local propia de esta app."
    ),
    lifespan=lifespan,
)

# CORS: el portal ya lo sirve esta misma app (ver el final de este archivo),
# así que no lo necesita. Se deja por si algún cliente externo consume la API
# desde otro origen; por default abierto ("*", ver CORS_ALLOWED_ORIGINS en
# .env) -- ANTES de pasar a un ambiente real, restríngelo.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_arranque_settings().cors_allowed_origins_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


_RUTAS_FRONTEND_SIN_CACHE = ("/js/", "/css/", "/img/")


@app.middleware("http")
async def agregar_headers_seguridad(request, call_next):
    """X-Content-Type-Options: nosniff en toda respuesta -- evita que el
    navegador intente "adivinar" el tipo real de un archivo (ej. un
    comprobante de pago subido con un Content-Type que no corresponde a su
    contenido) en vez de respetar el que manda el servidor."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    # El portal (frontend/) cambia seguido durante el desarrollo -- sin un
    # Cache-Control explícito, el navegador a veces se queda con una copia
    # vieja del JS/CSS/HTML y los cambios "no se ven" aunque el servidor ya
    # los tenga. no-cache obliga a revalidar siempre (barato: StaticFiles ya
    # manda ETag/Last-Modified, así que si no cambió responde 304 sin volver
    # a mandar el archivo completo).
    path = request.url.path
    if path == "/" or path == "/index.html" or path.startswith(_RUTAS_FRONTEND_SIN_CACHE):
        response.headers["Cache-Control"] = "no-cache"
    return response


app.include_router(auth.router)
app.include_router(expedientes.router)
app.include_router(catalogos.router)
app.include_router(seguimiento.router)
app.include_router(configuracion_cuentas.router)
app.include_router(admin_accesos.router)
app.include_router(correos_enviados.router)
app.include_router(graphql_router, prefix="/graphql", tags=["GraphQL"])


@app.get("/health", tags=["Salud"])
def health():
    return {"status": "ok"}


# Frontend del portal (frontend/index.html + css/ + js/), servido en "/".
# Va al FINAL a propósito: un mount en "/" atrapa cualquier ruta, así que
# todos los endpoints de arriba deben estar registrados antes.
# En Windows, el registro a veces asocia .js a "text/plain" y el navegador se
# niega a cargarlo como módulo (sobre todo con X-Content-Type-Options:
# nosniff), por eso se fijan los tipos explícitamente.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
