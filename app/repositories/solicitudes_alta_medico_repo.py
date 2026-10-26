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
ESTATUS_CEDULA_NO_LOCALIZADA = "Cédula no localizada"
ESTATUS_APROBADA = "Aprobada"
ESTATUS_RECHAZADA = "Rechazada"
ESTATUS_VALIDOS = (
    ESTATUS_EN_REVISION, ESTATUS_CEDULA_NO_LOCALIZADA, ESTATUS_APROBADA, ESTATUS_RECHAZADA,
)

# Estatus en los que la solicitud TODAVÍA se puede corregir (botón "Editar",
# exclusivo de Administrador). Son los dos estados "sin resolver": o nadie la
# ha revisado, o se revisó y la cédula profesional no se localizó en el
# registro, que es justo el caso que hay que poder corregir.
#
# Aprobada y Rechazada quedan fuera: aprobada ya creó al proveedor en el
# padrón con su clave (y puede tener citas), así que editarla aquí dejaría
# los dos lados en desacuerdo.
ESTATUS_EDITABLES = (ESTATUS_EN_REVISION, ESTATUS_CEDULA_NO_LOCALIZADA)

_CAMPOS_SOLICITUD = (
    "nombre", "especialidad", "cedula", "rfc", "estado", "municipio",
    "calle_num_ext_int", "colonia", "codigo_postal", "consultorio", "horario", "telefono", "email",
)


class SolicitudYaResuelta(Exception):
    """La solicitud ya se aprobó o rechazó, así que sus datos ya no se editan."""


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


def actualizar_solicitud(folio: str, datos: dict) -> dict | None:
    """
    Corrige los datos de una solicitud sin resolver -- "En revisión" o
    "Cédula no localizada", ver ESTATUS_EDITABLES (botón "Editar",
    exclusivo de Administrador). Devuelve la solicitud ya actualizada, o
    None si el folio no existe.

    Si ya fue aprobada o rechazada lanza SolicitudYaResuelta: aprobada
    significa que el proveedor ya está en el padrón con su clave y puede
    tener citas, así que editar aquí dejaría los dos lados en desacuerdo.
    """
    solicitud = obtener_solicitud(folio)
    if solicitud is None:
        return None
    if solicitud["estatus"] not in ESTATUS_EDITABLES:
        raise SolicitudYaResuelta(
            f"La solicitud {folio} ya está {solicitud['estatus'].lower()}; sus datos ya no se pueden editar."
        )

    asignaciones = {c: datos.get(c) for c in _CAMPOS_SOLICITUD}
    asignaciones["folio"] = folio
    # El estatus se repite en el WHERE (además de la validación de arriba)
    # para que, si alguien la resuelve entre la lectura y el UPDATE, el
    # cambio ya no entre.
    marcadores_editables = ", ".join(f":estatus_{i}" for i in range(len(ESTATUS_EDITABLES)))
    for i, valor in enumerate(ESTATUS_EDITABLES):
        asignaciones[f"estatus_{i}"] = valor
    sets = ", ".join(f"{c} = :{c}" for c in _CAMPOS_SOLICITUD)
    with get_local_connection() as conn:
        conn.execute(
            f"UPDATE solicitudes_alta_medico SET {sets} "
            f"WHERE folio = :folio AND estatus IN ({marcadores_editables})",
            asignaciones,
        )
        conn.commit()
    return obtener_solicitud(folio)


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
