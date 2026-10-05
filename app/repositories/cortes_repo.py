import json

from app.db.local_store import ahora_local, get_local_connection


def crear_corte(
    rfc: str, tipo_expediente: str, expedientes: list[int], nombre_archivo: str, contenido: bytes
) -> int:
    with get_local_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO cortes_generados "
            "(rfc, tipo_expediente, expedientes, nombre_archivo, contenido, fecha_generado) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (rfc, tipo_expediente, json.dumps(expedientes), nombre_archivo, contenido, ahora_local()),
        )
        conn.commit()
        return cursor.lastrowid


def obtener_corte(corte_id: int) -> dict | None:
    with get_local_connection() as conn:
        row = conn.execute(
            "SELECT id, rfc, tipo_expediente, expedientes, nombre_archivo, contenido, "
            "fecha_generado, enviado, destinatario, fecha_enviado "
            "FROM cortes_generados WHERE id = ?",
            (corte_id,),
        ).fetchone()
        if not row:
            return None
        datos = dict(row)
        datos["expedientes"] = json.loads(datos["expedientes"])
        return datos


def marcar_enviado(corte_id: int, destinatario: str) -> None:
    with get_local_connection() as conn:
        conn.execute(
            "UPDATE cortes_generados SET enviado = 1, destinatario = ?, fecha_enviado = ? WHERE id = ?",
            (destinatario, ahora_local(), corte_id),
        )
        conn.commit()
