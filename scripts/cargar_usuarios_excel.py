"""
Da de alta en lote los accesos del portal a partir de un Excel con las
columnas RFC, NOMBRE y ROL -- para sembrar usuarios productivos (Cabina y
Administrador) sin tener que darlos de alta uno por uno desde la pantalla
Usuarios y Accesos.

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

import openpyxl

from app.db.local_store import init_local_db
from app.repositories import accesos_repo
from app.schemas.acceso import PATRON_RFC, PATRON_RFC_ADMINISTRADOR

ROLES = {
    "CABINA": accesos_repo.PERFIL_CABINA,
    "ADMINISTRADOR": accesos_repo.PERFIL_ADMINISTRADOR,
    "PROVEEDOR": accesos_repo.PERFIL_PROVEEDOR,
}


def _leer_filas(ruta_archivo: str) -> list[dict]:
    wb = openpyxl.load_workbook(ruta_archivo, data_only=True)
    ws = wb.worksheets[0]
    encabezados = [
        (c.value or "").strip().upper() if isinstance(c.value, str) else c.value
        for c in next(ws.iter_rows(min_row=1, max_row=1))
    ]
    indice = {nombre: i for i, nombre in enumerate(encabezados) if nombre}

    for col in ("RFC", "NOMBRE", "ROL"):
        if col not in indice:
            raise SystemExit(f"Al Excel le falta la columna {col!r} (encabezados encontrados: {encabezados}).")

    filas = []
    for fila in ws.iter_rows(min_row=2, values_only=True):
        rfc = fila[indice["RFC"]]
        if not rfc:
            continue
        filas.append({
            "rfc": str(rfc).strip().upper(),
            "nombre": str(fila[indice["NOMBRE"]] or "").strip(),
            "rol": str(fila[indice["ROL"]] or "").strip().upper(),
            "entidad": str(fila[indice["ENTIDAD"]]).strip() if "ENTIDAD" in indice and fila[indice["ENTIDAD"]] else None,
            "correo": str(fila[indice["CORREO"]]).strip() if "CORREO" in indice and fila[indice["CORREO"]] else None,
        })
    return filas


def _validar(fila: dict) -> str | None:
    """Regresa el motivo de rechazo, o None si la fila está lista para darse de alta."""
    if fila["rol"] not in ROLES:
        return f"rol desconocido {fila['rol']!r} (válidos: {', '.join(ROLES)})"
    if not fila["nombre"]:
        return "falta el nombre"

    perfil = ROLES[fila["rol"]]
    if perfil == accesos_repo.PERFIL_ADMINISTRADOR:
        if not PATRON_RFC_ADMINISTRADOR.match(fila["rfc"]):
            return "RFC de Administrador inválido: debe tener 11 caracteres (4 letras + 6 números + homoclave)"
    elif not PATRON_RFC.match(fila["rfc"]):
        return "RFC inválido: debe tener 10 caracteres (4 letras + 6 números)"

    if perfil == accesos_repo.PERFIL_PROVEEDOR and (not fila["entidad"] or not fila["correo"]):
        return "faltan ENTIDAD/CORREO, obligatorios para Proveedor"
    return None


def ejecutar(ruta_archivo: str, aplicar: bool = False) -> dict:
    init_local_db()
    filas = _leer_filas(ruta_archivo)
    print(f"Leídas {len(filas)} fila(s) de {ruta_archivo}.")

    listas, rechazadas = [], []
    for fila in filas:
        motivo = _validar(fila)
        (rechazadas if motivo else listas).append((fila, motivo))

    for fila, motivo in rechazadas:
        print(f"  RECHAZADA  {fila['rfc']:<12} {fila['nombre']:<40} -- {motivo}")

    for fila, _ in listas:
        perfil = ROLES[fila["rol"]]
        accion = "ALTA" if aplicar else "ALTA (simulada)"
        print(f"  {accion:<16} {fila['rfc']:<12} {fila['nombre']:<40} -> {fila['rol']}")
        if aplicar:
            accesos_repo.alta_acceso(fila["rfc"], fila["nombre"], perfil, fila["entidad"], fila["correo"])

    print()
    print(f"Total: {len(listas)} lista(s) para alta, {len(rechazadas)} rechazada(s).")
    if not aplicar and listas:
        print("Modo simulado: no se escribió nada. Vuelve a correr con --aplicar para darlas de alta.")
    return {"listas": len(listas), "rechazadas": len(rechazadas)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Alta en lote de accesos desde un Excel (RFC, NOMBRE, ROL).")
    parser.add_argument("excel", help="Ruta al archivo .xlsx")
    parser.add_argument("--aplicar", action="store_true", help="Escribe los accesos (sin esto solo se simula).")
    args = parser.parse_args()
    ejecutar(args.excel, aplicar=args.aplicar)
