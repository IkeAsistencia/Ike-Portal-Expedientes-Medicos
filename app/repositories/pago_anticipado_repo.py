from app.db.local_store import ahora_local, get_local_connection


def obtener(cl_expediente: int) -> dict | None:
    with get_local_connection() as conn:
        row = conn.execute(
            "SELECT es_anticipado, bloqueado, rfc, fecha FROM expediente_pago_anticipado WHERE cl_expediente = ?",
            (cl_expediente,),
        ).fetchone()
        return dict(row) if row else None


def es_anticipado(cl_expediente: int) -> bool:
    row = obtener(cl_expediente)
    return bool(row and row["es_anticipado"])


def marcar(cl_expediente: int, es_anticipado: bool, rfc: str) -> None:
    """Solo lo marca Proveedor, y solo mientras no esté bloqueado (ver router)."""
    with get_local_connection() as conn:
        conn.execute(
            """
            INSERT INTO expediente_pago_anticipado (cl_expediente, es_anticipado, rfc, fecha)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(cl_expediente) DO UPDATE SET
                es_anticipado = excluded.es_anticipado,
                rfc = excluded.rfc,
                fecha = excluded.fecha
            """,
            (cl_expediente, int(es_anticipado), rfc, ahora_local()),
        )
        conn.commit()


def bloquear(cl_expediente: int) -> None:
    """
    Se llama en cuanto Proveedor manda su primer comentario -- si nunca tocó
    la casilla, queda fijo en "no es anticipado" (0) a partir de aquí.
    """
    with get_local_connection() as conn:
        conn.execute(
            """
            INSERT INTO expediente_pago_anticipado (cl_expediente, es_anticipado, bloqueado, fecha)
            VALUES (?, 0, 1, ?)
            ON CONFLICT(cl_expediente) DO UPDATE SET bloqueado = 1
            """,
            (cl_expediente, ahora_local()),
        )
        conn.commit()
