"""
Citas agendadas desde el Directorio de Proveedores (tabla `citas_proveedor`).

Se amarran a `proveedores.clave` -- la clave que genera el portal, no el id
interno ni `cl_proveedor` del sistema central. Esa es justamente la razón de
que exista: una carga de Excel ya no deja citas huérfanas, y un médico que
primero se dio de alta en el portal conserva sus citas cuando después llega
en la carga (ver proveedores_repo.cargar_padron).
"""

import sqlite3

from app.db.local_store import ahora_local, get_local_connection

PREFIJO_FOLIO = "CITA-"
_LARGO_CONSECUTIVO = 5

ESTATUS_AGENDADA = "Agendada"
ESTATUS_CANCELADA = "Cancelada"


class HorarioOcupado(Exception):
    """Ese médico ya tiene una cita en esa fecha y hora."""


def _siguiente_folio(conn) -> str:
    fila = conn.execute(
        f"SELECT MAX(CAST(SUBSTR(folio, {len(PREFIJO_FOLIO) + 1}) AS INTEGER)) AS maximo FROM citas_proveedor"
    ).fetchone()
    return PREFIJO_FOLIO + str((fila["maximo"] or 0) + 1).zfill(_LARGO_CONSECUTIVO)


def agendar(clave_proveedor: str, fecha: str, hora: str, paciente: str | None, rfc_agendo: str) -> dict:
    with get_local_connection() as conn:
        folio = _siguiente_folio(conn)
        try:
            conn.execute(
                "INSERT INTO citas_proveedor "
                "(folio, clave_proveedor, fecha, hora, paciente, rfc_agendo, estatus, fecha_registro) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (folio, clave_proveedor, fecha, hora, paciente, rfc_agendo, ESTATUS_AGENDADA, ahora_local()),
            )
        except sqlite3.IntegrityError as e:
            # Lo garantiza el UNIQUE (clave_proveedor, fecha, hora) de la
            # tabla, no una consulta previa: entre el "ya está libre" y el
            # INSERT puede colarse otra petición.
            raise HorarioOcupado("Ese horario ya fue apartado con este médico.") from e
        conn.commit()
    return {"folio": folio, "clave_proveedor": clave_proveedor, "fecha": fecha, "hora": hora}


def horarios_ocupados(clave_proveedor: str, fecha: str) -> list[str]:
    with get_local_connection() as conn:
        filas = conn.execute(
            "SELECT hora FROM citas_proveedor "
            "WHERE clave_proveedor = ? AND fecha = ? AND estatus = ? ORDER BY hora",
            (clave_proveedor, fecha, ESTATUS_AGENDADA),
        ).fetchall()
    return [f["hora"] for f in filas]


def listar_citas(clave_proveedor: str | None = None) -> list[dict]:
    """
    Citas con el nombre/especialidad del médico resueltos. El LEFT JOIN es a
    propósito: si algún día se borrara un proveedor del padrón, la cita debe
    seguir apareciendo (con el nombre vacío) en vez de desaparecer del
    control.
    """
    sql = (
        "SELECT c.folio, c.clave_proveedor, c.fecha, c.hora, c.paciente, c.rfc_agendo, "
        "       c.estatus, c.fecha_registro, "
        "       p.nombre AS proveedor_nombre, p.especialidad AS proveedor_especialidad, "
        "       p.origen AS proveedor_origen "
        "FROM citas_proveedor c "
        "LEFT JOIN proveedores p ON p.clave = c.clave_proveedor "
    )
    parametros: tuple = ()
    if clave_proveedor:
        sql += "WHERE c.clave_proveedor = ? "
        parametros = (clave_proveedor,)
    sql += "ORDER BY c.fecha DESC, c.hora DESC"
    with get_local_connection() as conn:
        return [dict(r) for r in conn.execute(sql, parametros).fetchall()]


def cancelar(folio: str) -> bool:
    with get_local_connection() as conn:
        cur = conn.execute(
            "UPDATE citas_proveedor SET estatus = ? WHERE folio = ? AND estatus = ?",
            (ESTATUS_CANCELADA, folio, ESTATUS_AGENDADA),
        )
        conn.commit()
        return cur.rowcount > 0


def contar_citas() -> int:
    with get_local_connection() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM citas_proveedor WHERE estatus = ?", (ESTATUS_AGENDADA,)
        ).fetchone()[0]
