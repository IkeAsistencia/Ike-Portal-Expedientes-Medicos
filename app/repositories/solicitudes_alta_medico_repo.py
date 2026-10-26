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
import re
import string
import unicodedata

from app.db.local_store import ahora_local, get_local_connection
from app.repositories import proveedores_repo

ESTATUS_EN_REVISION = "En revisión"
ESTATUS_APROBADA = "Aprobada"
ESTATUS_RECHAZADA = "Rechazada"
# "Cédula no localizada" se quitó (2026-10-26): no había forma de ponerlo
# desde la pantalla. Las que lo tuvieran vuelven a "En revisión" (ver
# _migrar_columnas_faltantes en local_store.py).
ESTATUS_VALIDOS = (ESTATUS_EN_REVISION, ESTATUS_APROBADA, ESTATUS_RECHAZADA)

# Estatus en el que la solicitud TODAVÍA se puede corregir (botón "Editar",
# exclusivo de Administrador).
#
# Aprobada y Rechazada quedan fuera: aprobada ya creó al proveedor en el
# padrón con su clave (y puede tener citas), así que editarla aquí dejaría
# los dos lados en desacuerdo.
ESTATUS_EDITABLES = (ESTATUS_EN_REVISION,)

# Las que cuentan para no repetir un alta: una rechazada no impide volver a
# intentarlo.
ESTATUS_VIGENTES = (ESTATUS_EN_REVISION, ESTATUS_APROBADA)

_CAMPOS_SOLICITUD = (
    "nombre", "especialidad", "cedula", "rfc", "estado", "municipio",
    "calle_num_ext_int", "colonia", "codigo_postal", "consultorio", "horario", "costo_consulta",
    "telefono", "email",
)


def _comparable(texto) -> str:
    """Para comparar lo que escribe una persona: sin acentos, sin mayúsculas
    y sin signos ni espacios ("Av. Vallarta #1450" == "av vallarta 1450")."""
    sin_acentos = unicodedata.normalize("NFD", str(texto or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", sin_acentos.lower())


def _misma_alta(fila: dict, datos: dict) -> bool:
    return all(
        _comparable(fila.get(c)) == _comparable(datos.get(c))
        for c in ("especialidad", "codigo_postal", "calle_num_ext_int")
    )


def existe_alta_igual(datos: dict, excluir_folio: str | None = None) -> bool:
    """
    Regla de duplicados: un mismo RFC puede tener varias altas (una empresa
    con varios servicios o varias sucursales), pero no dos con la MISMA
    especialidad en el MISMO domicilio (código postal + calle).

    Cuenta lo que ya está en revisión o aprobado y el padrón oficial; una
    solicitud rechazada no impide volver a intentarlo.
    """
    rfc = (datos.get("rfc") or "").strip().upper()
    if not rfc:
        return False
    marcadores = ", ".join("?" for _ in ESTATUS_VIGENTES)
    with get_local_connection() as conn:
        solicitudes = conn.execute(
            f"SELECT folio, especialidad, codigo_postal, calle_num_ext_int FROM solicitudes_alta_medico "
            f"WHERE UPPER(rfc) = ? AND estatus IN ({marcadores})",
            (rfc, *ESTATUS_VIGENTES),
        ).fetchall()
        padron = conn.execute(
            "SELECT especialidad, codigo_postal, calle_num_ext_int FROM proveedores WHERE UPPER(rfc) = ?",
            (rfc,),
        ).fetchall()
    if any(_misma_alta(dict(f), datos) for f in solicitudes if f["folio"] != excluir_folio):
        return True
    return any(_misma_alta(dict(f), datos) for f in padron)


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
    Corrige los datos de una solicitud sin resolver ("En revisión", ver
    ESTATUS_EDITABLES; botón "Editar", exclusivo de Administrador). Devuelve
    la solicitud ya actualizada, o None si el folio no existe.

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
