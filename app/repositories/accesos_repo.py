"""
Acceso por RFC, independiente de SISE (ver decisión del equipo: no se
toca ni se depende de SISE para nada de esto). Vive entera en la base
local (SQLite, ver app/db/local_store.py).

Perfiles:
    1 = Administrador (altas/bajas de usuarios y cuentas)
    2 = Cabina
    3 = Proveedor

Contraseñas: se guardan con hash + salt (PBKDF2-SHA256), nunca en
texto plano. La persona crea su propia contraseña la primera vez que
usa su RFC (ver /auth/rfc/crear-password).
"""

import hashlib
import hmac
import os

from app.db.local_store import ahora_local, get_local_connection

PERFIL_ADMINISTRADOR = 1
PERFIL_CABINA = 2
PERFIL_PROVEEDOR = 3

NOMBRES_PERFIL = {
    PERFIL_ADMINISTRADOR: "Administrador",
    PERFIL_CABINA: "Cabina",
    PERFIL_PROVEEDOR: "Proveedor",
}

# Entidad y correo solo aplican al perfil Proveedor -- a los demás perfiles
# se les guarda este valor fijo en vez de dejarlo vacío/NULL en la grilla.
SIN_APLICA = "NA"

# Catálogo fijo de las 32 entidades federativas de México. Se le asigna una
# a cada usuario con perfil Proveedor (para su atención) -- Cabina y
# Administrador no la usan.
ENTIDADES_MEXICO = [
    "Aguascalientes", "Baja California", "Baja California Sur", "Campeche",
    "Chiapas", "Chihuahua", "Ciudad de México", "Coahuila", "Colima",
    "Durango", "Estado de México", "Guanajuato", "Guerrero", "Hidalgo",
    "Jalisco", "Michoacán", "Morelos", "Nayarit", "Nuevo León", "Oaxaca",
    "Puebla", "Querétaro", "Quintana Roo", "San Luis Potosí", "Sinaloa",
    "Sonora", "Tabasco", "Tamaulipas", "Tlaxcala", "Veracruz", "Yucatán",
    "Zacatecas",
]

# ⚠️ PENDIENTE: un usuario RFC (login propio de esta app) no tiene un clUsrApp
# real de SISE ligado a él todavía (falta definir ese mapeo con el equipo).
# "Actualizar Bit?cora" SÍ necesita un clUsrApp válido para escribir en
# dbo.Seguimiento. Mientras no se resuelva, se usa este placeholder para no
# bloquear el flujo de Proveedores — pero OJO: contra el SQL Server real,
# ese registro de bitácora quedaría atribuido a este ID falso, no a la
# persona real. No usar "Actualizar Bit?cora" contra la base real hasta
# resolver esto; probarlo solo contra el servidor de datos de prueba.
CL_USR_APP_PLACEHOLDER_RFC = 0

_PBKDF2_ITERACIONES = 200_000


def verificar_rol_administrador(usuario: dict) -> None:
    """
    Exige perfil Administrador. Lo usan Configuración Cuentas (REST y
    GraphQL) y la carga del catálogo de proveedores; está centralizado aquí
    para que todas esas vías exijan exactamente la misma regla.

    Es una LISTA BLANCA (perfil == Administrador), igual que
    app/routers/admin_accesos.py:requerir_administrador. Antes era una lista
    negra (rechazaba Cabina y Proveedor), así que una sesión SISE legada
    -- cuyo token no trae 'perfil' -- pasaba de largo. Eso dejaba la puerta
    abierta justo en las dos vías que escriben configuración global del
    portal, así que se cerró (revisión de seguridad del 19-oct-2026).

    Lanza ValueError si el usuario no tiene el rol permitido.
    """
    if usuario.get("perfil") != PERFIL_ADMINISTRADOR:
        raise ValueError("Esta sección es exclusiva del perfil Administrador.")


class RfcNoAutorizado(Exception):
    pass


class CredencialesInvalidas(Exception):
    pass


class ErrorPerfil(Exception):
    """Base de los errores al agregar/quitar un perfil (el router los traduce a HTTP)."""


class AccesoNoEncontrado(ErrorPerfil):
    pass


class PerfilInvalido(ErrorPerfil):
    pass


class PerfilYaAsignado(ErrorPerfil):
    pass


def _normalizar_rfc(rfc: str) -> str:
    return rfc.strip().upper()


def _hash_password(password: str, salt: bytes) -> str:
    hash_bytes = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERACIONES)
    return salt.hex() + ":" + hash_bytes.hex()


def _crear_hash_nuevo(password: str) -> str:
    return _hash_password(password, os.urandom(16))


