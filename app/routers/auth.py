import logging
import socket
from typing import Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings
from app.core.log_seguro import sanear_para_log
from app.core.rate_limit import verificar_limite
from app.core.red import ip_cliente
from app.core.security import crear_token, renovar_token

_bearer_renovar = HTTPBearer(auto_error=False)
from app.repositories import accesos_repo, auth_repo
from app.schemas.acceso import (
    AccesoLoginResponse,
    ActivacionEstadoResponse,
    ActivarPortalInput,
    CrearPasswordInput,
    PerfilDisponible,
    PerfilesDisponiblesResponse,
    RfcEstadoInput,
    RfcEstadoResponse,
    RfcLoginInput,
)
from app.schemas.auth import LoginInput, LoginResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Autenticación"])

# Sin esto, cualquiera puede probar contraseñas sin límite (fuerza bruta /
# credential stuffing) o, en /rfc/estado, enumerar qué RFC existen en el
# sistema. La clave combina IP + identificador para no bloquear a todo
# mundo detrás del mismo NAT por los fallos de una sola cuenta.
MAXIMO_INTENTOS_LOGIN = 10
VENTANA_INTENTOS_LOGIN_SEGUNDOS = 5 * 60


@router.post("/login", response_model=LoginResponse)
def login(data: LoginInput, request: Request):
    # Login legado por usuario/contraseña de SISE: apagado por default
    # (LOGIN_LEGADO_HABILITADO, ver app/config.py). Se responde 404 para no
    # anunciar que la ruta existe.
    if not get_settings().login_legado_habilitado:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")
    host = _obtener_host_servidor()
    ip = ip_cliente(request)
    verificar_limite(f"login:{ip}:{data.usuario}", MAXIMO_INTENTOS_LOGIN, VENTANA_INTENTOS_LOGIN_SEGUNDOS)

    try:
        resultado = auth_repo.autenticar(data.usuario, data.password.get_secret_value(), host, ip[:20])
    except auth_repo.UsuarioInactivo as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))
    except auth_repo.CredencialesInvalidas as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e))

    token = crear_token(resultado["cl_usr_app"], resultado["usuario"], resultado["nombre"])
    return LoginResponse(
        access_token=token,
        cl_usr_app=resultado["cl_usr_app"],
        usuario=resultado["usuario"],
        nombre=resultado["nombre"],
    )


@router.get("/activacion/estado", response_model=ActivacionEstadoResponse)
def activacion_estado(request: Request):
    """
    ¿El portal está sin activar (sin ningún acceso)? El login lo consulta al
    abrirse: si es así, en vez del RFC pide crear al primer Administrador.
    """
    verificar_limite(f"activacion-estado:{ip_cliente(request)}", 60, VENTANA_INTENTOS_LOGIN_SEGUNDOS)
    return ActivacionEstadoResponse(requerida=accesos_repo.portal_sin_accesos())


@router.post("/activacion", response_model=AccesoLoginResponse)
def activar_portal(data: ActivarPortalInput, request: Request):
    """
    Activación inicial: con la tabla de accesos vacía, el primer RFC que llega
    queda como Administrador y entra. En cuanto existe un acceso, esta ruta
    responde 404 como si no existiera.
    """
    ip = ip_cliente(request)
    verificar_limite(f"activacion:{ip}", MAXIMO_INTENTOS_LOGIN, VENTANA_INTENTOS_LOGIN_SEGUNDOS)

    acceso = accesos_repo.activar_portal(data.rfc, data.nombre, data.password.get_secret_value())
    if acceso is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")

    logger.warning(
        "Activación inicial del portal: primer Administrador creado (RFC %s) desde %s",
        sanear_para_log(acceso["rfc"]), sanear_para_log(ip),
    )
    token = crear_token(nombre=acceso["nombre"], rfc=acceso["rfc"], perfil=acceso["perfil"])
    return AccesoLoginResponse(
        access_token=token, rfc=acceso["rfc"], nombre=acceso["nombre"], perfil=acceso["perfil"]
    )


