from app.db.local_store import get_local_connection


def listar_cuentas_configuradas() -> list[dict]:
    with get_local_connection() as conn:
        rows = conn.execute("SELECT cl_cuenta, nombre FROM cuentas_configuradas").fetchall()
        return [dict(r) for r in rows]


def agregar_cuenta_configurada(cl_cuenta: int, nombre: str) -> None:
    with get_local_connection() as conn:
        existe = conn.execute(
            "SELECT 1 FROM cuentas_configuradas WHERE cl_cuenta = ?", (cl_cuenta,)
        ).fetchone()
        if existe:
            raise ValueError(f"La cuenta {nombre} ya está configurada.")
        conn.execute(
            "INSERT INTO cuentas_configuradas (cl_cuenta, nombre) VALUES (?, ?)",
            (cl_cuenta, nombre),
        )
        conn.commit()


def eliminar_cuenta_configurada(cl_cuenta: int) -> bool:
    with get_local_connection() as conn:
        cur = conn.execute("DELETE FROM cuentas_configuradas WHERE cl_cuenta = ?", (cl_cuenta,))
        conn.commit()
        return cur.rowcount > 0


def limpiar_cuentas_configuradas() -> None:
    with get_local_connection() as conn:
        conn.execute("DELETE FROM cuentas_configuradas")
        conn.commit()
