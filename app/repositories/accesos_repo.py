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
# "Actualizar Core" SÍ necesita un clUsrApp válido para escribir en
# dbo.Seguimiento. Mientras no se resuelva, se usa este placeholder para no
# bloquear el flujo de Proveedores — pero OJO: contra el SQL Server real,
# ese registro de bitácora quedaría atribuido a este ID falso, no a la
# persona real. No usar "Actualizar Core" contra la base real hasta
# resolver esto; probarlo solo contra el servidor de datos de prueba.
CL_USR_APP_PLACEHOLDER_RFC = 0

_PBKDF2_ITERACIONES = 200_000


class RfcNoAutorizado(Exception):
    pass


class CredencialesInvalidas(Exception):
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


def buscar_acceso(rfc: str) -> dict | None:
    with get_local_connection() as conn:
        row = conn.execute(
            "SELECT rfc, nombre, perfil, password_hash, activo, entidad, correo FROM usuarios_acceso WHERE rfc = ?",
            (_normalizar_rfc(rfc),),
        ).fetchone()
        return dict(row) if row else None


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
        conn.commit()


def actualizar_entidad(rfc: str, entidad: str) -> bool:
    """
    Permite cambiarle la entidad a un Proveedor ya dado de alta (ej. si en
    el futuro se reasigna a otro estado) -- antes solo se podía fijar al
    crearlo. Solo aplica a perfil Proveedor.
    """
    with get_local_connection() as conn:
        cur = conn.execute(
            "UPDATE usuarios_acceso SET entidad = ? WHERE rfc = ? AND perfil = ?",
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
        return [
            {
                "rfc": r["rfc"],
                "nombre": r["nombre"],
                "perfil": r["perfil"],
                "tiene_password": bool(r["password_hash"]),
                "fecha_alta": r["fecha_alta"],
                "activo": bool(r["activo"]),
                "entidad": r["entidad"] or SIN_APLICA,
                "correo": r["correo"] or SIN_APLICA,
            }
            for r in rows
        ]


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
