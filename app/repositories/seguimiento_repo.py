from app.db.connection import call_procedure_write
from app.db.local_store import ahora_local, get_local_connection
from app.schemas.seguimiento import SeguimientoInput


# Formato del texto que se inserta en Core (dbo.Seguimiento.Observaciones):
#   "Cabina Médica --> {nombre}\n{comentario}"   (Coordinador de Cabina)
#   "Proveedores --> {nombre}\n{comentario}"     (Proveedor)
# y, si el expediente es de pago anticipado, el comentario del Proveedor
# empieza con "PA-" -- así los identifican en Core.
ETIQUETA_CORE_CABINA = "Cabina Médica"
ETIQUETA_CORE_PROVEEDOR = "Proveedores"
PREFIJO_PAGO_ANTICIPADO = "PA-"
# Tamaño de @Observaciones en dbo.ST_CP_RegistrarSeguimiento (NVARCHAR(1500)):
# lo que pase de ahí SQL Server lo cortaría sin avisar.
LONGITUD_MAXIMA_OBSERVACIONES_CORE = 1500


def observaciones_para_core(etiqueta: str, nombre: str, comentario: str) -> str:
    return f"{etiqueta} --> {nombre}\n{comentario}"


def registrar_seguimiento(data: SeguimientoInput, cl_usr_app: int) -> dict:
    """
    Inserta un registro en dbo.Seguimiento (tabla ya existente). El
    clUsrApp viene del usuario autenticado (JWT emitido en /auth/login),
    nunca de un campo libre del formulario.
    """
    rows = call_procedure_write(
        "dbo.ST_CP_RegistrarSeguimiento",
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
    """El nombre de quien escribió se toma de los accesos dados de alta (así
    aplica también a comentarios ya guardados); si el RFC ya no existe ahí,
    se regresa el RFC como nombre."""
    consulta = (
        "SELECT c.rfc, COALESCE(u.nombre, c.rfc) AS nombre, c.comentario, c.origen, c.fecha "
        "FROM comentarios_seguimiento c LEFT JOIN usuarios_acceso u ON u.rfc = c.rfc "
        "WHERE c.cl_expediente = ?"
    )
    parametros: tuple = (cl_expediente,)
    if origen:
        consulta += " AND c.origen = ?"
        parametros += (origen,)
    consulta += " ORDER BY c.fecha DESC"
    with get_local_connection() as conn:
        return [dict(r) for r in conn.execute(consulta, parametros).fetchall()]
