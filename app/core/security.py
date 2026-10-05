"""
Sesión de la aplicación: tras un login exitoso contra el SP legado, esta
app emite su PROPIO token (JWT) para no depender de @CreateSession del SP
(que se manda fijo en 0, según lo indicado). Los endpoints protegidos
exigen 'Authorization: Bearer <token>'.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings

_bearer_scheme = HTTPBearer(auto_error=False)


def crear_token(
    cl_usr_app: Optional[int] = None,
    usuario: Optional[str] = None,
    nombre: str = "",
    *,
    rfc: Optional[str] = None,
    perfil: Optional[int] = None,
) -> str:
    """
    Emite el JWT de sesión. Soporta dos orígenes de login:
      - SISE (cl_usr_app, usuario): como antes, usado por /auth/login.
      - RFC (rfc, perfil): acceso propio de la app, usado por /auth/rfc/login.
    """
    settings = get_settings()
    expira = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"nombre": nombre, "exp": expira}
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
