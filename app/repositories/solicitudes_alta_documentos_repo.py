"""
Documentos OPCIONALES de una solicitud de "Alta de médico": la constancia de
situación fiscal (respalda el RFC) y la cédula profesional. Como el resto de
la solicitud, viven SOLO en este portal (SQLite), nunca en SQL Server.

Un documento por tipo y solicitud: volver a subirlo reemplaza al anterior.
Mismos formatos, tamaño y revisión de contenido que el comprobante de pago
(ver comprobantes_repo).
"""
from app.db.local_store import ahora_local, get_local_connection

TIPOS_DOCUMENTO = {
    "constancia_fiscal": "Constancia de situación fiscal",
    "cedula": "Cédula profesional",
}


def guardar(folio: str, tipo: str, nombre_archivo: str, tipo_mime: str, contenido: bytes, rfc_subio: str) -> dict:
    fecha = ahora_local()
    with get_local_connection() as conn:
        conn.execute(
            "INSERT INTO solicitudes_alta_documentos "
            "(folio, tipo, nombre_archivo, tipo_mime, contenido, rfc_subio, fecha) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (folio, tipo) DO UPDATE SET nombre_archivo = excluded.nombre_archivo, "
            "tipo_mime = excluded.tipo_mime, contenido = excluded.contenido, "
            "rfc_subio = excluded.rfc_subio, fecha = excluded.fecha",
            (folio, tipo, nombre_archivo, tipo_mime, contenido, rfc_subio, fecha),
        )
        conn.commit()
    return {"nombre_archivo": nombre_archivo, "tipo_mime": tipo_mime, "fecha": fecha}


def obtener(folio: str, tipo: str) -> dict | None:
    with get_local_connection() as conn:
        fila = conn.execute(
            "SELECT nombre_archivo, tipo_mime, contenido, rfc_subio, fecha "
            "FROM solicitudes_alta_documentos WHERE folio = ? AND tipo = ?",
            (folio, tipo),
        ).fetchone()
        return dict(fila) if fila else None


def quitar(folio: str, tipo: str) -> bool:
    with get_local_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM solicitudes_alta_documentos WHERE folio = ? AND tipo = ?", (folio, tipo)
        )
        conn.commit()
        return cursor.rowcount > 0


def resumen_por_folio() -> dict[str, dict[str, dict]]:
    """{folio: {tipo: {nombre_archivo, fecha}}} sin el contenido, para la
    lista de Solicitudes (solo dice qué se subió)."""
    resumen: dict[str, dict[str, dict]] = {}
    with get_local_connection() as conn:
        for fila in conn.execute(
            "SELECT folio, tipo, nombre_archivo, fecha FROM solicitudes_alta_documentos"
        ).fetchall():
            resumen.setdefault(fila["folio"], {})[fila["tipo"]] = {
                "nombre_archivo": fila["nombre_archivo"], "fecha": fila["fecha"],
            }
    return resumen
