from app.db.local_store import ahora_local, get_local_connection
from app.schemas.expediente import EstatusExpediente


def actualizar_estatus(cl_expediente: int, estatus: EstatusExpediente, identificador: str) -> None:
    """
    Guarda el estatus SOLO en la base local (SQLite) de la aplicación.
    No se ejecuta ningún SP ni se toca SQL Server, por instrucción
    explícita del usuario.

    identificador: RFC (o usuario SISE legado) de quién hizo el cambio --
    se usa para el corte de expedientes (columna "RFC Coordinador"),
    específicamente cuando el estatus queda en "En Espera de Respuesta".
    """
    with get_local_connection() as conn:
        conn.execute(
            """
            INSERT INTO estatus_expediente (cl_expediente, estatus, fecha_cambio, rfc_cambio)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(cl_expediente) DO UPDATE SET
                estatus = excluded.estatus,
                fecha_cambio = excluded.fecha_cambio,
                rfc_cambio = excluded.rfc_cambio
            """,
            (cl_expediente, estatus.value, ahora_local(), identificador),
        )
        conn.commit()


def obtener_detalle(cl_expediente: int) -> dict | None:
    """Usado por el corte: quién y cuándo fue el último cambio de estatus."""
    with get_local_connection() as conn:
        row = conn.execute(
            "SELECT estatus, fecha_cambio, rfc_cambio FROM estatus_expediente WHERE cl_expediente = ?",
            (cl_expediente,),
        ).fetchone()
        return dict(row) if row else None
