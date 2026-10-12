"""
Historial de "Enviar correo a proveedores" (ver app/db/local_store.py:
tabla correos_enviados). Sirve para comprobar después qué se mandó, a quién,
cuándo y quién le dio clic -- por ejemplo, si un proveedor dice que nunca se
le notificó un expediente.
"""

import json

from app.db.local_store import ahora_local, get_local_connection
from app.repositories import accesos_repo


def registrar_envio(
    tipo: str, destinatario: str, expedientes: list[int], rfc_envio: str, simulado: bool
) -> None:
    with get_local_connection() as conn:
        conn.execute(
            "INSERT INTO correos_enviados (tipo, destinatario, expedientes, rfc_envio, simulado, fecha) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (tipo, destinatario, json.dumps(expedientes), rfc_envio, int(simulado), ahora_local()),
        )
        conn.commit()


def listar_por_expediente(cl_expediente: int) -> list[dict]:
    """Correos que incluyeron este expediente, más reciente primero."""
    with get_local_connection() as conn:
        rows = conn.execute("SELECT * FROM correos_enviados ORDER BY fecha DESC").fetchall()

    resultado = []
    for row in rows:
        expedientes = json.loads(row["expedientes"])
        if cl_expediente in expedientes:
            registro = dict(row)
            registro["expedientes"] = expedientes
            registro["nombre_envio"] = accesos_repo.nombre_o_rfc(registro["rfc_envio"])
            resultado.append(registro)
    return resultado


def obtener_envio_original(cl_expediente: int) -> dict | None:
    """
    El envío "nuevo" (no "recordatorio") de este expediente -- quién y cuándo
    se le mandó ORIGINALMENTE al proveedor. A diferencia de
    estatus_repo.obtener_detalle (que solo guarda el último cambio de
    estatus y por lo tanto cambia si el expediente sigue avanzando, ej. a
    "Seguimiento Proveedor" o "Finalizado"), este dato no se pierde ni se
    sobreescribe: queda fijo desde el momento en que se mandó, sin importar
    cuánto avance después. Usado por el corte (columna "Coordinador").
    """
    coincidencias = [r for r in listar_por_expediente(cl_expediente) if r["tipo"] == "nuevo"]
    if not coincidencias:
        return None
    # No debería haber más de un "nuevo" por expediente, pero por si acaso
    # queda alguno viejo de antes de esta regla, el más antiguo gana.
    return min(coincidencias, key=lambda r: r["fecha"])


def listar(cl_expediente: int | None = None, limite: int = 200) -> list[dict]:
    """
    Historial completo (panel de Administrador), más reciente primero.
    `cl_expediente` filtra a los correos que incluyeron ese expediente --
    útil cuando un proveedor dice que nunca se le notificó uno en concreto.
    """
    if cl_expediente is not None:
        return listar_por_expediente(cl_expediente)[:limite]

    with get_local_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM correos_enviados ORDER BY fecha DESC LIMIT ?", (limite,)
        ).fetchall()

    resultado = []
    for row in rows:
        registro = dict(row)
        registro["expedientes"] = json.loads(registro["expedientes"])
        registro["nombre_envio"] = accesos_repo.nombre_o_rfc(registro["rfc_envio"])
        resultado.append(registro)
    return resultado
