from app.db.connection import call_procedure_write
from app.db.local_store import ahora_local, get_local_connection
from app.schemas.seguimiento import SeguimientoInput


def registrar_seguimiento(data: SeguimientoInput, cl_usr_app: int) -> dict:
    """
    Inserta un registro en dbo.Seguimiento (tabla ya existente). El
    clUsrApp viene del usuario autenticado (JWT emitido en /auth/login),
    nunca de un campo libre del formulario.
    """
    rows = call_procedure_write(
        "dbo.RegistrarSeguimiento",
        {
            "clExpediente": data.cl_expediente,
            "Observaciones": data.comentario,
            "clUsrApp": cl_usr_app,
        },
    )
    return rows[0] if rows else {}


def guardar_comentario_local(cl_expediente: int, rfc: str, comentario: str, origen: str = "proveedor") -> None:
    """
    Copia local del comentario, ver nota en app/schemas/seguimiento.py:ComentarioSeguimiento.
    origen: 'proveedor' (Actualizar Core) | 'cabina' (Regresar a Proveedor) --
    distingue en qué sección de Seguimiento de expedientes debe mostrarse.
    """
    with get_local_connection() as conn:
        conn.execute(
            "INSERT INTO comentarios_seguimiento (cl_expediente, rfc, comentario, origen, fecha) "
            "VALUES (?, ?, ?, ?, ?)",
            (cl_expediente, rfc, comentario, origen, ahora_local()),
        )
        conn.commit()


def listar_comentarios_local(cl_expediente: int, origen: str | None = None) -> list[dict]:
    with get_local_connection() as conn:
        if origen:
            rows = conn.execute(
                "SELECT rfc, comentario, origen, fecha FROM comentarios_seguimiento "
                "WHERE cl_expediente = ? AND origen = ? ORDER BY fecha DESC",
                (cl_expediente, origen),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT rfc, comentario, origen, fecha FROM comentarios_seguimiento "
                "WHERE cl_expediente = ? ORDER BY fecha DESC",
                (cl_expediente,),
            ).fetchall()
        return [dict(r) for r in rows]
