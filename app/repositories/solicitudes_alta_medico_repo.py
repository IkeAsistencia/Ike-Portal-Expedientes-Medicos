"""
Solicitudes de "Alta de médico" (pantalla "Proveedores" del Directorio de
Proveedores) -- quedan SOLO en este portal, nunca se mandan al sistema
central.

Al APROBARSE, el médico entra al padrón (`proveedores`, ver
proveedores_repo.alta_desde_portal) con origen='portal' -- o sea, "Fuera de
la red" -- y con su propia clave. Esa clave es la que amarra sus citas, así
que si después llega en la carga de Excel no se duplica ni pierde su agenda:
el mismo renglón solo cambia de origen a 'catalogo' ("Dentro de la red").
"""
import random
import string

from app.db.local_store import ahora_local, get_local_connection
from app.repositories import proveedores_repo

ESTATUS_EN_REVISION = "En revisión"
ESTATUS_APROBADA = "Aprobada"
ESTATUS_RECHAZADA = "Rechazada"
ESTATUS_VALIDOS = (ESTATUS_EN_REVISION, ESTATUS_APROBADA, ESTATUS_RECHAZADA)

_CAMPOS_SOLICITUD = (
    "nombre", "especialidad", "cedula", "rfc", "estado", "municipio",
    "calle_num_ext_int", "colonia", "codigo_postal", "telefono", "email",
)


def _generar_folio() -> str:
    return "ALT-" + "".join(random.choices(string.digits, k=5))


def crear_solicitud(datos: dict, rfc_solicito: str) -> dict:
    folio = _generar_folio()
    columnas = ("folio",) + _CAMPOS_SOLICITUD + ("estatus", "rfc_solicito", "fecha")
    valores = {
        "folio": folio,
        **{c: datos.get(c) for c in _CAMPOS_SOLICITUD},
        "estatus": ESTATUS_EN_REVISION, "rfc_solicito": rfc_solicito, "fecha": ahora_local(),
    }
    with get_local_connection() as conn:
        conn.execute(
            f"INSERT INTO solicitudes_alta_medico ({', '.join(columnas)}) "
            f"VALUES ({', '.join(':' + c for c in columnas)})",
            valores,
        )
        conn.commit()
    return {"folio": folio}


def listar_solicitudes() -> list[dict]:
    with get_local_connection() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM solicitudes_alta_medico ORDER BY id DESC"
        ).fetchall()]


def obtener_solicitud(folio: str) -> dict | None:
    with get_local_connection() as conn:
        fila = conn.execute("SELECT * FROM solicitudes_alta_medico WHERE folio = ?", (folio,)).fetchone()
        return dict(fila) if fila else None


def cambiar_estatus(folio: str, estatus: str) -> dict | None:
    """
    Cambia el estatus y, si se aprueba, da de alta al médico en el padrón.
    Devuelve la solicitud ya actualizada (o None si el folio no existe).

    El alta en el padrón es idempotente: volver a aprobar la misma solicitud
    no crea un segundo renglón (ver proveedores_repo.alta_desde_portal).
    """
    solicitud = obtener_solicitud(folio)
    if solicitud is None:
        return None

    clave = solicitud.get("clave_proveedor")
    if estatus == ESTATUS_APROBADA:
        clave = proveedores_repo.alta_desde_portal(solicitud, folio)

    with get_local_connection() as conn:
        conn.execute(
            "UPDATE solicitudes_alta_medico SET estatus = ?, clave_proveedor = ? WHERE folio = ?",
            (estatus, clave, folio),
        )
        conn.commit()
    return obtener_solicitud(folio)
