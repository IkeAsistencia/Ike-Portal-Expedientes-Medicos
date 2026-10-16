"""
Solicitudes de "Alta de médico" (pantalla "Proveedores" del Directorio de
Proveedores) -- quedan SOLO en este portal, nunca se mandan a Core. La
validación de cédula sigue siendo simulada en el frontend; aquí solo se
guarda la solicitud y su estatus para que Administrador la revise.

Un médico aprobado se vuelve visible en el Directorio de Proveedores (ver
listar_aprobados_como_directorio(), usado por
app/routers/directorio_proveedores.py) SIN copiarlo a proveedores_catalogo
-- ese catálogo es exclusivamente el que sube Administrador desde Excel, y
cada carga lo REEMPLAZA por completo (ver proveedores_catalogo_repo); si un
médico dado de alta aquí se guardara ahí, una recarga del Excel lo borraría.
"""
import random
import string

from app.db.local_store import ahora_local, get_local_connection

ESTATUS_VALIDOS = ("En revisión", "Aprobada", "Rechazada")


def _generar_folio() -> str:
    return "ALT-" + "".join(random.choices(string.digits, k=5))


def crear_solicitud(datos: dict, rfc_solicito: str) -> dict:
    folio = _generar_folio()
    with get_local_connection() as conn:
        conn.execute(
            "INSERT INTO solicitudes_alta_medico "
            "(folio, nombre, especialidad, cedula, rfc, estado, municipio, direccion, telefono, email, "
            " estatus, rfc_solicito, fecha) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'En revisión', ?, ?)",
            (
                folio, datos["nombre"], datos["especialidad"], datos["cedula"], datos.get("rfc"),
                datos.get("estado"), datos.get("municipio"), datos.get("direccion"),
                datos.get("telefono"), datos.get("email"), rfc_solicito, ahora_local(),
            ),
        )
        conn.commit()
    return {"folio": folio}


def listar_solicitudes() -> list[dict]:
    with get_local_connection() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM solicitudes_alta_medico ORDER BY id DESC"
        ).fetchall()]


def cambiar_estatus(folio: str, estatus: str) -> bool:
    with get_local_connection() as conn:
        cur = conn.execute(
            "UPDATE solicitudes_alta_medico SET estatus = ? WHERE folio = ?", (estatus, folio)
        )
        conn.commit()
        return cur.rowcount > 0


def listar_aprobados_como_directorio() -> list[dict]:
    """
    Los médicos dados de alta desde el portal y ya aprobados también deben
    verse en el Directorio de Proveedores -- se exponen con la misma forma
    que las filas de proveedores_catalogo (ver
    app/routers/directorio_proveedores.py), marcados origen='portal' y sin
    cl_proveedor real (no vienen de Core, por eso se identifican por folio).
    """
    with get_local_connection() as conn:
        filas = conn.execute(
            "SELECT folio, nombre, especialidad, cedula, rfc, estado, municipio, direccion, telefono, email "
            "FROM solicitudes_alta_medico WHERE estatus = 'Aprobada' ORDER BY nombre"
        ).fetchall()
    return [
        {
            "cl_proveedor": None, "folio": f["folio"], "nombre": f["nombre"], "especialidad": f["especialidad"],
            "cedula": f["cedula"], "rfc": f["rfc"], "estado": f["estado"], "municipio": f["municipio"],
            "direccion": f["direccion"], "consultorio": None, "telefono": f["telefono"], "email": f["email"],
            "horario": None, "costo_consulta": None, "convenio": None, "teleconsulta": 0,
            "codigo_postal": None, "latitud": None, "longitud": None, "origen": "portal",
        }
        for f in filas
    ]
