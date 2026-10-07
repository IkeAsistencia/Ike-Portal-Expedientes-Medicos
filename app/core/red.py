"""
IP real del usuario cuando la app corre detrás de uno o más proxies (ALB,
CloudFront, nginx...).

Cada proxy agrega al final de X-Forwarded-For la IP de quien le hizo la
petición. Lo que esté antes lo pudo haber escrito el propio usuario, así que
no es confiable: la IP real es la que agregó el primer proxy de confianza,
es decir, la que está en la posición PROXIES_CONFIABLES contando desde el
final (ver app/config.py).

Se usa para el límite de intentos del login (app/core/rate_limit.py): si se
tomara el primer valor del encabezado, cualquiera podría falsear su IP y
saltarse el límite.
"""

from fastapi import Request

from app.config import get_settings


def ip_cliente(request: Request) -> str:
    proxies = get_settings().proxies_confiables
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded and proxies > 0:
        partes = [p.strip() for p in forwarded.split(",") if p.strip()]
        if partes:
            # Si llegaron menos entradas que proxies (ej. alguien le pegó
            # directo al balanceador sin pasar por CloudFront), se toma la
            # más antigua que haya.
            return partes[-proxies] if len(partes) >= proxies else partes[0]
    return request.client.host if request.client else ""
