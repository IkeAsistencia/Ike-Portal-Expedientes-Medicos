"""
Padrón de proveedores del Directorio de Proveedores (tabla `proveedores`).

Los dos orígenes viven en la MISMA tabla:
  - 'catalogo': llegó en la carga de Excel ("Dentro de la red").
  - 'portal':   se dio de alta en el portal ("Fuera de la red").

Cada proveedor trae una `clave` que genera este portal (PRV-000001). Esa
clave es la que usan las citas y no cambia nunca: antes el catálogo dependía
de `cl_proveedor` y cada carga REEMPLAZABA el padrón completo, así que las
citas quedaban colgando. Ahora la carga es incremental (solo agrega lo que no
existe y actualiza lo que ya estaba) y `cl_proveedor` es opcional.

Un médico con VARIAS especialidades ocupa un renglón por especialidad: cada
uno con su clave y su agenda, porque la consulta y el horario cambian según
la especialidad.
"""

import unicodedata

from app.db.local_store import ahora_local, get_local_connection

ORIGEN_CATALOGO = "catalogo"
ORIGEN_PORTAL = "portal"

PREFIJO_CLAVE = "PRV-"
_LARGO_CONSECUTIVO = 6

# Campos que trae el Excel y que una carga posterior puede refrescar. La
# clave, la llave de identidad y el origen NO están aquí a propósito: son del
# portal, no del archivo.
_CAMPOS_DATOS = (
    "cl_proveedor", "nombre", "especialidad", "cedula", "rfc", "estado", "municipio",
    "calle_num_ext_int", "colonia", "codigo_postal", "consultorio", "telefono", "email",
    "horario", "costo_consulta", "convenio", "teleconsulta", "latitud", "longitud",
)


def _normalizar(valor) -> str:
    """Minúsculas, sin acentos y sin espacios de más -- para que "Dra. Laura
    Méndez" y "DRA.  LAURA MENDEZ" se reconozcan como la misma persona."""
    texto = str(valor or "").strip().lower()
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return " ".join(sin_acentos.split())


def llaves_candidatas(registro: dict) -> list[str]:
    """
    Con qué se puede reconocer a este médico, de la llave más confiable a la
    menos. La cédula es la buena (es única por profesionista); el nombre es
    el respaldo para los renglones del Excel que no la traen.

    La especialidad va en ambas porque el padrón guarda un renglón por
    especialidad.
    """
    especialidad = _normalizar(registro.get("especialidad"))
    candidatas = []
    cedula = _normalizar(registro.get("cedula"))
    if cedula:
        candidatas.append(f"ced:{cedula}|{especialidad}")
    nombre = _normalizar(registro.get("nombre"))
    if nombre:
        candidatas.append(f"nom:{nombre}|{especialidad}")
    return candidatas


def _siguiente_clave(conn) -> str:
    """
    Consecutivo propio del portal. Se calcula del máximo ya usado (no de un
    COUNT) para no repetir una clave si alguna vez se borra un renglón: una
    clave repetida reasignaría las citas de otro médico.
    """
    fila = conn.execute(
        f"SELECT MAX(CAST(SUBSTR(clave, {len(PREFIJO_CLAVE) + 1}) AS INTEGER)) AS maximo FROM proveedores"
    ).fetchone()
    siguiente = (fila["maximo"] or 0) + 1
    return PREFIJO_CLAVE + str(siguiente).zfill(_LARGO_CONSECUTIVO)


def _buscar_por_llaves(conn, candidatas: list[str]):
    for llave in candidatas:
        fila = conn.execute(
            "SELECT id, clave, origen, llave_identidad FROM proveedores WHERE llave_identidad = ?",
            (llave,),
        ).fetchone()
        if fila:
            return fila
    return None


def _insertar(conn, registro: dict, llave: str, origen: str, folio_alta: str | None) -> str:
    clave = _siguiente_clave(conn)
    columnas = ("clave", "llave_identidad", "origen", "folio_alta", "fecha_alta") + _CAMPOS_DATOS
    valores = {
        "clave": clave, "llave_identidad": llave, "origen": origen,
        "folio_alta": folio_alta, "fecha_alta": ahora_local(),
        **{c: registro.get(c) for c in _CAMPOS_DATOS},
    }
    valores["teleconsulta"] = 1 if valores.get("teleconsulta") else 0
    conn.execute(
        f"INSERT INTO proveedores ({', '.join(columnas)}) "
        f"VALUES ({', '.join(':' + c for c in columnas)})",
        valores,
    )
    return clave


