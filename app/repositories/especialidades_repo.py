"""
Catálogo de especialidades médicas (tabla `especialidades_catalogo`).

De dónde sale: CatEspecialidadesMedicas.txt, el volcado del catálogo del
sistema central que entregó el usuario (2026-10-20) -- las primeras 38 filas
de SEMILLA, con su `cl_especialidad` oficial. No se leen del .txt en tiempo
de ejecución: así el portal levanta igual aunque el archivo no esté, y
cualquier cambio al catálogo queda versionado en git junto al código que lo
usa.

A esas 38 se le agregaron (2026-10-28) las especialidades que trae la
columna "Especialidad" del Excel real del padrón ("Lay out red médica.xlsx",
hojas "Padrón de proveedores" y "Proveedores red de apoyo") y que no
empataban con ninguna de las 38 ni con sus equivalentes (ver
_EQUIVALENTES) -- SIN eso, esos proveedores se cargaban pero no sumaban a
ninguna tarjeta de KPI (quedaban "fuera del catálogo"). Van en una sección
aparte de SEMILLA, con `cl_especialidad` >= 1000.

Desde esa misma fecha, una carga de Excel que traiga una especialidad que
TODAVÍA no esté en el catálogo ya no la deja fuera: `agregar()` la da de
alta sola, con una clave >= 2000 (ver `cargar_padron`). Tres rangos de
`cl_especialidad`, para no chocar nunca entre ellos ni con uno que el
sistema central use más adelante:
  - < 1000:  catálogo oficial del sistema central (SEMILLA).
  - 1000-1999: agregadas a mano en SEMILLA al revisar un archivo real --
    quedan versionadas en git y `sembrar()` las administra igual que a las
    oficiales (se desactivan si algún día se les quita de SEMILLA).
  - >= 2000: aprendidas EN RUNTIME por una carga (`agregar()`). Viven solo en
    la base, `sembrar()` no las toca (ni las resiembra ni las desactiva):
    perderlas requeriría borrar el renglón a mano.

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

    # ---- Agregadas del Excel real del padrón (2026-10-28), no vienen del
    # catálogo central -- ver nota de arriba. Sin prioridad ni orden_kpi
    # (van al combo, no desplazan ninguna tarjeta ya asignada).
    (1000, "ANESTESIOLOGIA", None, None),
    # Estas 3 sí llevan orden_kpi (decisión del usuario, 2026-10-28): son las
    # especialidades más frecuentes del Excel real que quedaban sin tarjeta
    # (NEFROLOGIA 58 proveedores, GERIATRIA 46, ANGIOLOGIA 48). El 18 empata
    # con NEUROFISIOLOGIA (cl 28): el desempate por clave las deja justo en
    # las posiciones 18-20 de MAXIMO_TARJETAS_KPI, sin mover a ninguna de las
    # 16 que ya tenían tarjeta.
    (1001, "ANGIOLOGIA", None, 18),
    (1002, "ARTROSCOPIA", None, None),
    (1003, "AUDIOLOGIA", None, None),
    (1004, "BARIATRIA", None, None),
    (1005, "CIRUGIA DE TORAX", None, None),
    (1006, "CIRUGIA GASTROENTEROLOGICA", None, None),
    (1007, "CIRUGIA INTERNA", None, None),
    (1008, "CIRUGIA MAXILO FACIAL", None, None),
    (1010, "CIRUGIA PEDIATRICA", None, None),
    (1011, "CIRUGIA PLASTICA", None, None),
    (1012, "COLOPROCTOLOGIA", None, None),
    (1013, "GERIATRIA", None, 18),
    (1014, "GERONTOLOGIA", None, None),
    (1015, "HEMATOLOGIA", None, None),
    (1016, "INFECTOLOGIA", None, None),
    (1017, "LAPAROSCOPIA Y ENDOSCOPIA", None, None),
    (1018, "NEFROLOGIA", None, 18),
    (1019, "NEONATOLOGIA", None, None),
    (1020, "ODONTOPEDIATRIA", None, None),
    (1021, "OPTOMETRISTA Y OPTICA", None, None),
    (1022, "PATOLOGIA", None, None),
    (1023, "PODOLOGIA", None, None),
    (1024, "PSICOTERAPIA", None, None),
    (1025, "REUMATOLOGIA", None, None),
]

# Cuántas tarjetas de KPI caben en la pantalla: 5 renglones de 4 (ampliado de
# 4x4 el 2026-10-28 para darle tarjeta a NEFROLOGIA/GERIATRIA/ANGIOLOGIA sin
# sacar a ninguna de las 16 que ya tenían -- ver SEMILLA). Las que no entran
# se ofrecen en el combo, con la misma funcionalidad.
MAXIMO_TARJETAS_KPI = 20

# Nombres con los que el padrón ya tenía datos ANTES de existir este
# catálogo: eran los del combo fijo del portal, más cortos que los del
# sistema central. Sin estos tres equivalentes, un proveedor cargado como
# "Traumatología" no contaría para "TRAUMATOLOGIA Y ORTOPEDIA" y su tarjeta
# diría 0 aunque sí haya a quién mostrar.
#
# Es una lista cerrada a propósito: solo cubre variantes YA CONFIRMADAS de
# una especialidad que ya existe. Cualquier otro nombre que no empate se da
# de alta como especialidad NUEVA en la carga (ver agregar() y
# proveedores_repo.cargar_padron) en vez de adivinarle un alias.
_EQUIVALENTES = {
    "TRAUMATOLOGIA": "TRAUMATOLOGIA Y ORTOPEDIA",
    "GINECOLOGIA": "GINECOLOGIA Y OBSTETRICIA",
    "ODONTOLOGIA": "ODONTOLOGIA INTEGRAL",
    # Mismo criterio, agregados al revisar el Excel real del padrón
    # (2026-10-28): el nombre corto que trae el archivo es un subconjunto
    # exacto de palabras del nombre oficial, así que es la misma
    # especialidad sin la calificación final.
    "ALERGOLOGIA E INMUNOLOGIA": "ALERGOLOGIA E INMUNOLOGIA CLINICA",
    "ONCOLOGIA": "ONCOLOGIA MEDICA",
    # Confirmado por el usuario (2026-10-28): error de dedo en el Excel por
    # "CIRUGIA ONCOLOGICA" (cl 11).
    "CIRUGIA ONCOLICA": "CIRUGIA ONCOLOGICA",
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


# A partir de aquí las claves que se inventa agregar() en tiempo de carga
# (ver nota del encabezado del módulo).
_INICIO_RUNTIME = 2000


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

    Las aprendidas en runtime por una carga (ver agregar(), cl_especialidad
    >= 2000) NO se tocan aquí: no viven en SEMILLA, así que si se incluyeran
    en el "no vengan en SEMILLA" de arriba, cada reinicio del portal las
    desactivaría.
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
            f"WHERE cl_especialidad NOT IN ({marcadores}) AND cl_especialidad < {_INICIO_RUNTIME}",
            tuple(claves),
        )


def agregar(conn, descripcion: str) -> int:
    """
    Da de alta una especialidad que no estaba en el catálogo, con una clave
    nueva (>= _INICIO_RUNTIME) y sin prioridad ni orden_kpi (entra al combo,
    no desplaza ninguna tarjeta ya asignada). Pensada para `cargar_padron`:
    un renglón del Excel con una especialidad desconocida ya no se queda
    sin `cl_especialidad` -- se le da de alta al catálogo en el momento.
    """
    siguiente = conn.execute(
        "SELECT COALESCE(MAX(cl_especialidad), ?) + 1 FROM especialidades_catalogo "
        "WHERE cl_especialidad >= ?",
        (_INICIO_RUNTIME - 1, _INICIO_RUNTIME),
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO especialidades_catalogo (cl_especialidad, descripcion, prioridad, orden_kpi, activo) "
        "VALUES (?, ?, NULL, NULL, 1)",
        (siguiente, str(descripcion).strip()),
    )
    return siguiente


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
    (origen='catalogo'), cuántos en la red de apoyo (origen='apoyo') y
    cuántos fuera (origen='portal', dados de alta aquí) -- formato que pidió
    el usuario (2026-10-20, ampliado 2026-10-28 para distinguir la red de
    apoyo).

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
                COALESCE(SUM(CASE WHEN p.origen = 'apoyo'    THEN 1 ELSE 0 END), 0) AS red_de_apoyo,
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
