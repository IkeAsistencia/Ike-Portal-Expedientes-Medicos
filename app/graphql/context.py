"""
Contexto de cada request GraphQL. Expone:
  - `usuario`: el usuario autenticado (dict) o None si no hay token válido.
  - `requerir_usuario()`: igual, pero lanza un error GraphQL si no hay sesión
    (equivalente a los `Depends(usuario_actual)` que protegen el REST).
  - `host_servidor()` / `ip_cliente()`: mismos datos que arma
    app/routers/auth.py para el login por REST, reutilizados aquí para
    que la mutation `login` de GraphQL haga exactamente lo mismo.
"""

import socket
from typing import Optional

from fastapi import Request
from strawberry.fastapi import BaseContext

from app.core.security import usuario_desde_token


class Context(BaseContext):
    def __init__(self, request: Request):
        super().__init__()
        self.request = request
        self._usuario_resuelto = False
        self._usuario: Optional[dict] = None

    @property
    def usuario(self) -> Optional[dict]:
        if self._usuario_resuelto:
            return self._usuario
        self._usuario_resuelto = True

        auth = self.request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            return None
        token = auth[7:].strip()
        try:
            self._usuario = usuario_desde_token(token)
        except Exception:
            self._usuario = None
        return self._usuario

    def requerir_usuario(self) -> dict:
        usuario = self.usuario
        if usuario is None:
            raise PermissionError("Debes iniciar sesión (header Authorization: Bearer <token>).")
        return usuario

    def host_servidor(self) -> str:
        return socket.gethostname()[:20]

    def ip_cliente(self) -> str:
        forwarded = self.request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()[:20]
        return (self.request.client.host if self.request.client else "")[:20]


async def get_context(request: Request) -> Context:
    return Context(request=request)
