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

-- Copia local de cada comentario que se registra en Core: los del Proveedor
-- (vía "Actualizar Core") y los del Coordinador de Cabina (vía "Regresar a
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
-- comentario por "Actualizar Core", para que no cambie después de que
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


def init_local_db() -> None:
    settings = get_settings()
    Path(settings.local_db_path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(settings.local_db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.executescript(_SCHEMA)
        _migrar_columnas_faltantes(conn)
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
