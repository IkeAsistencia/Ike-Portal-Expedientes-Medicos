"""
Da de alta 3 RFC de prueba (uno por perfil) en la base local, para poder
probar el login por RFC de punta a punta mientras se define el proceso
real de alta de usuarios.

Uso:
    python -m scripts.seed_usuarios_prueba

Después de correrlo, entra con cualquiera de estos RFC (la primera vez
te va a pedir crear una contraseña):
    RFCADMIN01  -> perfil Administrador
    RFCCABINA01 -> perfil Cabina
    RFCPROVEE01 -> perfil Proveedor

NO usar estos RFC de prueba en producción — son solo para pruebas locales.
"""

from app.db.local_store import init_local_db
from app.repositories import accesos_repo

USUARIOS_PRUEBA = [
    ("RFCADMIN01", "Admin de Prueba", accesos_repo.PERFIL_ADMINISTRADOR),
    ("RFCCABINA01", "Cabina de Prueba", accesos_repo.PERFIL_CABINA),
    ("RFCPROVEE01", "Proveedor de Prueba", accesos_repo.PERFIL_PROVEEDOR),
]


def ejecutar() -> None:
    init_local_db()
    for rfc, nombre, perfil in USUARIOS_PRUEBA:
        accesos_repo.alta_acceso(rfc, nombre, perfil)
        print(f"OK: {rfc} -> {nombre} (perfil {perfil} = {accesos_repo.NOMBRES_PERFIL[perfil]})")


if __name__ == "__main__":
    ejecutar()
