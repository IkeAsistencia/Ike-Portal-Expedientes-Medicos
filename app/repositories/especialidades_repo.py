"""
Catálogo de especialidades médicas (tabla `especialidades_catalogo`).

De dónde sale: CatEspecialidadesMedicas.txt, el volcado del catálogo del
sistema central que entregó el usuario (2026-10-20). Las 38 filas viven aquí
abajo en SEMILLA, no se leen del .txt en tiempo de ejecución: así el portal
levanta igual aunque el archivo no esté, y cualquier cambio al catálogo queda
versionado en git junto al código que lo usa.

Para qué sirve:
  - Las tarjetas de KPI del Directorio de Proveedores (`ordenKPI` decide
    cuáles salen en pantalla y en qué orden; el resto va al combo).
  - El combo de especialidad del "Alta de médico".
  - Amarrar cada renglón del padrón a una especialidad del catálogo
    (proveedores.cl_especialidad), que es lo que hace contable el KPI.

OJO con `orden_kpi`, tal como vino en el archivo:
  - 2 especialidades lo traen en NULL (CIRUGIA GENERAL y CIRUGIA
    ONCOLOGICA): por decisión del usuario nunca salen en tarjeta, van al
    final del combo.
  - Hay huecos (falta el 6, 10 y 19) y el 15 está REPETIDO (ENDOCRINOLOGIA y
    UROLOGIA). Por eso el orden desempata siempre por cl_especialidad: sin
    ese desempate, dos especialidades con el mismo orden se podrían
    intercambiar de lugar entre una consulta y otra.
"""

import unicodedata

from app.db.local_store import get_local_connection

# (cl_especialidad, descripcion, prioridad, orden_kpi) -- igual que el
# archivo del sistema central, sin corregirle nada.
SEMILLA = [
    (6, "CARDIOLOGIA", 1, 4),
    (8, "CIRUGIA GENERAL", 1, None),
    (11, "CIRUGIA ONCOLOGICA", 1, None),
    (15, "DERMATOLOGIA", 1, 8),
    (16, "ENDOCRINOLOGIA", 1, 15),
    (17, "GASTROENTEROLOGIA", 1, 20),
    (19, "GINECOLOGIA Y OBSTETRICIA", 1, 5),
    (21, "MEDICINA FAMILIAR", 1, 21),
    (22, "MEDICINA FISICA Y REHABILITACION", 1, 22),
    (23, "MEDICINA GENERAL", 1, 1),
    (24, "MEDICINA INTERNA", 1, 17),
    (26, "NEUMOLOGIA", 1, 16),
    (27, "NEUROCIRUGIA", 1, 13),
    (28, "NEUROFISIOLOGIA", 1, 18),
    (29, "NEUROLOGIA", 1, 14),
    (30, "NUTRICION", 1, 3),
    (31, "ODONTOLOGIA INTEGRAL", 1, 12),
    (32, "OFTALMOLOGIA", 1, 11),
    (33, "ONCOLOGIA MEDICA", 1, 23),
    (35, "OTORRINOLARINGOLOGIA", 1, 24),
    (37, "PEDIATRIA", 1, 7),
    (38, "PSICOLOGIA", 1, 2),
    (39, "PSIQUIATRIA", 1, 25),
    (44, "TRAUMATOLOGIA Y ORTOPEDIA", 1, 9),
    (45, "UROLOGIA", 1, 15),
    (46, "ALERGOLOGIA E INMUNOLOGIA CLINICA", 1, 26),
    (57, "PROCTOLOGIA", 1, 27),
    (58, "TRAUMATOLOGIA Y ORTOPEDIA PEDIATRICA", 1, 28),
    (60, "OTORRINOLARINGOLOGO PEDIATRA", 1, 29),
    (66, "GABINETE", 1, 30),
    (68, "CLINICA", 1, 31),
    (69, "CLINICA DE FISIOTERAPIA Y REHABILITACION", 1, 32),
    (70, "OPTICA", 1, 33),
    (71, "RENTA DE EQUIPO", 1, 34),
    (74, "FARMACIA", 1, 35),
    (77, "VETERINARIO", 1, 36),
    (91, "REHABILITACION Y ORTOPEDIA", 1, 37),
    (94, "ACOMPAÑANTE", 1, 38),
]

