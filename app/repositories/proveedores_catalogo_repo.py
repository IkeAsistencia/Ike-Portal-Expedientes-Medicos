from app.db.local_store import ahora_local, get_local_connection

_COLUMNAS_CATALOGO = (
    "cl_proveedor", "nombre", "especialidad", "cedula", "rfc", "estado", "municipio",
    "direccion", "consultorio", "telefono", "email", "horario", "costo_consulta",
    "convenio", "teleconsulta",
)


def reemplazar_catalogo(registros: list[dict], rfc_usuario: str) -> int:
    """
    Reemplazo COMPLETO: borra el catálogo anterior y mete el nuevo -- cada
    carga debe traer el catálogo completo, no solo los proveedores nuevos
    (decisión del usuario, 2026-10-16). Todo en una sola transacción: si
    algo falla a medias, no se queda un catálogo incompleto a medio cargar.
    """
    columnas_sql = ", ".join(_COLUMNAS_CATALOGO)
    placeholders = ", ".join(f":{c}" for c in _COLUMNAS_CATALOGO)
    with get_local_connection() as conn:
        conn.execute("DELETE FROM proveedores_catalogo")
        conn.executemany(
            f"INSERT INTO proveedores_catalogo ({columnas_sql}) VALUES ({placeholders})",
            registros,
        )
        conn.execute(
            "INSERT INTO proveedores_catalogo_cargas (rfc, total_filas, fecha) VALUES (?, ?, ?)",
            (rfc_usuario, len(registros), ahora_local()),
        )
        conn.commit()
    return len(registros)


def listar_catalogo() -> list[dict]:
    with get_local_connection() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM proveedores_catalogo ORDER BY nombre").fetchall()]


def contar_catalogo() -> int:
    with get_local_connection() as conn:
        return conn.execute("SELECT COUNT(*) FROM proveedores_catalogo").fetchone()[0]


def obtener_ultima_carga() -> dict | None:
    with get_local_connection() as conn:
        row = conn.execute(
            "SELECT rfc, total_filas, fecha FROM proveedores_catalogo_cargas ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None