@router.post("/rfc/estado", response_model=RfcEstadoResponse)
def rfc_estado(data: RfcEstadoInput, request: Request):
    """
    Paso 1 del login por RFC: el frontend pregunta si el RFC está
    autorizado y si ya tiene contraseña creada, para saber qué pantalla
    mostrar (crear contraseña vs. capturarla).
    """
    ip = ip_cliente(request)
    verificar_limite(f"rfc-estado:{ip}", MAXIMO_INTENTOS_LOGIN, VENTANA_INTENTOS_LOGIN_SEGUNDOS)

    acceso = accesos_repo.buscar_acceso(data.rfc)
    if not acceso or not acceso["activo"]:
        return RfcEstadoResponse(autorizado=False, tiene_password=False)
    return RfcEstadoResponse(
        autorizado=True,
        tiene_password=bool(acceso["password_hash"]),
        nombre=acceso["nombre"],
    )


def _respuesta_de_sesion(acceso: dict, perfil_elegido: Optional[int]) -> Union[AccesoLoginResponse, PerfilesDisponiblesResponse]:
    """
    Cierra el login de un RFC ya autenticado. Con un solo perfil entra directo;
    con varios, si todavía no eligió responde la lista para que el login pregunte
    "Entrar como", y con `perfil_elegido` emite la sesión con ESE perfil (el
    token lleva uno solo, así que los permisos no cambian).
    """
    perfiles = acceso.get("perfiles") or [acceso["perfil"]]
    if perfil_elegido is not None:
        if perfil_elegido not in perfiles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Ese perfil no está asignado a este RFC.")
        perfil = perfil_elegido
    elif len(perfiles) == 1:
        perfil = perfiles[0]
    else:
        return PerfilesDisponiblesResponse(
            perfiles=[PerfilDisponible(perfil=p, nombre=accesos_repo.NOMBRES_PERFIL[p]) for p in perfiles]
        )
    token = crear_token(nombre=acceso["nombre"], rfc=acceso["rfc"], perfil=perfil)
    return AccesoLoginResponse(access_token=token, rfc=acceso["rfc"], nombre=acceso["nombre"], perfil=perfil)


@router.post("/rfc/crear-password", response_model=Union[AccesoLoginResponse, PerfilesDisponiblesResponse])
def rfc_crear_password(data: CrearPasswordInput, request: Request):
    """Primera vez que un RFC autorizado usa el sistema: crea su contraseña y entra."""
    ip = ip_cliente(request)
    verificar_limite(f"rfc-crear:{ip}:{data.rfc}", MAXIMO_INTENTOS_LOGIN, VENTANA_INTENTOS_LOGIN_SEGUNDOS)

    try:
        acceso = accesos_repo.crear_password(data.rfc, data.password.get_secret_value())
    except accesos_repo.RfcNoAutorizado as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))
    except accesos_repo.CredencialesInvalidas as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))

    return _respuesta_de_sesion(acceso, None)


@router.post("/rfc/login", response_model=Union[AccesoLoginResponse, PerfilesDisponiblesResponse])
def rfc_login(data: RfcLoginInput, request: Request):
    """Login normal por RFC + contraseña (ya creada previamente)."""
    ip = ip_cliente(request)
    verificar_limite(f"rfc-login:{ip}:{data.rfc}", MAXIMO_INTENTOS_LOGIN, VENTANA_INTENTOS_LOGIN_SEGUNDOS)

    try:
        acceso = accesos_repo.autenticar(data.rfc, data.password.get_secret_value())
    except accesos_repo.CredencialesInvalidas as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e))

    return _respuesta_de_sesion(acceso, data.perfil)


@router.post("/renovar")
def renovar(credenciales: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_renovar)):
    """
    El portal lo llama mientras la persona trabaja (como mucho una vez por
    minuto): regresa un token con la ventana de inactividad otra vez completa.
    Sin actividad nadie lo llama y la sesión vence sola (ver
    app/core/security.py). No extiende la duración máxima de la sesión.
    """
    if credenciales is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Debes iniciar sesión.")
    settings = get_settings()
    return {
        "access_token": renovar_token(credenciales.credentials),
        "inactividad_minutos": settings.sesion_inactividad_minutos,
    }


def _obtener_host_servidor() -> str:
    """
    Un API web no puede obtener el hostname real del equipo del usuario
    final, solo el del servidor donde corre la app. Si necesitas el
    hostname real del cliente, hay que capturarlo en el navegador (JS)
    y mandarlo en el body del login.
    """
    return socket.gethostname()[:20]