def _verificar_password(password: str, password_hash: str) -> bool:
    salt_hex, _, _ = password_hash.partition(":")
    salt = bytes.fromhex(salt_hex)
    calculado = _hash_password(password, salt)
    return hmac.compare_digest(calculado, password_hash)


def _perfiles_de(conn, rfc: str) -> list[int]:
    return [r["perfil"] for r in conn.execute(
        "SELECT perfil FROM usuarios_perfiles WHERE rfc = ? ORDER BY perfil", (rfc,)
    )]


def buscar_acceso(rfc: str) -> dict | None:
    """El acceso de ese RFC, con `perfiles` (todos los que tiene) además del `perfil` principal."""
    rfc = _normalizar_rfc(rfc)
    with get_local_connection() as conn:
        row = conn.execute(
            "SELECT rfc, nombre, perfil, password_hash, activo, entidad, correo FROM usuarios_acceso WHERE rfc = ?",
            (rfc,),
        ).fetchone()
        if not row:
            return None
        acceso = dict(row)
        acceso["perfiles"] = _perfiles_de(conn, rfc) or [acceso["perfil"]]
        return acceso


def nombre_o_rfc(rfc: str) -> str:
    """
    Nombre de la persona dueña de ese RFC, para mostrar en reportes/historial
    en vez del RFC a secas. Si no hay registro (ej. una sesión legada de SISE
    sin alta en usuarios_acceso), regresa el mismo RFC tal cual.
    """
    acceso = buscar_acceso(rfc)
    return acceso["nombre"] if acceso else rfc


def crear_password(rfc: str, password: str) -> dict:
    acceso = buscar_acceso(rfc)
    if not acceso or not acceso["activo"]:
        raise RfcNoAutorizado("Este RFC no está autorizado para usar el sistema.")
    if acceso["password_hash"]:
        raise CredencialesInvalidas("Este RFC ya tiene una contraseña creada, inicia sesión normalmente.")

    password_hash = _crear_hash_nuevo(password)
    with get_local_connection() as conn:
        conn.execute(
            "UPDATE usuarios_acceso SET password_hash = ? WHERE rfc = ?",
            (password_hash, _normalizar_rfc(rfc)),
        )
        conn.commit()

    acceso["password_hash"] = password_hash
    return acceso


def establecer_password(rfc: str, password: str) -> None:
    """
    Fija la contraseña de un RFC ya dado de alta, sin pasar por el primer
    ingreso. Solo para el seed de usuarios de prueba (scripts/seed_usuarios_prueba.py):
    el flujo real es que cada persona cree la suya con crear_password.
    """
    with get_local_connection() as conn:
        conn.execute(
            "UPDATE usuarios_acceso SET password_hash = ? WHERE rfc = ?",
            (_crear_hash_nuevo(password), _normalizar_rfc(rfc)),
        )
        conn.commit()


def autenticar(rfc: str, password: str) -> dict:
    acceso = buscar_acceso(rfc)
    if not acceso or not acceso["activo"] or not acceso["password_hash"]:
        raise CredencialesInvalidas("RFC o contraseña incorrectos.")
    if not _verificar_password(password, acceso["password_hash"]):
        raise CredencialesInvalidas("RFC o contraseña incorrectos.")
    return acceso


def alta_acceso(rfc: str, nombre: str, perfil: int, entidad: str | None = None, correo: str | None = None) -> None:
    """
    Da de alta un RFC autorizado, sin contraseña todavía (la crea la
    persona en su primer ingreso). Usado por el admin y por el seed de
    usuarios de prueba.

    entidad y correo: obligatorios (y validados en el schema) solo cuando
    perfil es Proveedor; para los demás perfiles se guardan como
    SIN_APLICA ("NA"), no como None -- así la grilla nunca los deja vacíos.
    """
    if perfil not in NOMBRES_PERFIL:
        raise ValueError(f"Perfil inválido: {perfil}. Válidos: {list(NOMBRES_PERFIL)}")
    entidad_final = entidad if perfil == PERFIL_PROVEEDOR else SIN_APLICA
    correo_final = correo if perfil == PERFIL_PROVEEDOR else SIN_APLICA
    with get_local_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO usuarios_acceso (rfc, nombre, perfil, password_hash, fecha_alta, entidad, correo) "
            "VALUES (?, ?, ?, (SELECT password_hash FROM usuarios_acceso WHERE rfc = ?), ?, ?, ?)",
            (_normalizar_rfc(rfc), nombre, perfil, _normalizar_rfc(rfc), ahora_local(), entidad_final, correo_final),
        )
        # Dar de alta fija el perfil (si el RFC ya existía, lo reemplaza); para
        # sumarle otro a la misma persona está agregar_perfil.
        conn.execute("DELETE FROM usuarios_perfiles WHERE rfc = ?", (_normalizar_rfc(rfc),))
        conn.execute("INSERT INTO usuarios_perfiles (rfc, perfil) VALUES (?, ?)", (_normalizar_rfc(rfc), perfil))
        conn.commit()