# Cuántas tarjetas de KPI caben en la pantalla: 4 renglones de 4
# (instrucción del usuario, 2026-10-20). Las que no entran se ofrecen en el
# combo, con la misma funcionalidad.
MAXIMO_TARJETAS_KPI = 16

# Nombres con los que el padrón ya tenía datos ANTES de existir este
# catálogo: eran los del combo fijo del portal, más cortos que los del
# sistema central. Sin estos tres equivalentes, un proveedor cargado como
# "Traumatología" no contaría para "TRAUMATOLOGIA Y ORTOPEDIA" y su tarjeta
# diría 0 aunque sí haya a quién mostrar.
#
# Es una lista cerrada a propósito: solo cubre las variantes que de verdad
# generó el portal. Cualquier otro nombre que no empate se REPORTA en la
# carga (ver especialidades_no_reconocidas) en vez de adivinarle.
_EQUIVALENTES = {
    "TRAUMATOLOGIA": "TRAUMATOLOGIA Y ORTOPEDIA",
    "GINECOLOGIA": "GINECOLOGIA Y OBSTETRICIA",
    "ODONTOLOGIA": "ODONTOLOGIA INTEGRAL",
}


def normalizar(texto) -> str:
    """
    Mayúsculas, sin acentos y sin espacios de más: así "Cardiología",
    "CARDIOLOGIA" y "cardiologia " se reconocen como la misma.
    """
    base = str(texto or "").strip().upper()
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", base) if unicodedata.category(c) != "Mn"
    )
    return " ".join(sin_acentos.split())


def sembrar(conn) -> None:
    """
    Deja el catálogo igual a SEMILLA. Corre en cada arranque (ver
    init_local_db) y es idempotente: refresca descripción, prioridad y orden
    de las que ya estaban, para que un cambio de `ordenKPI` en el código se
    refleje sin tener que borrar la base a mano.

    No borra las que ya no vengan en SEMILLA: si alguna desapareciera del
    catálogo central, los proveedores que la tengan asignada seguirían
    apuntando a algo existente. Se marca como inactiva, que es lo que la
    saca de las tarjetas y del combo.
    """
    claves = {fila[0] for fila in SEMILLA}
    conn.executemany(
        """
        INSERT INTO especialidades_catalogo
            (cl_especialidad, descripcion, prioridad, orden_kpi, activo)
        VALUES (?, ?, ?, ?, 1)
        ON CONFLICT (cl_especialidad) DO UPDATE SET
            descripcion = excluded.descripcion,
            prioridad   = excluded.prioridad,
            orden_kpi   = excluded.orden_kpi,
            activo      = 1
        """,
        SEMILLA,
    )
    if claves:
        marcadores = ", ".join("?" for _ in claves)
        conn.execute(
            f"UPDATE especialidades_catalogo SET activo = 0 "
            f"WHERE cl_especialidad NOT IN ({marcadores})",
            tuple(claves),
        )


# El orden de los KPI, en SQL: primero las que traen `orden_kpi`, al final
# las que lo traen en NULL, y siempre desempatando por clave.
_ORDEN_KPI = (
    "ORDER BY CASE WHEN orden_kpi IS NULL THEN 1 ELSE 0 END, orden_kpi, cl_especialidad"
)


def listar(solo_activas: bool = True) -> list[dict]:
    """El catálogo en el orden de los KPI (ver _ORDEN_KPI)."""
    filtro = "WHERE activo = 1" if solo_activas else ""
    with get_local_connection() as conn:
        filas = conn.execute(
            f"SELECT cl_especialidad, descripcion, prioridad, orden_kpi "
            f"FROM especialidades_catalogo {filtro} {_ORDEN_KPI}"
        ).fetchall()
    return [dict(f) for f in filas]


def mapa_por_nombre(conn) -> dict[str, int]:
    """Nombre normalizado (y sus equivalentes) -> cl_especialidad."""
    filas = conn.execute(
        "SELECT cl_especialidad, descripcion FROM especialidades_catalogo WHERE activo = 1"
    ).fetchall()
    mapa = {normalizar(f["descripcion"]): f["cl_especialidad"] for f in filas}
    for alias, oficial in _EQUIVALENTES.items():
        clave = mapa.get(normalizar(oficial))
        if clave is not None:
            mapa.setdefault(normalizar(alias), clave)
    return mapa


