"""
Color y prefijo que el Administrador le pone a una cuenta (módulo "Colores
de Cuentas"). Es independiente de cuentas_configuradas (Configuración
Cuentas): aquí se puede etiquetar cualquier cuenta que exista en Core.

Con estos datos Expedientes pinta el renglón de ese color y muestra el
prefijo junto a la cuenta (ver expedientes_repo.listar_expedientes).
"""
import unicodedata

from app.db.local_store import ahora_local, get_local_connection
from app.repositories import accesos_repo


def _normalizar_nombre(nombre: str | None) -> str:
    """Sin acentos, en minúsculas y con espacios simples: para comparar el
    nombre de la cuenta que regresa el SP de expedientes con el guardado."""
    if not nombre:
        return ""
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", nombre) if unicodedata.category(c) != "Mn"
    )
    return " ".join(sin_acentos.casefold().split())


def listar() -> list[dict]:
    with get_local_connection() as conn:
        rows = conn.execute(
            "SELECT cl_cuenta, nombre, prefijo, color, actualizado, actualizado_por "
            "FROM cuentas_etiqueta ORDER BY nombre COLLATE NOCASE"
        ).fetchall()
        resultado = []
        for r in rows:
            d = dict(r)
            d["actualizado_por"] = accesos_repo.nombre_o_rfc(d["actualizado_por"]) if d["actualizado_por"] else None
            resultado.append(d)
        return resultado


def guardar(cl_cuenta: int, nombre: str, prefijo: str, color: str, rfc: str) -> bool:
    """Alta o cambio (una cuenta tiene una sola etiqueta). True si ya existía."""
    with get_local_connection() as conn:
        existia = conn.execute(
            "SELECT 1 FROM cuentas_etiqueta WHERE cl_cuenta = ?", (cl_cuenta,)
        ).fetchone() is not None
        conn.execute(
            "INSERT INTO cuentas_etiqueta (cl_cuenta, nombre, prefijo, color, actualizado, actualizado_por) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(cl_cuenta) DO UPDATE SET nombre = excluded.nombre, prefijo = excluded.prefijo, "
            "color = excluded.color, actualizado = excluded.actualizado, actualizado_por = excluded.actualizado_por",
            (cl_cuenta, nombre, prefijo, color, ahora_local(), rfc),
        )
        conn.commit()
        return existia


def eliminar(cl_cuenta: int) -> bool:
    with get_local_connection() as conn:
        cur = conn.execute("DELETE FROM cuentas_etiqueta WHERE cl_cuenta = ?", (cl_cuenta,))
        conn.commit()
        return cur.rowcount > 0


class BuscadorDeEtiquetas:
    """Se arma UNA vez por consulta de expedientes (una sola lectura de la
    base local) y resuelve cada fila sin volver a consultar."""

    def __init__(self) -> None:
        self._por_clave: dict[int, dict] = {}
        self._por_nombre: dict[str, dict] = {}
        for e in listar():
            datos = {"color": e["color"], "prefijo": e["prefijo"]}
            self._por_clave[e["cl_cuenta"]] = datos
            self._por_nombre[_normalizar_nombre(e["nombre"])] = datos

    def buscar(self, cl_cuenta: int | None, nombre: str | None) -> dict | None:
        # Si el SP de expedientes trae la clave de la cuenta se usa (más
        # seguro); si no, se compara por el nombre.
        if cl_cuenta is not None and cl_cuenta in self._por_clave:
            return self._por_clave[cl_cuenta]
        return self._por_nombre.get(_normalizar_nombre(nombre))
