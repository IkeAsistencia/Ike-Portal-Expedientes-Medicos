"""
Sesión de la aplicación: tras un login exitoso contra el SP legado, esta
app emite su PROPIO token (JWT) para no depender de @CreateSession del SP
(que se manda fijo en 0, según lo indicado). Los endpoints protegidos
exigen 'Authorization: Bearer <token>'.

Vencimiento (2026-10-26):
  - Por INACTIVIDAD: el token dura poco (SESION_INACTIVIDAD_MINUTOS más un
    margen) y el portal lo renueva mientras la persona trabaja (POST
    /auth/renovar, ver frontend/js/core/inactividad.js). Si nadie lo
    renueva, vence solo: el cierre por inactividad lo impone el servidor, no
    solo la pantalla.
  - MÁXIMO: nunca más de JWT_EXPIRE_MINUTES desde que se inició sesión
    (claim "ini"), aunque haya actividad; renovar no lo extiende.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings

_bearer_scheme = HTTPBearer(auto_error=False)

# El portal avisa 1 minuto antes de cerrar por inactividad y renueva a lo más
# una vez por minuto mientras hay actividad: este margen evita que el token
# venza en el servidor justo mientras el aviso sigue en pantalla.
MARGEN_INACTIVIDAD_MINUTOS = 2


def _vencimiento(inicio: datetime) -> datetime:
    settings = get_settings()
    por_inactividad = datetime.now(timezone.utc) + timedelta(
        minutes=settings.sesion_inactividad_minutos + MARGEN_INACTIVIDAD_MINUTOS
    )
    maximo = inicio + timedelta(minutes=settings.jwt_expire_minutes)
    return min(por_inactividad, maximo)


def crear_token(
    cl_usr_app: Optional[int] = None,
    usuario: Optional[str] = None,
    nombre: str = "",
    *,
    rfc: Optional[str] = None,
    perfil: Optional[int] = None,
    inicio: Optional[datetime] = None,
) -> str:
    """
    Emite el JWT de sesión. Soporta dos orígenes de login:
      - SISE (cl_usr_app, usuario): como antes, usado por /auth/login.
      - RFC (rfc, perfil): acceso propio de la app, usado por /auth/rfc/login.
    `inicio`: cuándo se inició la sesión (al renovar se conserva el original).
    """
    settings = get_settings()
    inicio = inicio or datetime.now(timezone.utc)
    payload = {"nombre": nombre, "exp": _vencimiento(inicio), "ini": int(inicio.timestamp())}
    if cl_usr_app is not None:
        payload["cl_usr_app"] = cl_usr_app
    if usuario is not None:
        payload["usuario"] = usuario
    if rfc is not None:
        payload["rfc"] = rfc
    if perfil is not None:
        payload["perfil"] = perfil
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def _decodificar_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Sesión inválida o expirada, inicia sesión de nuevo.",
        )


def renovar_token(token: str) -> str:
    """
    Token nuevo para la misma sesión, con la ventana de inactividad otra vez
    completa. Conserva el inicio original, así que no pasa del máximo: ya
    vencido ese máximo, responde 401 como cualquier sesión expirada.
    """
    payload = _decodificar_token(token)
    settings = get_settings()
    inicio = datetime.fromtimestamp(payload.get("ini") or datetime.now(timezone.utc).timestamp(), tz=timezone.utc)
    if datetime.now(timezone.utc) >= inicio + timedelta(minutes=settings.jwt_expire_minutes):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión inválida o expirada, inicia sesión de nuevo.")
    return crear_token(
        payload.get("cl_usr_app"), payload.get("usuario"), payload.get("nombre") or "",
        rfc=payload.get("rfc"), perfil=payload.get("perfil"), inicio=inicio,
    )


def usuario_desde_token(token: str) -> dict:
    """
    Decodifica y valida un JWT. Regresa un dict con lo que venga en el
    token (SISE: cl_usr_app/usuario, o RFC: rfc/perfil) — todos los
    campos son opcionales con .get() porque un token puede traer solo
    uno de los dos orígenes de login.
    Compartido entre la capa REST (usuario_actual) y la capa GraphQL
    (ver app/graphql/context.py), para no duplicar la lógica de sesión.
    """
    payload = _decodificar_token(token)
    return {
        "cl_usr_app": payload.get("cl_usr_app"),
        "usuario": payload.get("usuario"),
        "nombre": payload.get("nombre"),
        "rfc": payload.get("rfc"),
        "perfil": payload.get("perfil"),
    }


def usuario_actual(
    credenciales: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> dict:
    """
    Dependencia de FastAPI para proteger endpoints REST. Úsala como:
        @router.get("/algo", dependencies=[Depends(usuario_actual)])
    o para leer quién es el usuario:
        def endpoint(usuario: dict = Depends(usuario_actual)): ...
    Regresa {'cl_usr_app': int, 'usuario': str, 'nombre': str}.
    """
    if credenciales is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Debes iniciar sesión.")
    return usuario_desde_token(credenciales.credentials)
