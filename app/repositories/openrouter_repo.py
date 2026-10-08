"""
Bitácora local de llamadas a OpenRouter (tabla openrouter_iteraciones, ver
app/db/local_store.py). Cada fila guarda tokens y costo TAL CUAL los regresó
OpenRouter en su respuesta (ver app/services/openrouter_service.py) -- este
repo solo persiste y agrega, nunca recalcula ni estima esos valores.
"""

from typing import Optional

from app.db.local_store import ahora_local, get_local_connection


def registrar_iteracion(
    modelo: str,
    tokens_entrada: int,
    tokens_salida: int,
    tokens_totales: int,
    costo_usd: float,
    descripcion: Optional[str] = None,
    identificador: Optional[str] = None,
) -> int:
    with get_local_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO openrouter_iteraciones
                (modelo, descripcion, identificador, tokens_entrada, tokens_salida, tokens_totales, costo_usd, fecha)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (modelo, descripcion, identificador, tokens_entrada, tokens_salida, tokens_totales, costo_usd, ahora_local()),
        )
        conn.commit()
        return cur.lastrowid


def listar_iteraciones(desde: Optional[str] = None, hasta: Optional[str] = None) -> list[dict]:
    """
    desde/hasta: 'YYYY-MM-DD' (inclusive). hasta se compara contra el día
    completo (hasta las 23:59:59) para no perder las iteraciones de ese
    mismo día por la parte de la hora.
    """
    consulta = "SELECT * FROM openrouter_iteraciones WHERE 1=1"
    parametros: list = []
    if desde:
        consulta += " AND fecha >= ?"
        parametros.append(f"{desde} 00:00:00")
    if hasta:
        consulta += " AND fecha <= ?"
        parametros.append(f"{hasta} 23:59:59")
    consulta += " ORDER BY fecha DESC"
    with get_local_connection() as conn:
        return [dict(r) for r in conn.execute(consulta, parametros).fetchall()]


def reporte(desde: Optional[str] = None, hasta: Optional[str] = None, top_n: int = 5) -> dict:
    """
    Agrega la bitácora en el rango dado: totales, promedio, desglose por
    modelo, desglose por día y las top_n peticiones de mayor consumo/costo.
    Se agrega en Python (no SQL) porque el volumen esperado de esta tabla
    es bajo y así se reutiliza la misma fuente de verdad para todo.
    """
    filas = listar_iteraciones(desde, hasta)

    total_peticiones = len(filas)
    tokens_entrada = sum(f["tokens_entrada"] for f in filas)
    tokens_salida = sum(f["tokens_salida"] for f in filas)
    tokens_totales = sum(f["tokens_totales"] for f in filas)
    costo_total = sum(f["costo_usd"] for f in filas)
    costo_promedio = (costo_total / total_peticiones) if total_peticiones else 0.0

    por_modelo: dict[str, dict] = {}
    por_dia: dict[str, dict] = {}
    for f in filas:
        m = por_modelo.setdefault(
            f["modelo"], {"modelo": f["modelo"], "peticiones": 0, "tokens_entrada": 0, "tokens_salida": 0, "tokens_totales": 0, "costo_usd": 0.0}
        )
        m["peticiones"] += 1
        m["tokens_entrada"] += f["tokens_entrada"]
        m["tokens_salida"] += f["tokens_salida"]
        m["tokens_totales"] += f["tokens_totales"]
        m["costo_usd"] += f["costo_usd"]

        dia = f["fecha"][:10]
        d = por_dia.setdefault(
            dia, {"fecha": dia, "peticiones": 0, "tokens_entrada": 0, "tokens_salida": 0, "tokens_totales": 0, "costo_usd": 0.0}
        )
        d["peticiones"] += 1
        d["tokens_entrada"] += f["tokens_entrada"]
        d["tokens_salida"] += f["tokens_salida"]
        d["tokens_totales"] += f["tokens_totales"]
        d["costo_usd"] += f["costo_usd"]

    mayor_consumo_tokens = sorted(filas, key=lambda f: f["tokens_totales"], reverse=True)[:top_n]
    mayor_costo = sorted(filas, key=lambda f: f["costo_usd"], reverse=True)[:top_n]

    return {
        "desde": desde,
        "hasta": hasta,
        "total_peticiones": total_peticiones,
        "tokens_entrada": tokens_entrada,
        "tokens_salida": tokens_salida,
        "tokens_totales": tokens_totales,
        "costo_total_usd": costo_total,
        "costo_promedio_usd": costo_promedio,
        "por_modelo": sorted(por_modelo.values(), key=lambda m: m["costo_usd"], reverse=True),
        "por_dia": sorted(por_dia.values(), key=lambda d: d["fecha"]),
        "mayor_consumo_tokens": mayor_consumo_tokens,
        "mayor_costo": mayor_costo,
    }
