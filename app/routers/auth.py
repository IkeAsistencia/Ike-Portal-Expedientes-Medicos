import socket

from fastapi import APIRouter, HTTPException, Request, status

from app.core.rate_limit import verificar_limite
from app.core.security import crear_token
from app.repositories import accesos_repo, auth_repo
from app.schemas.acceso import (
    AccesoLoginResponse,
    CrearPasswordInput,
    RfcEstadoInput,
    RfcEstadoResponse,
    RfcLoginInput,
)
from app.schemas.auth import LoginInput, LoginResponse

router = APIRouter(prefix="/auth", tags=["Autenticación"])

# Sin esto, cualquiera puede probar contraseñas sin límite (fuerza bruta /
# credential stuffing) o, en /rfc/estado, enumerar qué RFC existen en el
# sistema. La clave combina IP + identificador para no bloquear a todo
# mundo detrás del mismo NAT por los fallos de una sola cuenta.
MAXIMO_INTENTOS_LOGIN = 10
VENTANA_INTENTOS_LOGIN_SEGUNDOS = 5 * 60


@router.post("/login", response_model=LoginResponse)
def login(data: LoginInput, request: Request):
    host = _obtener_host_servidor()
    ip = _obtener_ip_cliente(request)
    verificar_limite(f"login:{ip}:{data.usuario}", MAXIMO_INTENTOS_LOGIN, VENTANA_INTENTOS_LOGIN_SEGUNDOS)

    try:
        resultado = auth_repo.autenticar(data.usuario, data.password, host, ip)
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


@router.post("/rfc/estado", response_model=RfcEstadoResponse)
def rfc_estado(data: RfcEstadoInput, request: Request):
    """
    Paso 1 del login por RFC: el frontend pregunta si el RFC está
    autorizado y si ya tiene contraseña creada, para saber qué pantalla
    mostrar (crear contraseña vs. capturarla).
    """
    ip = _obtener_ip_cliente(request)
    verificar_limite(f"rfc-estado:{ip}", MAXIMO_INTENTOS_LOGIN, VENTANA_INTENTOS_LOGIN_SEGUNDOS)

    acceso = accesos_repo.buscar_acceso(data.rfc)
    if not acceso or not acceso["activo"]:
        return RfcEstadoResponse(autorizado=False, tiene_password=False)
    return RfcEstadoResponse(
        autorizado=True,
        tiene_password=bool(acceso["password_hash"]),
        nombre=acceso["nombre"],
    )


@router.post("/rfc/crear-password", response_model=AccesoLoginResponse)
def rfc_crear_password(data: CrearPasswordInput, request: Request):
    """Primera vez que un RFC autorizado usa el sistema: crea su contraseña y entra."""
    ip = _obtener_ip_cliente(request)
    verificar_limite(f"rfc-crear:{ip}:{data.rfc}", MAXIMO_INTENTOS_LOGIN, VENTANA_INTENTOS_LOGIN_SEGUNDOS)

    try:
        acceso = accesos_repo.crear_password(data.rfc, data.password)
    except accesos_repo.RfcNoAutorizado as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))
    except accesos_repo.CredencialesInvalidas as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))

    token = crear_token(nombre=acceso["nombre"], rfc=acceso["rfc"], perfil=acceso["perfil"])
    return AccesoLoginResponse(
        access_token=token, rfc=acceso["rfc"], nombre=acceso["nombre"], perfil=acceso["perfil"]
    )


@router.post("/rfc/login", response_model=AccesoLoginResponse)
def rfc_login(data: RfcLoginInput, request: Request):
    """Login normal por RFC + contraseña (ya creada previamente)."""
    ip = _obtener_ip_cliente(request)
    verificar_limite(f"rfc-login:{ip}:{data.rfc}", MAXIMO_INTENTOS_LOGIN, VENTANA_INTENTOS_LOGIN_SEGUNDOS)

    try:
        acceso = accesos_repo.autenticar(data.rfc, data.password)
    except accesos_repo.CredencialesInvalidas as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e))

    token = crear_token(nombre=acceso["nombre"], rfc=acceso["rfc"], perfil=acceso["perfil"])
    return AccesoLoginResponse(
        access_token=token, rfc=acceso["rfc"], nombre=acceso["nombre"], perfil=acceso["perfil"]
    )


def _obtener_host_servidor() -> str:
    """
    Ver sql/05_..._NOTAS.md: un API web no puede obtener el hostname
    real del equipo del usuario final, solo el del servidor donde
    corre la app. Si necesitas el hostname real del cliente, hay que
    capturarlo en el navegador (JS) y mandarlo en el body del login.
    """
    return socket.gethostname()[:20]


def _obtener_ip_cliente(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:20]
    return (request.client.host if request.client else "")[:20]
