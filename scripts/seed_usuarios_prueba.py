"""
Da de alta 3 RFC de prueba (uno por perfil) en la base local, para poder
probar el login por RFC de punta a punta mientras se define el proceso
real de alta de usuarios.

Uso:
    python -m scripts.seed_usuarios_prueba
    python -m scripts.seed_usuarios_prueba --password 'Qwer1234$'

Con --password los 3 usuarios quedan con esa contraseña (sin pasar por el
primer ingreso); sin ella, cada quien crea la suya la primera vez.

Después de correrlo, entra con cualquiera de estos RFC (la primera vez
te va a pedir crear una contraseña):
    ADMI000001 -> perfil Administrador
    CABI000001 -> perfil Cabina
    PROV000001 -> perfil Proveedor (entidad Campeche)

Siguen el mismo formato que exige el alta desde el portal: 4 letras + 6
números (10 caracteres, el máximo que acepta el login).

El servidor de datos de prueba (dev_server_datos_prueba.py) ya los da de
alta solo al arrancar; este script es para cuando uses la base real.

NO usar estos RFC de prueba en producción — son solo para pruebas locales.
"""

import argparse

from app.db.local_store import init_local_db
from app.repositories import accesos_repo
from app.schemas.acceso import MENSAJE_REGLA_PASSWORD, _cumple_regla_password

# (rfc, nombre, perfil, entidad, correo) -- entidad y correo solo aplican a
# Proveedor (son obligatorios para ese perfil, igual que en el alta del portal).
USUARIOS_PRUEBA = [
    ("ADMI000001", "Admin de Prueba", accesos_repo.PERFIL_ADMINISTRADOR, None, None),
    ("CABI000001", "Cabina de Prueba", accesos_repo.PERFIL_CABINA, None, None),
    ("PROV000001", "Proveedor de Prueba", accesos_repo.PERFIL_PROVEEDOR, "Campeche", "proveedor.prueba@example.com"),
]


def ejecutar(password: str | None = None) -> None:
    if password is not None and not _cumple_regla_password(password):
        raise SystemExit(MENSAJE_REGLA_PASSWORD)
    init_local_db()
    for rfc, nombre, perfil, entidad, correo in USUARIOS_PRUEBA:
        # alta_acceso es idempotente (INSERT OR REPLACE) y conserva la
        # contraseña si el RFC ya la había creado.
        accesos_repo.alta_acceso(rfc, nombre, perfil, entidad, correo)
        if password is not None:
            accesos_repo.establecer_password(rfc, password)
        print(f"OK: {rfc} -> {nombre} (perfil {perfil} = {accesos_repo.NOMBRES_PERFIL[perfil]})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Alta de 3 RFC de prueba (uno por perfil).")
    parser.add_argument("--password", help="Contraseña común para los 3 usuarios (opcional).")
    ejecutar(parser.parse_args().password)
