"""
Login contra el SP legado dbo.sp_EncriptDesEncriptPassword (ya existe en
tu base, no se crea aquí).

Columnas de salida CONFIRMADAS (de todas las que regresa el SP, solo
estas 3 se usan):
    clUsrApp -> se guarda en la bitácora de Seguimiento
    Nombre   -> se muestra en la app una vez logeado el usuario
    activo   -> si es falso, se bloquea el acceso con un mensaje fijo
    (la columna real en la tabla es "Activo", con A mayúscula)
"""

from app.db.connection import call_procedure

COLUMNA_CL_USR_APP = "clUsrApp"
COLUMNA_NOMBRE = "Nombre"
COLUMNA_ACTIVO = "Activo"

MENSAJE_USUARIO_INACTIVO = "Usuario sin permisos o inactivo, valide con el Supervisor"

# @pContraseña es varchar(10) en el SP, aunque la pantalla de login
# permite hasta 20 (ver inconsistencia documentada en sql/05_..._NOTAS.md).
LARGO_MAXIMO_PASSWORD_SP = 10


class CredencialesInvalidas(Exception):
    pass


class UsuarioInactivo(Exception):
    pass


def autenticar(usuario: str, password: str, host: str, ip: str) -> dict:
    if len(password) > LARGO_MAXIMO_PASSWORD_SP:
        # No se trunca en silencio: preferible fallar explícito a que
        # SQL Server trunque el parámetro y valide contra una
        # contraseña distinta a la que el usuario realmente escribió.
        raise CredencialesInvalidas(
            f"La contraseña excede el límite soportado ({LARGO_MAXIMO_PASSWORD_SP} caracteres). "
            "Confirmar con el equipo de base de datos si el límite real es 10 o 20."
        )

    rows = call_procedure(
        "dbo.sp_EncriptDesEncriptPassword",
        {
            "pUsuario": usuario,
            "CreateSession": 0,
            "pHost": host,
            "pContraseña": password,
            "ip": ip,
        },
    )

    if not rows:
        raise CredencialesInvalidas("Usuario o contraseña incorrectos.")

    fila = rows[0]

    cl_usr_app = fila.get(COLUMNA_CL_USR_APP)
    if cl_usr_app is None:
        raise CredencialesInvalidas("Usuario o contraseña incorrectos.")

    if not fila.get(COLUMNA_ACTIVO):
        raise UsuarioInactivo(MENSAJE_USUARIO_INACTIVO)

    return {
        "cl_usr_app": cl_usr_app,
        "usuario": usuario,
        "nombre": fila.get(COLUMNA_NOMBRE) or usuario,
    }
