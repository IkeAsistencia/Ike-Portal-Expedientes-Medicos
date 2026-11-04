"""
Da de alta en lote los accesos del portal a partir de un Excel con las
columnas RFC, NOMBRE y ROL -- para sembrar usuarios productivos (Cabina y
Administrador) sin tener que darlos de alta uno por uno desde la pantalla
Usuarios y Accesos.

En producción esto ya NO hace falta correrlo a mano: el servidor lo hace
solo en su primer arranque si configuras SEED_USUARIOS_RUTA (ver
DESPLIEGUE-PRODUCCION.md y `_sembrar_usuarios_iniciales` en app/main.py).
Este script sigue sirviendo para el ambiente local/de pruebas, o para
cargar altas sueltas fuera de ese primer arranque.

FORMATO ESPERADO DEL EXCEL (una fila por persona, cabecera en la fila 1):
    RFC          NOMBRE                        ROL
    MIMA991129   MIRANDA MARTINEZ ANA KAREN     CABINA
    PASE950502G  EMMANUEL PARRA SANCHEZ         ADMINISTRADOR

- ROL acepta (sin distinguir mayúsculas/minúsculas): CABINA, ADMINISTRADOR,
  PROVEEDOR.
- RFC de Cabina y Proveedor: 10 caracteres (4 letras + 6 números).
- RFC de Administrador: 11 caracteres -- los mismos 10 más el primer
  caracter de la homoclave (ej. ABCD123456Z) -- porque el RFC de 10
  caracteres no siempre distingue a dos administradores.
- Proveedor necesita además columnas ENTIDAD y CORREO (obligatorias para
  ese perfil); si el Excel no las trae, las filas de Proveedor se rechazan
  con el motivo "faltan ENTIDAD/CORREO", no se adivinan.

Cada acceso se crea SIN contraseña (igual que el alta manual): la persona
crea la suya la primera vez que entra con su RFC.

USO:
    # 1) Ver qué haría, SIN tocar la base (así arranca por defecto):
    python -m scripts.cargar_usuarios_excel UsuariosPortal_ProMedico.xlsx

    # 2) Aplicarlo:
    python -m scripts.cargar_usuarios_excel UsuariosPortal_ProMedico.xlsx --aplicar

Corre en seco a propósito: da de alta accesos reales, así que conviene
revisar el plan antes de escribirlo.

QUÉ NO HACE:
  - No manda correo ni avisa a nadie: solo deja el acceso listo para que la
    persona entre y cree su contraseña.
  - No borra ni inactiva a nadie que no esté en el Excel.
  - alta_acceso es idempotente (INSERT OR REPLACE): si el RFC ya existe,
    actualiza nombre/perfil y conserva la contraseña que ya se haya creado.
"""

import argparse

from app.db.local_store import init_local_db
from app.services.carga_usuarios_service import ErrorCargaUsuarios, sembrar_desde_excel


def ejecutar(ruta_archivo: str, aplicar: bool = False) -> dict:
    init_local_db()
    try:
        resultado = sembrar_desde_excel(ruta_archivo, aplicar=aplicar)
    except ErrorCargaUsuarios as err:
        raise SystemExit(str(err))

    print(f"Leídas {resultado['total']} fila(s) de {ruta_archivo}.")
    for fila, motivo in resultado["rechazadas"]:
        print(f"  RECHAZADA  {fila['rfc']:<12} {fila['nombre']:<40} -- {motivo}")
    for fila, _ in resultado["listas"]:
        accion = "ALTA" if aplicar else "ALTA (simulada)"
        print(f"  {accion:<16} {fila['rfc']:<12} {fila['nombre']:<40} -> {fila['rol']}")

    print()
    print(f"Total: {len(resultado['listas'])} lista(s) para alta, {len(resultado['rechazadas'])} rechazada(s).")
    if not aplicar and resultado["listas"]:
        print("Modo simulado: no se escribió nada. Vuelve a correr con --aplicar para darlas de alta.")
    return {"listas": len(resultado["listas"]), "rechazadas": len(resultado["rechazadas"])}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Alta en lote de accesos desde un Excel (RFC, NOMBRE, ROL).")
    parser.add_argument("excel", help="Ruta al archivo .xlsx")
    parser.add_argument("--aplicar", action="store_true", help="Escribe los accesos (sin esto solo se simula).")
    args = parser.parse_args()
    ejecutar(args.excel, aplicar=args.aplicar)
