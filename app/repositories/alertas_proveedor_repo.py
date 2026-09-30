from app.db.local_store import ahora_local, get_local_connection


def ya_se_envio(cl_expediente: int, nivel: str) -> bool:
    with get_local_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM alertas_proveedor_enviadas WHERE cl_expediente = ? AND nivel = ?",
            (cl_expediente, nivel),
        ).fetchone()
        return row is not None


def marcar_enviada(cl_expediente: int, nivel: str) -> None:
    with get_local_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO alertas_proveedor_enviadas (cl_expediente, nivel, fecha_envio) VALUES (?, ?, ?)",
            (cl_expediente, nivel, ahora_local()),
        )
        conn.commit()
