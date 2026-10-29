"""
Padrón de proveedores del Directorio de Proveedores (tabla `proveedores`).

Los tres orígenes viven en la MISMA tabla:
  - 'catalogo': llegó en la carga de Excel, hoja "Padrón de proveedores"
    ("Dentro de la red").
  - 'apoyo':    llegó en la carga de Excel, hoja "Proveedores red de apoyo"
    ("Red de apoyo" -- también con convenio, pero se identifica aparte
    porque el área los entrega en una hoja distinta y con menos datos).
  - 'portal':   se dio de alta en el portal ("Fuera de la red").

Cada proveedor trae una `clave` que genera este portal (PRV-000001). Esa
clave es la que usan las citas y no cambia nunca: antes el catálogo dependía
de `cl_proveedor` y cada carga REEMPLAZABA el padrón completo, así que las
citas quedaban colgando. Ahora la carga es incremental (solo agrega lo que no
existe y actualiza lo que ya estaba) y `cl_proveedor` es opcional.

Un médico con VARIAS especialidades ocupa un renglón por especialidad: cada
uno con su clave y su agenda, porque la consulta y el horario cambian según
la especialidad. Lo mismo con las SUCURSALES: el padrón real trae cadenas
("OPTICAS DEVLYN" en 68 domicilios, "FARMACOS ESPECIALIZADOS" en 38), y cada
domicilio es donde se da la consulta, así que es un renglón aparte.
"""

import unicodedata

from app.db.local_store import ahora_local, get_local_connection
from app.repositories import especialidades_repo

ORIGEN_CATALOGO = "catalogo"
ORIGEN_APOYO = "apoyo"
ORIGEN_PORTAL = "portal"

PREFIJO_CLAVE = "PRV-"
_LARGO_CONSECUTIVO = 6

# De dónde salieron las coordenadas de un proveedor (columna
# origen_coordenadas): el Excel del área es la fuente autorizada y no se pisa;
# 'clues' marca las que puso el enriquecimiento con el Catálogo CLUES.
ORIGEN_COORDENADAS_CARGA = "carga"
ORIGEN_COORDENADAS_CLUES = "clues"