def agregar_perfil(rfc: str, perfil: int, entidad: str | None = None, correo: str | None = None) -> None:
    """
    Le suma un perfil a una persona que ya tiene acceso (ej. a un Administrador,
    el de Cabina). La contraseña y el RFC siguen siendo los mismos: al entrar,
    la persona elige con qué perfil. Para Proveedor, `entidad` y `correo` son
    obligatorios y se guardan en su acceso (son de la persona, no del perfil).
    """
    rfc = _normalizar_rfc(rfc)
    acceso = buscar_acceso(rfc)
    if not acceso:
        raise AccesoNoEncontrado("No se encontró ese RFC.")
    if perfil not in NOMBRES_PERFIL:
        raise PerfilInvalido(f"Perfil inválido: {perfil}. Válidos: {list(NOMBRES_PERFIL)}")
    if perfil in acceso["perfiles"]:
        raise PerfilYaAsignado(f"Ese RFC ya tiene el perfil {NOMBRES_PERFIL[perfil]}.")
    if perfil == PERFIL_PROVEEDOR and (not entidad or not correo):
        raise PerfilInvalido("Para el perfil Proveedor hace falta la entidad y el correo.")

    with get_local_connection() as conn:
        conn.execute("INSERT INTO usuarios_perfiles (rfc, perfil) VALUES (?, ?)", (rfc, perfil))
        if perfil == PERFIL_PROVEEDOR:
            conn.execute("UPDATE usuarios_acceso SET entidad = ?, correo = ? WHERE rfc = ?", (entidad, correo, rfc))
        conn.commit()


def quitar_perfil(rfc: str, perfil: int) -> None:
    """
    Le quita uno de sus perfiles a una persona. No deja a nadie sin perfil (para
    eso está inactivar) ni sin Administrador activo en el portal.
    """
    rfc = _normalizar_rfc(rfc)
    acceso = buscar_acceso(rfc)
    if not acceso:
        raise AccesoNoEncontrado("No se encontró ese RFC.")
    if perfil not in acceso["perfiles"]:
        raise PerfilInvalido("Ese RFC no tiene ese perfil.")
    restantes = [p for p in acceso["perfiles"] if p != perfil]
    if not restantes:
        raise PerfilInvalido("No se le puede quitar su único perfil. Si ya no debe entrar, inactiva el acceso.")

    with get_local_connection() as conn:
        if perfil == PERFIL_ADMINISTRADOR and acceso["activo"]:
            otros = conn.execute(
                "SELECT 1 FROM usuarios_perfiles p JOIN usuarios_acceso u ON u.rfc = p.rfc "
                "WHERE p.perfil = ? AND u.activo = 1 AND p.rfc != ? LIMIT 1",
                (PERFIL_ADMINISTRADOR, rfc),
            ).fetchone()
            if not otros:
                raise PerfilInvalido("Es el único Administrador activo: el portal no puede quedarse sin uno.")
        conn.execute("DELETE FROM usuarios_perfiles WHERE rfc = ? AND perfil = ?", (rfc, perfil))
        if acceso["perfil"] == perfil:
            conn.execute("UPDATE usuarios_acceso SET perfil = ? WHERE rfc = ?", (restantes[0], rfc))
        if perfil == PERFIL_PROVEEDOR:
            conn.execute("UPDATE usuarios_acceso SET entidad = ?, correo = ? WHERE rfc = ?", (SIN_APLICA, SIN_APLICA, rfc))
        conn.commit()


def portal_sin_accesos() -> bool:
    """True mientras la tabla de accesos está vacía: el portal aún no se activa."""
    with get_local_connection() as conn:
        return conn.execute("SELECT 1 FROM usuarios_acceso LIMIT 1").fetchone() is None


