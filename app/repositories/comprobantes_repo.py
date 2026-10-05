from app.db.local_store import ahora_local, get_local_connection

TAMANO_MAXIMO_BYTES = 5 * 1024 * 1024  # 5 MB
TIPOS_MIME_PERMITIDOS = {"application/pdf", "image/jpeg", "image/png"}

# Primeros bytes ("magic numbers") reales de cada tipo permitido -- el
# Content-Type de un UploadFile lo manda el cliente (header HTTP), nadie
# verifica que el contenido real corresponda. Sin esto, se podía subir
# cualquier archivo con el Content-Type de la lista blanca puesto a mano.
_FIRMAS_POR_TIPO = {
    "application/pdf": (b"%PDF",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
}


def contenido_coincide_con_tipo(contenido: bytes, tipo_mime: str) -> bool:
    firmas = _FIRMAS_POR_TIPO.get(tipo_mime)
    if not firmas:
        return False
    return any(contenido.startswith(firma) for firma in firmas)


def existe_comprobante(cl_expediente: int) -> bool:
    with get_local_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM comprobantes_pago WHERE cl_expediente = ?", (cl_expediente,)
        ).fetchone()
        return row is not None


def guardar_comprobante(cl_expediente: int, rfc: str, nombre_archivo: str, tipo_mime: str, contenido: bytes) -> None:
    with get_local_connection() as conn:
        conn.execute(
            "INSERT INTO comprobantes_pago (cl_expediente, rfc, nombre_archivo, tipo_mime, contenido, fecha) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (cl_expediente, rfc, nombre_archivo, tipo_mime, contenido, ahora_local()),
        )
        conn.commit()


def obtener_comprobante(cl_expediente: int) -> dict | None:
    """El más reciente (si Proveedor lo volvió a subir tras una devolución de Cabina)."""
    with get_local_connection() as conn:
        row = conn.execute(
            "SELECT rfc, nombre_archivo, tipo_mime, contenido, fecha FROM comprobantes_pago "
            "WHERE cl_expediente = ? ORDER BY fecha DESC, id DESC LIMIT 1",
            (cl_expediente,),
        ).fetchone()
        return dict(row) if row else None