# Campos que trae el Excel y que una carga posterior puede refrescar. La
# clave, la llave de identidad y el origen NO están aquí a propósito: son del
# portal, no del archivo.
_CAMPOS_DATOS = (
    "cl_proveedor", "nombre", "especialidad", "cl_especialidad",
    "cedula", "rfc", "estado", "municipio",
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


# Qué compone la identidad de un renglón del padrón. El orden es fijo: la
# llave se guarda armada en llave_identidad y se vuelve a armar igual en cada
# carga para reconocer al mismo proveedor.
_CAMPOS_IDENTIDAD = (
    "nombre", "especialidad",
    # Domicilio DONDE DA LA CONSULTA: es lo que distingue una sucursal de
    # otra. Sin esto, las 662 filas del padrón real colapsan a 480.
    "calle_num_ext_int", "colonia", "codigo_postal", "municipio", "estado",
    # Desempata las dos sucursales que comparten domicilio exacto.
    "telefono",
)


def llaves_candidatas(registro: dict) -> list[str]:
    """
    Con qué se reconoce a este renglón entre una carga y otra.

    Es nombre + especialidad + domicilio de consulta + teléfono (decisión del
    usuario, 2026-10-20, medida contra el padrón real de 662 filas: así entran
    las 662; con menos campos se fusionan sucursales distintas).

    La CÉDULA NO entra: en el padrón que entrega el área viene un mismo valor
    de relleno repetido en las 662 filas, así que usarla fusionaba todo lo que
    compartiera especialidad -- de 662 proveedores quedaban 38. Se sigue
    guardando como dato del proveedor, nada más que no identifica.

    Devuelve una lista (y no una sola llave) porque `cargar_padron` espera
    varias candidatas; aquí siempre es una. Vacía si el renglón no trae NADA
    con qué distinguirlo, para no fusionarlo con otro igual de vacío.
    """
    partes = [_normalizar(registro.get(campo)) for campo in _CAMPOS_IDENTIDAD]
    if not any(partes):
        return []
    return ["prv:" + "|".join(partes)]


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


def _altas_del_portal_por_nombre(conn) -> dict:
    """
    Las altas hechas en el portal, indexadas por nombre + especialidad.

    Sirve de RED DE SEGURIDAD al absorber: el Excel del área casi nunca trae
    el domicilio exactamente igual al que capturó el médico al darse de alta,
    y sin esto la carga lo insertaría como un proveedor NUEVO -- quedaría
    duplicado y sus citas colgando de la clave anterior.

    Solo se buscan las de origen 'portal' (son pocas y capturadas a mano). No
    se usa este atajo contra las que vinieron del Excel, porque ahí sí hay
    cadenas con el mismo nombre y especialidad en decenas de domicilios
    ("OPTICAS DEVLYN" aparece 68 veces) y se fusionarían entre ellas.
    """
    filas = conn.execute(
        "SELECT id, clave, origen, llave_identidad, nombre, especialidad "
        "FROM proveedores WHERE origen = ?",
        (ORIGEN_PORTAL,),
    ).fetchall()
    return {
        (_normalizar(f["nombre"]), _normalizar(f["especialidad"])): f
        for f in filas
        if _normalizar(f["nombre"])
    }


def _insertar(conn, registro: dict, llave: str, origen: str, folio_alta: str | None) -> str:
    clave = _siguiente_clave(conn)
    columnas = (
        "clave", "llave_identidad", "origen", "folio_alta", "fecha_alta", "origen_coordenadas",
    ) + _CAMPOS_DATOS
    valores = {
        "clave": clave, "llave_identidad": llave, "origen": origen,
        "folio_alta": folio_alta, "fecha_alta": ahora_local(),
        **{c: registro.get(c) for c in _CAMPOS_DATOS},
    }
    valores["teleconsulta"] = 1 if valores.get("teleconsulta") else 0
    # Si el alta trae coordenadas, quedan marcadas como venidas del archivo
    # (la fuente autorizada), para distinguirlas de las que ponga CLUES.
    valores["origen_coordenadas"] = (
        ORIGEN_COORDENADAS_CARGA
        if valores.get("latitud") is not None and valores.get("longitud") is not None
        else None
    )
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
    pasa al origen de la hoja que lo trajo ('catalogo' o 'apoyo'): el médico
    ya quedó dentro de la red y deja de aparecer como alta del portal, pero
    sigue siendo el MISMO proveedor.
    """
    asignaciones = {c: registro.get(c) for c in _CAMPOS_DATOS}
    asignaciones["teleconsulta"] = 1 if asignaciones.get("teleconsulta") else 0
    # Las coordenadas NO se borran con una carga que venga sin ellas: el Excel
    # del área las entrega vacías, así que sobrescribir con NULL tiraría lo que
    # ya se hubiera enriquecido con CLUES (ver asignar_coordenadas). Si el
    # archivo SÍ trae coordenadas, esas mandan y se marcan como 'carga'.
    if asignaciones.get("latitud") is None or asignaciones.get("longitud") is None:
        asignaciones.pop("latitud", None)
        asignaciones.pop("longitud", None)
    else:
        asignaciones["origen_coordenadas"] = ORIGEN_COORDENADAS_CARGA
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

    Una especialidad que el catálogo todavía no tiene se da de alta sola
    (ver especialidades_repo.agregar, instrucción del usuario 2026-10-28):
    ya ningún renglón se queda sin `cl_especialidad` por un nombre que el
    catálogo no traía todavía.
    """
    nuevos = actualizados = absorbidos = 0
    with get_local_connection() as conn:
        # El mapa del catálogo se arma UNA vez, con esta misma conexión: abrir
        # otra por renglón chocaría con el candado de escritura de la carga.
        # Se va completando aquí mismo con lo que agregar() dé de alta, para
        # no repetir la especialidad si varios renglones la traen igual.
        mapa_especialidades = especialidades_repo.mapa_por_nombre(conn)
        altas_del_portal = _altas_del_portal_por_nombre(conn)
        for registro in registros:
            # De qué hoja del Excel salió ('catalogo' o 'apoyo', ver
            # proveedores_excel_service.leer_catalogo_excel) -- a falta de
            # dato se asume 'catalogo' (quien llame a esta función sin
            # marcarlo, ver alta_desde_portal, nunca es la hoja de apoyo).
            origen_registro = registro.get("origen") or ORIGEN_CATALOGO
            especialidad_normalizada = especialidades_repo.normalizar(registro.get("especialidad"))
            cl_especialidad = mapa_especialidades.get(especialidad_normalizada)
            if cl_especialidad is None and especialidad_normalizada:
                cl_especialidad = especialidades_repo.agregar(conn, registro.get("especialidad"))
                mapa_especialidades[especialidad_normalizada] = cl_especialidad
            registro = {**registro, "cl_especialidad": cl_especialidad}
            candidatas = llaves_candidatas(registro)
            if not candidatas:
                continue
            fila = _buscar_por_llaves(conn, candidatas)
            if fila is None:
                # Antes de darlo por nuevo: ¿será un alta del portal que el
                # Excel trae con otro domicilio? (ver _altas_del_portal_por_nombre)
                senas = (
                    _normalizar(registro.get("nombre")),
                    _normalizar(registro.get("especialidad")),
                )
                # Se saca del mapa para que dos renglones del Excel no
                # absorban al mismo proveedor del portal.
                fila = altas_del_portal.pop(senas, None)
            if fila is None:
                _insertar(conn, registro, candidatas[0], origen_registro, None)
                nuevos += 1
                continue
            if fila["origen"] == ORIGEN_PORTAL:
                absorbidos += 1
            else:
                actualizados += 1
            _actualizar(conn, fila, registro, candidatas[0], origen_registro)

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
        datos = {
            **datos,
            "cl_especialidad": especialidades_repo.mapa_por_nombre(conn).get(
                especialidades_repo.normalizar(datos.get("especialidad"))
            ),
        }
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


def contar_coordenadas() -> dict:
    """Cuántos proveedores se pueden ubicar en el mapa y de dónde salió su
    ubicación (ver la columna origen_coordenadas)."""
    with get_local_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM proveedores").fetchone()[0]
        con = conn.execute(
            "SELECT COUNT(*) FROM proveedores WHERE latitud IS NOT NULL AND longitud IS NOT NULL"
        ).fetchone()[0]
        # OJO con el nombre del alias: la tabla YA tiene una columna `origen`
        # ('catalogo'/'portal'), así que un alias llamado igual haría que
        # SQLite agrupara por esa columna en vez de por la del SELECT.
        filas = conn.execute(
            "SELECT COALESCE(origen_coordenadas, ?) AS fuente_coordenadas, COUNT(*) AS total "
            "FROM proveedores WHERE latitud IS NOT NULL AND longitud IS NOT NULL "
            "GROUP BY fuente_coordenadas",
            (ORIGEN_COORDENADAS_CARGA,),
        ).fetchall()
    return {
        "total": total,
        "con_coordenadas": con,
        "sin_coordenadas": total - con,
        "por_origen": {f["fuente_coordenadas"]: f["total"] for f in filas},
    }


def asignar_coordenadas(asignaciones, origen: str = ORIGEN_COORDENADAS_CLUES) -> int:
    """
    Pone latitud/longitud a los proveedores de `asignaciones`
    [{clave, latitud, longitud}, ...] y marca de dónde salieron.

    El UPDATE exige que las coordenadas sigan vacías: si entre que se calculó
    el plan y se aplica llegó una carga del área con las suyas, gana la del
    Excel, que es la fuente autorizada. Devuelve cuántos renglones cambiaron.
    """
    datos = [
        (a["latitud"], a["longitud"], origen, a["clave"])
        for a in asignaciones
        if a.get("clave") and a.get("latitud") is not None and a.get("longitud") is not None
    ]
    if not datos:
        return 0
    with get_local_connection() as conn:
        cursor = conn.executemany(
            "UPDATE proveedores SET latitud = ?, longitud = ?, origen_coordenadas = ?, "
            "fecha_actualizacion = datetime('now','localtime') "
            "WHERE clave = ? AND latitud IS NULL AND longitud IS NULL",
            datos,
        )
        cambiados = cursor.rowcount
        conn.commit()
    return cambiados


def obtener_ultima_carga() -> dict | None:
    with get_local_connection() as conn:
        fila = conn.execute(
            "SELECT rfc, total_filas, nuevos, actualizados, absorbidos, fecha "
            "FROM proveedores_cargas ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(fila) if fila else None