def activar_portal(rfc: str, nombre: str, password: str) -> dict | None:
    """
    Activación inicial: crea al primer Administrador, con su contraseña, SOLO
    si la tabla de accesos está vacía. Regresa el acceso creado, o None si el
    portal ya estaba activado (no se escribe nada).

    Revisar y escribir van en una sola transacción con candado de escritura
    (BEGIN IMMEDIATE): si dos personas mandan el formulario al mismo tiempo,
    solo la primera crea el usuario y la otra encuentra la tabla ya con datos.
    """
    rfc = _normalizar_rfc(rfc)
    password_hash = _crear_hash_nuevo(password)
    with get_local_connection() as conn:
        conn.isolation_level = None
        conn.execute("BEGIN IMMEDIATE")
        try:
            if conn.execute("SELECT 1 FROM usuarios_acceso LIMIT 1").fetchone() is not None:
                conn.execute("ROLLBACK")
                return None
            conn.execute(
                "INSERT INTO usuarios_acceso (rfc, nombre, perfil, password_hash, fecha_alta, entidad, correo) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (rfc, nombre, PERFIL_ADMINISTRADOR, password_hash, ahora_local(), SIN_APLICA, SIN_APLICA),
            )
            conn.execute("INSERT INTO usuarios_perfiles (rfc, perfil) VALUES (?, ?)", (rfc, PERFIL_ADMINISTRADOR))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return {"rfc": rfc, "nombre": nombre, "perfil": PERFIL_ADMINISTRADOR}


def actualizar_entidad(rfc: str, entidad: str) -> bool:
    """
    Permite cambiarle la entidad a un Proveedor ya dado de alta (ej. si en
    el futuro se reasigna a otro estado) -- antes solo se podía fijar al
    crearlo. Solo aplica a perfil Proveedor.
    """
    with get_local_connection() as conn:
        cur = conn.execute(
            "UPDATE usuarios_acceso SET entidad = ? WHERE rfc = ? "
            "AND rfc IN (SELECT rfc FROM usuarios_perfiles WHERE perfil = ?)",
            (entidad, _normalizar_rfc(rfc), PERFIL_PROVEEDOR),
        )
        conn.commit()
        return cur.rowcount > 0


def listar_accesos() -> list[dict]:
    """Grid de la pantalla de administración de Usuarios y Accesos."""
    with get_local_connection() as conn:
        rows = conn.execute(
            "SELECT rfc, nombre, perfil, password_hash, fecha_alta, activo, entidad, correo FROM usuarios_acceso "
            "ORDER BY activo DESC, fecha_alta DESC"
        ).fetchall()
        perfiles: dict[str, list[int]] = {}
        for p in conn.execute("SELECT rfc, perfil FROM usuarios_perfiles ORDER BY perfil"):
            perfiles.setdefault(p["rfc"], []).append(p["perfil"])
        return [
            {
                "rfc": r["rfc"],
                "nombre": r["nombre"],
                "perfil": r["perfil"],
                "perfiles": perfiles.get(r["rfc"]) or [r["perfil"]],
                "tiene_password": bool(r["password_hash"]),
                "fecha_alta": r["fecha_alta"],
                "activo": bool(r["activo"]),
                "entidad": r["entidad"] or SIN_APLICA,
                "correo": r["correo"] or SIN_APLICA,
            }
            for r in rows
        ]


def listar_proveedores_con_correo() -> list[dict]:
    """
    Proveedores ACTIVOS con correo capturado: a quiénes se les puede mandar
    "Enviar correo a proveedores". Regresa [{nombre, entidad, correo}].
    """
    with get_local_connection() as conn:
        rows = conn.execute(
            "SELECT nombre, entidad, correo FROM usuarios_acceso "
            "WHERE rfc IN (SELECT rfc FROM usuarios_perfiles WHERE perfil = ?) "
            "AND activo = 1 AND correo IS NOT NULL AND TRIM(correo) NOT IN ('', ?)",
            (PERFIL_PROVEEDOR, SIN_APLICA),
        ).fetchall()
    return [{"nombre": r["nombre"], "entidad": r["entidad"], "correo": r["correo"].strip()} for r in rows]


def inactivar_acceso(rfc: str) -> bool:
    """
    Baja lógica: el registro NUNCA se borra (se conserva el track de quién
    tuvo acceso), pero ya no puede iniciar sesión. Sustituye al DELETE.
    """
    with get_local_connection() as conn:
        cur = conn.execute(
            "UPDATE usuarios_acceso SET activo = 0 WHERE rfc = ? AND activo = 1", (_normalizar_rfc(rfc),)
        )
        conn.commit()
        return cur.rowcount > 0


def reactivar_acceso(rfc: str) -> bool:
    with get_local_connection() as conn:
        cur = conn.execute(
            "UPDATE usuarios_acceso SET activo = 1 WHERE rfc = ? AND activo = 0", (_normalizar_rfc(rfc),)
        )
        conn.commit()
        return cur.rowcount > 0


def resetear_password(rfc: str) -> bool:
    """Borra la contraseña actual: a la persona se le volverá a pedir crear una nueva."""
    with get_local_connection() as conn:
        cur = conn.execute(
            "UPDATE usuarios_acceso SET password_hash = NULL WHERE rfc = ?", (_normalizar_rfc(rfc),)
        )
        conn.commit()
        return cur.rowcount > 0
