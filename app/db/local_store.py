"""
Base de datos LOCAL (SQLite) para datos que, por decisión del usuario, NO
se persisten en SQL Server:

  - estatus_expediente: el estatus de negocio del expediente (Abierto,
    En Espera de Respuesta, Seguimiento Proveedor, Finalizado). Es un
    dato exclusivo de esta aplicación (ver app/schemas/expediente.py).
  - cuentas_configuradas: el grid de la pantalla "Configuración Cuentas".
  - alertas_proveedor_enviadas: registro de qué alertas del cron
    (jobs/validar_estatus_proveedor.py) ya se mandaron, para no
    reenviar la misma cada vez que corre.
  - usuarios_acceso: accesos por RFC (perfiles Administrador/Cabina/Proveedor).
  - comentarios_seguimiento: copia local de los comentarios de Proveedor.
  - comprobantes_pago: archivo de comprobante (expedientes Pago Anticipado).
  - seguimiento_fallidos: bitácora PROPIA del portal para los intentos
    de "Actualizar Seguimiento"/"Regresar a Proveedor" que no se pudieron
    insertar en dbo.Seguimiento por un error de base de datos.
  - proveedores: padrón ÚNICO del Directorio de Proveedores, con los dos
    orígenes juntos ('catalogo' = llegó en la carga de Excel, 'portal' =
    se dio de alta aquí). Cada proveedor tiene una clave propia del portal
    (PRV-000001) que NO cambia entre cargas, para que las citas sigan
    apuntando al mismo médico. Vive SOLO aquí, no existe en SQL Server.
  - citas_proveedor: citas agendadas desde el Directorio de Proveedores,
    ligadas a esa clave propia.
  - solicitudes_alta_medico: solicitudes de "Alta de médico" (pantalla
    "Proveedores" del Directorio de Proveedores) -- igual que el padrón,
    vive SOLO en este portal, nunca en SQL Server.
  - solicitudes_alta_documentos: archivos opcionales de esas solicitudes
    (constancia de situación fiscal y cédula profesional).

Este archivo vive junto al API (ver LOCAL_DB_PATH en .env) y no requiere
ningún permiso especial en SQL Server.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from app.config import get_settings


def ahora_local() -> str:
    """
    Fecha/hora local del servidor, para usar EXPLICITAMENTE en cada INSERT.
    OJO: datetime('now') de SQLite guarda en UTC, no en la hora local, y un
    DEFAULT de columna ('CREATE TABLE IF NOT EXISTS') no se actualiza en una
    tabla que ya existe -- por eso ya no se usa un DEFAULT para esto, cada
    repo pasa este valor a mano en su INSERT/UPDATE.
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS estatus_expediente (
    cl_expediente INTEGER PRIMARY KEY,
    estatus       TEXT NOT NULL DEFAULT 'Abierto',
    fecha_cambio  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    rfc_cambio    TEXT
);

CREATE TABLE IF NOT EXISTS cuentas_configuradas (
    cl_cuenta INTEGER PRIMARY KEY,
    nombre    TEXT NOT NULL
);

-- Color y prefijo por cuenta (módulo "Colores de Cuentas", solo Administrador).
CREATE TABLE IF NOT EXISTS cuentas_etiqueta (
    cl_cuenta        INTEGER PRIMARY KEY,
    nombre           TEXT NOT NULL,
    prefijo          TEXT NOT NULL DEFAULT '',
    color            TEXT NOT NULL,
    actualizado      TEXT,
    actualizado_por  TEXT
);

CREATE TABLE IF NOT EXISTS alertas_proveedor_enviadas (
    cl_expediente INTEGER NOT NULL,
    nivel         TEXT NOT NULL,      -- 'naranja' (>=8h) | 'rojo' (>=24h)
    fecha_envio   TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (cl_expediente, nivel)
);

-- Acceso por RFC (independiente de SISE). perfil: 1=Administrador, 2=Cabina, 3=Proveedor.
-- password_hash queda NULL hasta que la persona crea su contraseña la primera vez.
-- activo: 1=activo, 0=inactivado (baja lógica, ver migración más abajo — nunca se borra el registro).
CREATE TABLE IF NOT EXISTS usuarios_acceso (
    rfc           TEXT PRIMARY KEY,
    nombre        TEXT NOT NULL,
    perfil        INTEGER NOT NULL,
    password_hash TEXT,
    fecha_alta    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    entidad       TEXT,
    correo        TEXT
);

