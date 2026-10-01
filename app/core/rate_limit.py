"""
Limitador de intentos simple, en memoria del propio proceso -- sin
dependencias nuevas. Pensado para endpoints de login/credenciales
(/auth/login, /auth/rfc/*), donde antes no había ningún freno a fuerza
bruta ni a enumeración de RFC.

LIMITACIÓN A TENER EN CUENTA: el conteo vive solo en memoria de ESTE
proceso. Si la app corre con varios workers/procesos (ej. uvicorn
--workers 4) o detrás de balanceo entre varias instancias, cada uno lleva
su propio conteo -- el límite real efectivo se multiplica por la cantidad
de procesos. Para un despliegue así, hay que mover esto a un backend
compartido (ej. Redis). Para esta app (tráfico bajo, un solo proceso) es
suficiente.
"""

import time
from collections import defaultdict
from threading import Lock

from fastapi import HTTPException, status

_intentos: dict[str, list[float]] = defaultdict(list)
_lock = Lock()


def verificar_limite(clave: str, maximo: int, ventana_segundos: int) -> None:
    """
    Lanza 429 si `clave` ya acumuló `maximo` intentos dentro de los
    últimos `ventana_segundos`. Si no, registra este intento y deja pasar.
    Úsalo con una clave que combine IP + identificador (usuario/RFC) para
    no bloquear a todo mundo detrás del mismo NAT por los fallos de una
    sola cuenta, ni dejar sin freno a quien va rotando de cuenta.
    """
    ahora = time.monotonic()
    limite_inferior = ahora - ventana_segundos
    with _lock:
        intentos = [t for t in _intentos[clave] if t > limite_inferior]
        if len(intentos) >= maximo:
            _intentos[clave] = intentos
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Demasiados intentos. Espera unos minutos antes de volver a intentar.",
            )
        intentos.append(ahora)
        _intentos[clave] = intentos


def limpiar_todo() -> None:
    """Para pruebas: resetea el conteo entre tests (el estado es del proceso,
    y pytest corre todas las pruebas en el mismo proceso)."""
    with _lock:
        _intentos.clear()