def resolver(texto) -> int | None:
    """
    A qué especialidad del catálogo corresponde ese texto libre del Excel o
    del alta. None si no empata con ninguna -- la carga NO se rechaza por
    eso (decisión del usuario, 2026-10-20): el proveedor entra igual, solo
    que no suma a ninguna tarjeta hasta que se corrija el nombre.
    """
    if not normalizar(texto):
        return None
    with get_local_connection() as conn:
        return mapa_por_nombre(conn).get(normalizar(texto))


def resolver_muchas(textos) -> dict[str, int | None]:
    """Igual que resolver() pero de un golpe, para no abrir una conexión por
    renglón del Excel. La llave del resultado es el texto normalizado."""
    with get_local_connection() as conn:
        mapa = mapa_por_nombre(conn)
    return {normalizar(t): mapa.get(normalizar(t)) for t in textos if normalizar(t)}


def especialidades_no_reconocidas(textos) -> list[str]:
    """
    Los nombres que no empataron con el catálogo, sin repetir y conservando
    cómo venían escritos (para poder mostrárselos a quien cargó el archivo).
    """
    with get_local_connection() as conn:
        mapa = mapa_por_nombre(conn)
    vistos: set[str] = set()
    fuera: list[str] = []
    for texto in textos:
        normalizado = normalizar(texto)
        if not normalizado or normalizado in mapa or normalizado in vistos:
            continue
        vistos.add(normalizado)
        fuera.append(str(texto).strip())
    return fuera


def kpis() -> list[dict]:
    """
    El catálogo con el conteo REAL del padrón para cada especialidad, que es
    lo que pintan las tarjetas: cuántos proveedores hay dentro de la red
    (origen='catalogo', ya contratados) y cuántos fuera (origen='portal',
    dados de alta aquí) -- formato que pidió el usuario (2026-10-20).

    El conteo se amarra por proveedores.cl_especialidad, no por el texto: un
    renglón cuyo nombre no empató con el catálogo no suma en ningún lado (y
    por eso la carga lo reporta).
    """
    with get_local_connection() as conn:
        filas = conn.execute(
            f"""
            SELECT
                c.cl_especialidad,
                c.descripcion,
                c.prioridad,
                c.orden_kpi,
                COALESCE(SUM(CASE WHEN p.origen = 'catalogo' THEN 1 ELSE 0 END), 0) AS dentro_de_red,
                COALESCE(SUM(CASE WHEN p.origen = 'portal'   THEN 1 ELSE 0 END), 0) AS fuera_de_red,
                COUNT(p.id) AS total_proveedores,
                COUNT(DISTINCT CASE
                    WHEN TRIM(COALESCE(p.municipio, '')) <> ''
                    THEN UPPER(TRIM(p.municipio)) || '|' || UPPER(TRIM(COALESCE(p.estado, '')))
                END) AS zonas
            FROM especialidades_catalogo c
            LEFT JOIN proveedores p ON p.cl_especialidad = c.cl_especialidad
            WHERE c.activo = 1
            GROUP BY c.cl_especialidad, c.descripcion, c.prioridad, c.orden_kpi
            {_ORDEN_KPI.replace("orden_kpi", "c.orden_kpi").replace("cl_especialidad", "c.cl_especialidad")}
            """
        ).fetchall()
    return [dict(f) for f in filas]


def asignar_padron(conn) -> int:
    """
    Vuelve a resolver proveedores.cl_especialidad para TODO el padrón a
    partir del texto que cada renglón trae en `especialidad`.

    Hace falta porque el padrón existía antes que este catálogo (sus
    renglones tenían la especialidad solo como texto) y porque un cambio en
    el catálogo puede hacer que un nombre que antes no empataba ahora sí.
    Corre en el arranque, junto con la siembra; no hace commit (lo hace quien
    la llama, para que catálogo y padrón queden en la misma transacción).

    Devuelve cuántos renglones quedaron amarrados a una especialidad.
    """
    mapa = mapa_por_nombre(conn)
    filas = conn.execute("SELECT id, especialidad FROM proveedores").fetchall()
    cambios = [(mapa.get(normalizar(f["especialidad"])), f["id"]) for f in filas]
    conn.executemany("UPDATE proveedores SET cl_especialidad = ? WHERE id = ?", cambios)
    return sum(1 for clave, _ in cambios if clave is not None)


def reasignar_padron() -> int:
    """asignar_padron() con su propia conexión y su commit."""
    with get_local_connection() as conn:
        amarrados = asignar_padron(conn)
        conn.commit()
    return amarrados