-- Copia local de cada comentario que se registra en el sistema central: los del Proveedor
-- (vía "Actualizar Bit?cora") y los del Coordinador de Cabina (vía "Regresar a
-- Proveedor"). "origen" distingue de quién es cada uno para mostrarlos en
-- secciones separadas en Seguimiento de expedientes.
CREATE TABLE IF NOT EXISTS comentarios_seguimiento (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    cl_expediente INTEGER NOT NULL,
    rfc           TEXT NOT NULL,
    comentario    TEXT NOT NULL,
    origen        TEXT NOT NULL DEFAULT 'proveedor',  -- 'proveedor' | 'cabina'
    fecha         TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- Comprobante de pago (solo expedientes "Pago Anticipado"). Se guarda el
-- archivo completo aquí mismo (no hay todavía un servidor con almacenamiento
-- de archivos aparte) -- máximo 5 MB, validado en el router.
CREATE TABLE IF NOT EXISTS comprobantes_pago (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    cl_expediente  INTEGER NOT NULL,
    rfc            TEXT NOT NULL,
    nombre_archivo TEXT NOT NULL,
    tipo_mime      TEXT NOT NULL,
    contenido      BLOB NOT NULL,
    fecha          TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- Bitácora PROPIA del portal (NUNCA dbo.Seguimiento ni comentarios_seguimiento)
-- para cuando el insert hacia el sistema central (dbo.Seguimiento, vía
-- dbo.ST_CP_RegistrarSeguimiento -- botón "Actualizar Seguimiento" / "Regresar
-- a Proveedor") falla por un error de base de datos: así no se pierde lo que
-- el usuario capturó, y se puede revisar/reintentar después. "nombre" es el
-- nombre de quien inició sesión en el portal (no RFC, no clUsrApp).
CREATE TABLE IF NOT EXISTS seguimiento_fallidos (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    cl_expediente INTEGER NOT NULL,
    observaciones TEXT NOT NULL,
    cl_usr_app    INTEGER,
    nombre        TEXT,
    error         TEXT,
    fecha         TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- "Corte" en Excel de expedientes enviados a proveedores (botón "Generar
-- corte", pantallas Expedientes/Expedientes PA). Se guarda el archivo ya
-- generado para que "descargar" y "confirmar y enviar" usen EXACTAMENTE
-- el mismo binario, y para dejar evidencia de qué se generó/envió y cuándo
-- (ej. si un proveedor luego dice que no fue notificado).
CREATE TABLE IF NOT EXISTS cortes_generados (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    rfc             TEXT NOT NULL,
    tipo_expediente TEXT NOT NULL,   -- 'normal' | 'anticipado'
    expedientes     TEXT NOT NULL,   -- JSON: lista de cl_expediente incluidos
    nombre_archivo  TEXT NOT NULL,
    contenido       BLOB NOT NULL,
    fecha_generado  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    enviado         INTEGER NOT NULL DEFAULT 0,
    destinatario    TEXT,
    fecha_enviado   TEXT
);

-- Si un expediente es de "pago anticipado" -- solo el Proveedor lo sabe, por
-- eso lo marca él desde Seguimiento de expediente. "bloqueado" se activa
-- solo (no se puede desmarcar) en cuanto Proveedor manda su primer
-- comentario por "Actualizar Bit?cora", para que no cambie después de que
-- Cabina ya empezó a revisarlo con ese valor.
CREATE TABLE IF NOT EXISTS expediente_pago_anticipado (
    cl_expediente INTEGER PRIMARY KEY,
    es_anticipado INTEGER NOT NULL DEFAULT 0,
    bloqueado     INTEGER NOT NULL DEFAULT 0,
    rfc           TEXT,
    fecha         TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- Historial de "Enviar correo a proveedores" -- para comprobar después qué
-- se mandó, a quién, cuándo y quién le dio clic (ej. si un proveedor dice
-- que nunca se le notificó). "simulado"=1 cuando no había SMTP configurado
-- (no se mandó un correo real, solo quedó registrado en el log de la app).
CREATE TABLE IF NOT EXISTS correos_enviados (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo          TEXT NOT NULL,     -- 'nuevo' | 'recordatorio'
    destinatario  TEXT NOT NULL,
    expedientes   TEXT NOT NULL,     -- JSON: lista de cl_expediente incluidos
    rfc_envio     TEXT NOT NULL,
    simulado      INTEGER NOT NULL DEFAULT 0,
    fecha         TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- Padrón ÚNICO de proveedores del Directorio de Proveedores: aquí conviven
-- los dos orígenes, y por eso las citas pueden apuntar siempre al mismo
-- renglón sin importar de dónde llegó el médico.
--   origen='catalogo' -> llegó en la carga de Excel ("Dentro de la red").
--   origen='portal'   -> se dio de alta en el portal ("Fuera de la red").
--
-- clave: identificador que GENERA ESTE PORTAL (PRV-000001). Es el que usan
-- las citas y NO cambia nunca -- antes se dependía de cl_proveedor, que ya
-- no es obligatorio (decisión del usuario, 2026-10-19).
--
-- llave_identidad: con qué se reconoce al MISMO médico entre una carga y
-- otra (ver proveedores_repo._llave_identidad). Incluye la especialidad a
-- propósito: un médico puede tener varias y cada una es un renglón distinto
-- del padrón, con su propia clave y su propia agenda.
--
-- La carga ya NO borra el padrón: solo agrega los que no existan y
-- actualiza los datos de los que ya estaban, conservándoles su clave.
CREATE TABLE IF NOT EXISTS proveedores (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    clave               TEXT NOT NULL UNIQUE,
    llave_identidad     TEXT NOT NULL UNIQUE,
    origen              TEXT NOT NULL DEFAULT 'catalogo',  -- 'catalogo' | 'portal'
    cl_proveedor        INTEGER,            -- referencia opcional del sistema central
    nombre              TEXT NOT NULL,
    especialidad        TEXT,               -- como vino en el Excel / el alta
    -- A qué especialidad de especialidades_catalogo corresponde ese texto.
    -- Es lo que hace contable el KPI; queda en NULL si el nombre no empató
    -- con el catálogo (la carga lo reporta, pero no rechaza el renglón).
    cl_especialidad     INTEGER,
    cedula              TEXT,
    rfc                 TEXT,
    estado              TEXT,
    municipio           TEXT,
    -- Domicilio DONDE DA LA CONSULTA (no el fiscal ni el particular).
    calle_num_ext_int   TEXT,
    colonia             TEXT,
    codigo_postal       TEXT,
    consultorio         TEXT,
    telefono            TEXT,
    email               TEXT,
    horario             TEXT,
    costo_consulta      TEXT,
    convenio            TEXT,
    teleconsulta        INTEGER NOT NULL DEFAULT 0,
    latitud             REAL,
    longitud            REAL,
    -- De dónde salieron esas coordenadas: NULL/'carga' = vinieron en el Excel
    -- del área (fuente autorizada, no se toca), 'clues' = las puso el
    -- enriquecimiento con el Catálogo CLUES de la Secretaría de Salud
    -- (ver scripts/enriquecer_coordenadas_clues.py). Importa poder
    -- distinguirlas para no pisar el dato bueno y para saber qué auditar.
    origen_coordenadas  TEXT,
    folio_alta          TEXT,               -- folio de la solicitud, si nació en el portal
    fecha_alta          TEXT NOT NULL,
    fecha_actualizacion TEXT
);

-- Catálogo de especialidades médicas, copiado del sistema central
-- (CatEspecialidadesMedicas.txt). Lo siembra especialidades_repo.sembrar()
-- en cada arranque, así que la fuente de verdad es el código, no esta tabla.
--
-- orden_kpi decide qué especialidades salen como tarjeta en el Directorio de
-- Proveedores y en qué orden; las que no entran en pantalla se ofrecen en un
-- combo. Viene con huecos, un valor repetido y dos NULL tal como lo manda el
-- catálogo central (ver el encabezado de especialidades_repo.py).
--
-- activo = 0 marca las que dejaron de venir en el catálogo: no se borran
-- para no dejar proveedores apuntando a una especialidad inexistente.
CREATE TABLE IF NOT EXISTS especialidades_catalogo (
    cl_especialidad INTEGER PRIMARY KEY,
    descripcion     TEXT NOT NULL,
    prioridad       INTEGER,
    orden_kpi       INTEGER,
    activo          INTEGER NOT NULL DEFAULT 1
);

-- Bitácora de cada carga del padrón. Como la carga ya es incremental, aquí
-- se guarda el desglose de qué hizo cada una (nuevos / actualizados /
-- absorbidos de un alta del portal).
CREATE TABLE IF NOT EXISTS proveedores_cargas (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    rfc          TEXT NOT NULL,
    total_filas  INTEGER NOT NULL,
    nuevos       INTEGER NOT NULL DEFAULT 0,
    actualizados INTEGER NOT NULL DEFAULT 0,
    absorbidos   INTEGER NOT NULL DEFAULT 0,
    fecha        TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- Citas agendadas desde el Directorio de Proveedores. Se amarran a
-- proveedores.clave (no al id interno ni a cl_proveedor) justamente para que
-- una carga de Excel no las deje huérfanas. El UNIQUE evita que dos
-- personas tomen el mismo horario del mismo médico.
CREATE TABLE IF NOT EXISTS citas_proveedor (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    folio           TEXT NOT NULL UNIQUE,
    clave_proveedor TEXT NOT NULL,
    fecha           TEXT NOT NULL,   -- YYYY-MM-DD
    hora            TEXT NOT NULL,   -- HH:MM
    paciente        TEXT,
    cl_expediente   INTEGER,         -- si se coordinó desde un expediente (Seguimiento)
    rfc_agendo      TEXT NOT NULL,
    estatus         TEXT NOT NULL DEFAULT 'Agendada',
    fecha_registro  TEXT NOT NULL,
    UNIQUE (clave_proveedor, fecha, hora)
);

-- Solicitudes de "Alta de médico" (pantalla "Proveedores" del Directorio
-- de Proveedores) -- queda SOLO en el portal, nunca se manda al sistema
-- central. Al aprobarse, el médico entra al padrón de arriba con
-- origen='portal' y su propia clave (clave_proveedor guarda cuál le tocó).
CREATE TABLE IF NOT EXISTS solicitudes_alta_medico (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    folio             TEXT NOT NULL UNIQUE,
    nombre            TEXT NOT NULL,
    especialidad      TEXT NOT NULL,
    cedula            TEXT NOT NULL,
    rfc               TEXT,
    estado            TEXT,
    municipio         TEXT,
    calle_num_ext_int TEXT,
    colonia           TEXT,
    codigo_postal     TEXT,
    telefono          TEXT,
    email             TEXT,
    estatus           TEXT NOT NULL DEFAULT 'En revisión',
    clave_proveedor   TEXT,
    rfc_solicito      TEXT NOT NULL,
    fecha             TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- Documentos OPCIONALES de una solicitud de alta (constancia de situación
-- fiscal y cédula profesional). Uno por tipo: subirlo otra vez lo reemplaza.
CREATE TABLE IF NOT EXISTS solicitudes_alta_documentos (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    folio          TEXT NOT NULL,
    tipo           TEXT NOT NULL,
    nombre_archivo TEXT NOT NULL,
    tipo_mime      TEXT NOT NULL,
    contenido      BLOB NOT NULL,
    rfc_subio      TEXT NOT NULL,
    fecha          TEXT NOT NULL,
    UNIQUE (folio, tipo)
);
"""


def _migrar_columnas_faltantes(conn: sqlite3.Connection) -> None:
    """
    ALTER TABLE para columnas agregadas después de la creación inicial de la
    base (CREATE TABLE IF NOT EXISTS no las agrega a una tabla ya existente).
    """
    columnas = {row["name"] for row in conn.execute("PRAGMA table_info(usuarios_acceso)")}
    if "activo" not in columnas:
        conn.execute("ALTER TABLE usuarios_acceso ADD COLUMN activo INTEGER NOT NULL DEFAULT 1")
    if "entidad" not in columnas:
        conn.execute("ALTER TABLE usuarios_acceso ADD COLUMN entidad TEXT")
    if "correo" not in columnas:
        conn.execute("ALTER TABLE usuarios_acceso ADD COLUMN correo TEXT")

    columnas_estatus = {row["name"] for row in conn.execute("PRAGMA table_info(estatus_expediente)")}
    if "rfc_cambio" not in columnas_estatus:
        conn.execute("ALTER TABLE estatus_expediente ADD COLUMN rfc_cambio TEXT")

    columnas_comentarios = {row["name"] for row in conn.execute("PRAGMA table_info(comentarios_seguimiento)")}
    if "origen" not in columnas_comentarios:
        conn.execute("ALTER TABLE comentarios_seguimiento ADD COLUMN origen TEXT NOT NULL DEFAULT 'proveedor'")

    columnas_solicitudes = {row["name"] for row in conn.execute("PRAGMA table_info(solicitudes_alta_medico)")}
    for columna in ("calle_num_ext_int", "colonia", "codigo_postal", "clave_proveedor"):
        if columna not in columnas_solicitudes:
            conn.execute(f"ALTER TABLE solicitudes_alta_medico ADD COLUMN {columna} TEXT")

    columnas_proveedores = {row["name"] for row in conn.execute("PRAGMA table_info(proveedores)")}
    if "cl_especialidad" not in columnas_proveedores:
        conn.execute("ALTER TABLE proveedores ADD COLUMN cl_especialidad INTEGER")
    if "origen_coordenadas" not in columnas_proveedores:
        conn.execute("ALTER TABLE proveedores ADD COLUMN origen_coordenadas TEXT")

    columnas_citas = {row["name"] for row in conn.execute("PRAGMA table_info(citas_proveedor)")}
    if "cl_expediente" not in columnas_citas:
        conn.execute("ALTER TABLE citas_proveedor ADD COLUMN cl_expediente INTEGER")
    # Un expediente tiene UNA sola cita activa (las canceladas no cuentan). Lo
    # garantiza la base, no solo una consulta previa: dos clics casi al mismo
    # tiempo no pueden dejar dos citas vivas para el mismo expediente.
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_cita_activa_por_expediente "
        "ON citas_proveedor (cl_expediente) WHERE cl_expediente IS NOT NULL AND estatus = 'Agendada'"
    )


def _migrar_tablas_renombradas(conn: sqlite3.Connection) -> None:
    """
    Renombres y bajas de tablas (el CREATE TABLE de arriba solo crea las que
    faltan, no toca las que ya existen con otro nombre).
    """
    def existe(tabla: str) -> bool:
        return conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabla,)
        ).fetchone() is not None

    # La bitácora de fallos se renombró al salir del proyecto el nombre del
    # sistema central (decisión del usuario, 2026-10-19). Se conserva lo ya
    # registrado: se copian los renglones a la tabla nueva y se tira la vieja.
    if existe("seguimiento_core_fallidos"):
        conn.execute(
            "INSERT INTO seguimiento_fallidos "
            "(id, cl_expediente, observaciones, cl_usr_app, nombre, error, fecha) "
            "SELECT id, cl_expediente, observaciones, cl_usr_app, nombre, error, fecha "
            "FROM seguimiento_core_fallidos"
        )
        conn.execute("DROP TABLE seguimiento_core_fallidos")

    # El padrón de proveedores cambió de layout (la dirección se separó y
    # cl_proveedor dejó de ser obligatorio). Lo cargado con el layout
    # anterior se descarta a propósito -- se vuelve a cargar con el nuevo
    # (instrucción del usuario, 2026-10-19).
    for tabla in ("proveedores_catalogo", "proveedores_catalogo_cargas"):
        if existe(tabla):
            conn.execute(f"DROP TABLE {tabla}")


def _migrar_llaves_de_identidad(conn: sqlite3.Connection) -> None:
    """
    Vuelve a armar proveedores.llave_identidad con la fórmula vigente.

    Hace falta porque la identidad cambió (2026-10-20): antes mandaba la
    cédula y ahora es nombre + especialidad + domicilio + teléfono. Sin esto,
    los renglones viejos conservarían una llave con el formato anterior, la
    siguiente carga no los reconocería y los volvería a insertar: el
    proveedor quedaría DUPLICADO y sus citas colgando de la clave vieja.
    """
    from app.repositories.proveedores_repo import llaves_candidatas

    filas = conn.execute("SELECT * FROM proveedores").fetchall()
    if not filas:
        return

    usadas: set[str] = set()
    cambios = []
    for fila in filas:
        candidatas = llaves_candidatas(dict(fila))
        # Un renglón sin nada con qué identificarse conserva su llave actual:
        # es preferible a dejarlo sin ninguna (la columna es NOT NULL/UNIQUE).
        nueva = candidatas[0] if candidatas else fila["llave_identidad"]
        # La columna es UNIQUE: si dos renglones distintos caen en la misma
        # llave (duplicados que ya estaban en el padrón), se desempata con la
        # clave, que es única por definición.
        if nueva in usadas:
            nueva = f"{nueva}#{fila['clave']}"
        usadas.add(nueva)
        if nueva != fila["llave_identidad"]:
            cambios.append((nueva, fila["id"]))

    if cambios:
        conn.executemany("UPDATE proveedores SET llave_identidad = ? WHERE id = ?", cambios)


def init_local_db() -> None:
    # El import va aquí dentro a propósito: especialidades_repo importa de
    # este módulo (get_local_connection), así que arriba sería circular.
    from app.repositories import especialidades_repo

    settings = get_settings()
    Path(settings.local_db_path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(settings.local_db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.executescript(_SCHEMA)
        _migrar_columnas_faltantes(conn)
        _migrar_tablas_renombradas(conn)
        # El catálogo de especialidades se resiembra en cada arranque (la
        # fuente de verdad es el código) y enseguida se vuelve a amarrar el
        # padrón: así un cambio de nombre en el catálogo se refleja en los
        # KPI sin tener que recargar el Excel.
        especialidades_repo.sembrar(conn)
        especialidades_repo.asignar_padron(conn)
        _migrar_llaves_de_identidad(conn)
        conn.commit()


@contextmanager
def get_local_connection():
    settings = get_settings()
    conn = sqlite3.connect(settings.local_db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
