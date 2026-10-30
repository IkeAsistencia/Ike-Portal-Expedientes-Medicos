import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import logging

from app.config import get_arranque_settings, get_settings, validar_jwt_secret
from app.core.secretos_aws import cargar_en_entorno
from app.db.connection import calentar_pool
from app.db.local_store import init_local_db
from app.graphql.schema import graphql_router
from app.repositories import accesos_repo
from app.services.carga_usuarios_service import ErrorCargaUsuarios, sembrar_desde_excel

logger = logging.getLogger(__name__)
from app.routers import (
    admin_accesos,
    auth,
    catalogos,
    configuracion_cuentas,
    correos_enviados,
    cuentas_etiquetas,
    directorio_proveedores,
    expedientes,
    proveedores_catalogo,
    seguimiento,
    solicitudes_alta_medico,
)


def _cargar_secretos_de_aws() -> None:
    """
    Deja en el entorno las llaves que viven en AWS Secrets Manager (ver
    app/core/secretos_aws.py). Con SECRETOS_AWS_MODO=off no hace nada, así
    que en desarrollo y pruebas no se toca la red ni hace falta boto3.

    Con "obligatorio", si el secreto no se puede leer, ErrorSecretosAws
    sube y uvicorn aborta el arranque. Es a propósito: el servicio no debe
    quedar arriba con secretos a medias.
    """
    arranque = get_arranque_settings()
    cargar_en_entorno(
        modo=arranque.secretos_aws_modo,
        nombre=arranque.secretos_aws_nombre,
        region=arranque.secretos_aws_region,
        clave_texto_plano=arranque.secretos_aws_clave or None,
    )
    # Los secretos recién aplicados tienen que verse en get_settings(): sin
    # limpiar el cache, una instancia ya construida (por ejemplo al importar
    # app.graphql.schema) seguiría con los valores del .env.
    get_settings.cache_clear()


def _sembrar_usuarios_iniciales() -> None:
    """
    Da de alta en automático el Excel de SEED_USUARIOS_RUTA (ver
    app/services/carga_usuarios_service.py), SOLO si la tabla de accesos
    está vacía -- así es el primer despliegue el que los crea, sin que nadie
    tenga que correr el script a mano, y los arranques siguientes no la
    vuelven a tocar aunque la variable se quede puesta.

    No es "obligatorio" como los secretos de AWS: si el archivo no está o
    viene mal, se registra el error y el servicio sigue arrancando -- esto
    es una comodidad para no dar de alta a mano, no una dependencia dura.
    """
    settings = get_settings()
    if not settings.seed_usuarios_ruta:
        return
    if accesos_repo.listar_accesos():
        return  # ya hay accesos: no es el primer arranque, no se vuelve a sembrar
    try:
        resultado = sembrar_desde_excel(settings.seed_usuarios_ruta, aplicar=True)
    except ErrorCargaUsuarios as err:
        logger.error("Siembra inicial de usuarios: %s", err)
        return
    logger.info(
        "Siembra inicial de usuarios: %d alta(s), %d rechazada(s) de %s",
        len(resultado["listas"]), len(resultado["rechazadas"]), settings.seed_usuarios_ruta,
    )
    for fila, motivo in resultado["rechazadas"]:
        logger.warning("Siembra inicial de usuarios: RFC %s rechazado (%s)", fila["rfc"], motivo)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # PRIMERO los secretos de AWS (si están encendidos): dejan las llaves en
    # el entorno y de ahí las toma get_settings(), que está cacheado. Tiene
    # que ser antes de la primera llamada a get_settings() -- si no, la
    # configuración quedaría armada con el .env y el secreto ya no aplicaría.
    _cargar_secretos_de_aws()
    # Falla rápido y claro si nadie configuró un JWT_SECRET_KEY real -- mejor
    # que arrancar "funcionando" con un secreto público conocido.
    validar_jwt_secret(get_settings())
    init_local_db()
    _sembrar_usuarios_iniciales()
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


@app.exception_handler(RequestValidationError)
async def manejar_error_de_validacion(_: Request, exc: RequestValidationError) -> JSONResponse:
    """
    422 sin devolver el dato que llegó.

    Pydantic mete en cada error la clave "input" con el valor recibido y
    FastAPI lo regresa tal cual en la respuesta. Eso significaba que una
    contraseña que no cumplía la regla (POST /auth/rfc/crear-password)
    terminaba reflejada en el body del 422 -- y de ahí a los logs del
    proxy, al historial del navegador o a cualquier intermediario
    (CWE-359, exposición de datos sensibles).

    Se responde solo con qué campo falló y por qué, que es lo único que el
    frontend usa (ver `detail[].msg` en frontend/js/core/api.js).
    """
    errores = [
        {"type": e.get("type"), "loc": list(e.get("loc", ())), "msg": e.get("msg")}
        for e in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": errores})


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
app.include_router(proveedores_catalogo.router)
app.include_router(directorio_proveedores.router)
app.include_router(solicitudes_alta_medico.router)
app.include_router(cuentas_etiquetas.router)
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