def _actualizar(conn, fila, registro: dict, llave_fuerte: str, origen: str) -> None:
    """
    Refresca los datos conservando la clave (y por lo tanto las citas). Si el
    renglón se había dado de alta en el portal y ahora llega en la carga,
    pasa a origen='catalogo': el médico ya quedó "Dentro de la red" y deja de
    aparecer como alta del portal, pero sigue siendo el MISMO proveedor.
    """
    asignaciones = {c: registro.get(c) for c in _CAMPOS_DATOS}
    asignaciones["teleconsulta"] = 1 if asignaciones.get("teleconsulta") else 0
    # Si antes se le reconocía por nombre y ahora ya trae cédula, se queda con
    # la llave fuerte (la de la cédula) para las cargas siguientes.
    asignaciones["llave_identidad"] = llave_fuerte
    asignaciones["origen"] = origen
    asignaciones["fecha_actualizacion"] = ahora_local()
    asignaciones["id"] = fila["id"]
    sets = ", ".join(f"{c} = :{c}" for c in asignaciones if c != "id")
    conn.execute(f"UPDATE proveedores SET {sets} WHERE id = :id", asignaciones)


def cargar_padron(registros: list[dict], rfc_usuario: str) -> dict:
    """
    Carga INCREMENTAL del Excel (ya no reemplaza el padrón, decisión del
    usuario 2026-10-19):
      - el que no existe, se agrega con una clave nueva;
      - el que ya existe, se actualiza y CONSERVA su clave;
      - el que venía de un alta del portal, se absorbe (misma clave, ahora
        origen='catalogo').
    Todo en una sola transacción.
    """
    nuevos = actualizados = absorbidos = 0
    with get_local_connection() as conn:
        for registro in registros:
            candidatas = llaves_candidatas(registro)
            if not candidatas:
                continue
            fila = _buscar_por_llaves(conn, candidatas)
            if fila is None:
                _insertar(conn, registro, candidatas[0], ORIGEN_CATALOGO, None)
                nuevos += 1
                continue
            if fila["origen"] == ORIGEN_PORTAL:
                absorbidos += 1
            else:
                actualizados += 1
            _actualizar(conn, fila, registro, candidatas[0], ORIGEN_CATALOGO)

        conn.execute(
            "INSERT INTO proveedores_cargas (rfc, total_filas, nuevos, actualizados, absorbidos, fecha) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (rfc_usuario, len(registros), nuevos, actualizados, absorbidos, ahora_local()),
        )
        conn.commit()
    return {
        "total": len(registros), "nuevos": nuevos,
        "actualizados": actualizados, "absorbidos": absorbidos,
    }


def alta_desde_portal(datos: dict, folio: str) -> str:
    """
    Mete al padrón un médico aprobado desde "Alta de médico". Si ese médico
    YA estaba (porque ya venía en la carga), no se duplica: se devuelve la
    clave que ya tenía, para que sus citas sigan en el mismo lugar.
    """
    candidatas = llaves_candidatas(datos)
    with get_local_connection() as conn:
        fila = _buscar_por_llaves(conn, candidatas)
        if fila is not None:
            conn.commit()
            return fila["clave"]
        clave = _insertar(conn, datos, candidatas[0], ORIGEN_PORTAL, folio)
        conn.commit()
    return clave


def listar_padron() -> list[dict]:
    with get_local_connection() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM proveedores ORDER BY nombre").fetchall()]


def obtener_por_clave(clave: str) -> dict | None:
    with get_local_connection() as conn:
        fila = conn.execute("SELECT * FROM proveedores WHERE clave = ?", (clave,)).fetchone()
        return dict(fila) if fila else None


def contar_padron() -> int:
    with get_local_connection() as conn:
        return conn.execute("SELECT COUNT(*) FROM proveedores").fetchone()[0]


def contar_por_origen() -> dict:
    with get_local_connection() as conn:
        filas = conn.execute("SELECT origen, COUNT(*) AS total FROM proveedores GROUP BY origen").fetchall()
    return {f["origen"]: f["total"] for f in filas}


def obtener_ultima_carga() -> dict | None:
    with get_local_connection() as conn:
        fila = conn.execute(
            "SELECT rfc, total_filas, nuevos, actualizados, absorbidos, fecha "
            "FROM proveedores_cargas ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(fila) if fila else None
