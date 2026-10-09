import pyodbc

from app.db.connection import call_procedure, call_procedure_write
from app.db.local_store import ahora_local, get_local_connection
from app.schemas.seguimiento import SeguimientoInput

# clUsrApp fijo para dbo.sp_S2_Seguimiento (SP legado de SISE/Core, ya
# existente en la base, no creado por este proyecto). OJO: mandarlo en 1
# (en vez de 0) dispara reglas de negocio propias de Core que NO deben
# aplicar en este portal (confirmado por el usuario) -- 0 es el valor
# neutro para este SP.
CL_USR_APP_HISTORIAL_SISE = 0


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


class ErrorRegistroSeguimiento(Exception):
    """
    El insert hacia dbo.Seguimiento (Core) falló por un error de base de
    datos (no por una regla de negocio -- esas ya se validan antes de
    llegar a registrar_seguimiento). El intento ya quedó guardado en la
    bitácora PROPIA del portal (ver registrar_fallo_local) para revisión
    manual -- a propósito NO se escribe nada en Core ni en la copia local
    de comentarios (comentarios_seguimiento), porque esa sí debe reflejar
    solo lo que realmente llegó a Core.
    """


def registrar_seguimiento(data: SeguimientoInput, cl_usr_app: int, nombre: str | None = None) -> dict:
    """
    Inserta un registro en dbo.Seguimiento (tabla ya existente, vía
    dbo.ST_CP_RegistrarSeguimiento). El clUsrApp viene del usuario
    autenticado (JWT emitido en /auth/login), nunca de un campo libre del
    formulario.

    nombre: nombre de quien inició sesión en el portal -- solo se usa si
    la llamada falla (ver registrar_fallo_local), para identificar de
    quién fue el intento al revisarlo después.
    """
    try:
        rows = call_procedure_write(
            "dbo.ST_CP_RegistrarSeguimiento",
            {
                "clExpediente": data.cl_expediente,
                "Observaciones": data.comentario,
                "clUsrApp": cl_usr_app,
            },
        )
    except pyodbc.Error as e:
        registrar_fallo_local(data.cl_expediente, data.comentario, cl_usr_app, nombre, str(e))
        raise ErrorRegistroSeguimiento(
            "No se pudo guardar el seguimiento en Core por un problema de conexión con la base de datos. "
            "Tu intento quedó guardado en el portal para revisión manual -- no lo repitas todavía."
        ) from e
    return rows[0] if rows else {}


def registrar_fallo_local(
    cl_expediente: int, observaciones: str, cl_usr_app: int, nombre: str | None, error: str
) -> None:
    """
    Bitácora PROPIA del portal (tabla seguimiento_core_fallidos, SQLite
    local) -- NUNCA dbo.Seguimiento ni comentarios_seguimiento -- para los
    intentos de "Actualizar Core" / "Regresar a Proveedor" que no se
    pudieron insertar en Core por un error de base de datos. 'nombre' es
    el nombre de quien inició sesión en el portal (no RFC, no clUsrApp).
    """
    with get_local_connection() as conn:
        conn.execute(
            "INSERT INTO seguimiento_core_fallidos "
            "(cl_expediente, observaciones, cl_usr_app, nombre, error, fecha) VALUES (?, ?, ?, ?, ?, ?)",
            (cl_expediente, observaciones, cl_usr_app, nombre, error, ahora_local()),
        )
        conn.commit()


def listar_fallos_locales() -> list[dict]:
    """Para consultar después los intentos que no llegaron a Core (ver registrar_fallo_local)."""
    with get_local_connection() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM seguimiento_core_fallidos ORDER BY fecha DESC").fetchall()]


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


def listar_historial_sise(cl_expediente: int) -> list[dict]:
    """
    Bitácora de Core/SISE para este expediente, vía el SP legado ya
    existente dbo.sp_S2_Seguimiento. Parámetros confirmados por el usuario:
        @clExpediente AS INT = 0, @clUsrApp AS INT = 0
    (clUsrApp fijo en CL_USR_APP_HISTORIAL_SISE = 0 -- mandarlo en 1 activa
    reglas de negocio de Core que no deben aplicar en este portal).

    Columnas que regresa el SP: Fecha, Estatus, Proveedor, Nombre,
    Observaciones, Accion, CSSRow -- las dos últimas (botones/estilo de la
    pantalla original de SISE) se descartan aquí, no aplican al portal.
    """
    rows = call_procedure(
        "dbo.sp_S2_Seguimiento",
        {"clExpediente": cl_expediente, "clUsrApp": CL_USR_APP_HISTORIAL_SISE},
    )
    resultado = []
    for r in rows:
        fecha = r.get("Fecha")
        nombre = r.get("Nombre")
        resultado.append(
            {
                "fecha": fecha.isoformat(sep=" ") if hasattr(fecha, "isoformat") else (str(fecha) if fecha is not None else None),
                "estatus": r.get("Estatus"),
                "proveedor": r.get("Proveedor"),
                # Nombre puede venir NULL/vacío -- se deja en None (nunca un
                # placeholder como "—" o el RFC) para que el frontend lo
                # muestre en blanco, como lo pidió el usuario.
                "nombre": nombre if nombre else None,
                "observaciones": r.get("Observaciones"),
            }
        )
    return resultado


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
