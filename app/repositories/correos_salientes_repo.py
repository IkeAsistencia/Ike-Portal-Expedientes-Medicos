"""
Correos que salen del portal, para el tope diario (ver app/db/local_store.py:
tabla correos_salientes y app/services/cuota_correos_service.py).
"""

from app.db.local_store import ahora_local, get_local_connection


def usados_del_dia(dia: str) -> int:
    with get_local_connection() as conn:
        fila = conn.execute(
            "SELECT COALESCE(SUM(unidades), 0) AS usados FROM correos_salientes WHERE dia = ?", (dia,)
        ).fetchone()
    return int(fila["usados"])


def reservar(dia: str, origen: str, unidades: int, limite: int, simulado: bool) -> int | None:
    """
    Aparta `unidades` del tope del día ANTES de mandar el correo. Regresa el
    id del apartado, o None si no caben (no se aparta nada).

    Revisar y apartar van en una sola transacción con candado de escritura
    (BEGIN IMMEDIATE): si dos personas envían al mismo tiempo con 99 usados,
    solo una alcanza el último lugar -- la otra ve el tope ya lleno.
    """
    with get_local_connection() as conn:
        conn.isolation_level = None
        conn.execute("BEGIN IMMEDIATE")
        try:
            usados = conn.execute(
                "SELECT COALESCE(SUM(unidades), 0) FROM correos_salientes WHERE dia = ?", (dia,)
            ).fetchone()[0]
            if usados + unidades > limite:
                conn.execute("ROLLBACK")
                return None
            cur = conn.execute(
                "INSERT INTO correos_salientes (dia, origen, unidades, simulado, fecha) VALUES (?, ?, ?, ?, ?)",
                (dia, origen, unidades, int(simulado), ahora_local()),
            )
            conn.execute("COMMIT")
            return cur.lastrowid
        except Exception:
            conn.execute("ROLLBACK")
            raise


def liberar(reserva_id: int) -> None:
    """El correo no se pudo mandar: lo apartado vuelve a estar disponible."""
    with get_local_connection() as conn:
        conn.execute("DELETE FROM correos_salientes WHERE id = ?", (reserva_id,))
        conn.commit()
