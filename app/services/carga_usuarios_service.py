"""
Lee un Excel de usuarios y da de alta esos accesos -- compartido por
`scripts/cargar_usuarios_excel.py` (uso manual, con modo seco), por el
arranque de la app (siembra automática del primer despliegue, ver
`_sembrar_usuarios_iniciales` en app/main.py) y por la carga masiva de la
pantalla Usuarios y Accesos (POST /admin/accesos/carga-excel).

Formato esperado: ver el encabezado de scripts/cargar_usuarios_excel.py. El
lector es tolerante con los archivos que mandan las áreas: el encabezado
puede no estar en el primer renglón, se leen todas las hojas, y las
columnas pueden llamarse distinto (ver ENCABEZADOS). El RFC se corta a sus
primeros 10 caracteres, así que uno con homoclave (13) sirve igual.
"""

import re
import unicodedata
import zipfile
from typing import IO

import openpyxl
from openpyxl.utils.exceptions import InvalidFileException

from app.core.correo_empresa import DOMINIO_EMPRESA, es_correo_de_empresa
from app.repositories import accesos_repo
from app.schemas.acceso import PATRON_RFC

ROLES = {
    "CABINA": accesos_repo.PERFIL_CABINA,
    "ADMINISTRADOR": accesos_repo.PERFIL_ADMINISTRADOR,
    "PROVEEDOR": accesos_repo.PERFIL_PROVEEDOR,
}

# Tipos de carga de la pantalla: (rol de todas las filas, entidad que se le
# pone a los Proveedores que no traen). "segun_archivo" lee la columna ROL.
ENTIDAD_POR_DEFECTO_PROVEEDORES = "Ciudad de México"
TIPOS_DE_CARGA = {
    "cabina": ("CABINA", None),
    "proveedor": ("PROVEEDOR", ENTIDAD_POR_DEFECTO_PROVEEDORES),
    "segun_archivo": (None, None),
}

# Nombres con los que puede venir cada columna (ya sin acentos y en mayúsculas).
ENCABEZADOS = {
    "rfc": {"RFC"},
    "nombre": {"NOMBRE", "NOMBRE COMPLETO", "USUARIO", "NOMBRE DEL COORDINADOR"},
    "rol": {"ROL", "PERFIL"},
    "entidad": {"ENTIDAD"},
    "correo": {"CORREO", "CORREO ELECTRONICO", "EMAIL"},
}
_RENGLONES_PARA_ENCONTRAR_ENCABEZADO = 10

# Tope de filas por archivo: un Excel gigante no debe dejar al servidor
# trabajando (el de Cabina de hoy trae ~70).
MAXIMO_FILAS = 1000
LARGO_RFC = 10

ACCION_NUEVO = "nuevo"
ACCION_PERFIL_AGREGADO = "perfil_agregado"
ACCION_YA_EXISTIA = "ya_existia"


class ErrorCargaUsuarios(Exception):
    pass


def _sin_acentos_en_mayusculas(texto: str) -> str:
    base = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", base).strip().upper()


_ENTIDADES_POR_NOMBRE = {_sin_acentos_en_mayusculas(e): e for e in accesos_repo.ENTIDADES_MEXICO}


def _columnas_de(renglon: tuple) -> dict[str, int]:
    """{campo: posición} si el renglón es el encabezado (trae la columna RFC); si no, {}."""
    encontradas: dict[str, int] = {}
    for posicion, valor in enumerate(renglon):
        if not isinstance(valor, str):
            continue
        nombre = _sin_acentos_en_mayusculas(valor)
        for campo, nombres in ENCABEZADOS.items():
            if nombre in nombres and campo not in encontradas:
                encontradas[campo] = posicion
    return encontradas if "rfc" in encontradas else {}


def _texto(renglon: tuple, columnas: dict[str, int], campo: str) -> str:
    posicion = columnas.get(campo)
    if posicion is None or posicion >= len(renglon) or renglon[posicion] is None:
        return ""
    return str(renglon[posicion]).strip()


def leer_filas(origen: str | IO[bytes], rol_por_defecto: str | None = None) -> list[dict]:
    """
    Filas de todas las hojas que tienen encabezado con la columna RFC. `origen`
    es una ruta o el archivo ya abierto. Sin `rol_por_defecto`, la columna ROL
    es obligatoria; con él, TODAS las filas toman ese rol y la columna ROL, si
    la hay, se ignora (lo que se eligió en la pantalla manda).
    """
    try:
        wb = openpyxl.load_workbook(origen, read_only=True, data_only=True)
    except FileNotFoundError:
        raise ErrorCargaUsuarios(f"No existe el archivo: {origen}")
    except (InvalidFileException, zipfile.BadZipFile, KeyError, OSError):
        raise ErrorCargaUsuarios("El archivo no es un Excel (.xlsx) válido.")

    filas: list[dict] = []
    faltantes: list[str] = []
    hojas_con_encabezado = 0
    try:
        for ws in wb.worksheets:
            renglones = ws.iter_rows(values_only=True)
            columnas: dict[str, int] = {}
            for numero, renglon in enumerate(renglones, start=1):
                if numero > _RENGLONES_PARA_ENCONTRAR_ENCABEZADO:
                    break
                columnas = _columnas_de(renglon)
                if columnas:
                    break
            if not columnas:
                continue  # hoja sin encabezado de RFC (vacía o de otra cosa): se ignora
            hojas_con_encabezado += 1

            obligatorias = ["nombre"] + ([] if rol_por_defecto else ["rol"])
            faltantes += [c for c in obligatorias if c not in columnas]
            if faltantes:
                continue

            for numero, renglon in enumerate(renglones, start=numero + 1):
                rfc = re.sub(r"\s+", "", _texto(renglon, columnas, "rfc")).upper()[:LARGO_RFC]
                if not rfc:
                    continue
                if len(filas) >= MAXIMO_FILAS:
                    raise ErrorCargaUsuarios(f"El archivo trae más de {MAXIMO_FILAS} filas; divídelo en varios.")
                filas.append({
                    "hoja": ws.title,
                    "renglon": numero,
                    "rfc": rfc,
                    "nombre": _texto(renglon, columnas, "nombre"),
                    "rol": rol_por_defecto or _texto(renglon, columnas, "rol").upper(),
                    "entidad": _texto(renglon, columnas, "entidad") or None,
                    "correo": _texto(renglon, columnas, "correo") or None,
                })
    finally:
        wb.close()

    if not hojas_con_encabezado:
        raise ErrorCargaUsuarios("No encontré la columna RFC en el archivo (debe estar en los primeros renglones).")
    if faltantes:
        raise ErrorCargaUsuarios(f"Al Excel le falta la columna {faltantes[0].upper()!r}.")
    return filas


def validar_fila(fila: dict) -> str | None:
    """Regresa el motivo de rechazo, o None si la fila está lista para darse de alta."""
    if fila["rol"] not in ROLES:
        return f"rol desconocido {fila['rol']!r} (válidos: {', '.join(ROLES)})"
    if not fila["nombre"]:
        return "falta el nombre"

    perfil = ROLES[fila["rol"]]
    if not PATRON_RFC.match(fila["rfc"]):
        return "RFC inválido: debe tener 10 caracteres (4 letras + 6 números)"

    if perfil == accesos_repo.PERFIL_PROVEEDOR:
        if not fila["entidad"] or not fila["correo"]:
            return "faltan ENTIDAD/CORREO, obligatorios para Proveedor"
        if _sin_acentos_en_mayusculas(fila["entidad"]) not in _ENTIDADES_POR_NOMBRE:
            return f"entidad desconocida {fila['entidad']!r}"
        if not es_correo_de_empresa(fila["correo"]):
            return f"el correo no es del dominio @{DOMINIO_EMPRESA}"
    return None


def sembrar_desde_excel(
    origen: str | IO[bytes],
    aplicar: bool = True,
    rol_por_defecto: str | None = None,
    entidad_por_defecto: str | None = None,
) -> dict:
    """
    Da de alta cada fila válida del Excel. Con aplicar=False solo valida y
    regresa el plan, sin escribir nada.

    Un RFC que todavía no existe se da de alta; si ya existe (en la base o en
    un renglón anterior del mismo archivo) solo se le SUMA el perfil que le
    falta, sin tocar su nombre ni su contraseña, así que repetir una carga es
    seguro. `entidad_por_defecto` se les pone a los Proveedores que no traen.
    """
    filas = leer_filas(origen, rol_por_defecto)
    if entidad_por_defecto:
        for fila in filas:
            if fila["rol"] == "PROVEEDOR" and not fila["entidad"]:
                fila["entidad"] = entidad_por_defecto

    listas, rechazadas = [], []
    for fila in filas:
        motivo = validar_fila(fila)
        (rechazadas if motivo else listas).append((fila, motivo))

    perfiles_de: dict[str, set[int] | None] = {}  # rfc -> perfiles que ya tiene (None = no existe)
    plan = []
    for fila, _ in listas:
        perfil = ROLES[fila["rol"]]
        rfc = fila["rfc"]
        if rfc not in perfiles_de:
            acceso = accesos_repo.buscar_acceso(rfc)
            perfiles_de[rfc] = set(acceso["perfiles"]) if acceso else None
        tiene = perfiles_de[rfc]
        if perfil == accesos_repo.PERFIL_PROVEEDOR:
            fila["entidad"] = _ENTIDADES_POR_NOMBRE[_sin_acentos_en_mayusculas(fila["entidad"])]

        if tiene is None:
            accion = ACCION_NUEVO
            perfiles_de[rfc] = {perfil}
            if aplicar:
                accesos_repo.alta_acceso(rfc, fila["nombre"], perfil, fila["entidad"], fila["correo"])
        elif perfil in tiene:
            accion = ACCION_YA_EXISTIA
        else:
            accion = ACCION_PERFIL_AGREGADO
            tiene.add(perfil)
            if aplicar:
                try:
                    accesos_repo.agregar_perfil(rfc, perfil, fila["entidad"], fila["correo"])
                except accesos_repo.PerfilYaAsignado:
                    pass  # alguien se lo dio mientras tanto
        plan.append((fila, accion))

    cuenta = lambda accion: sum(1 for _, a in plan if a == accion)  # noqa: E731
    return {
        "total": len(filas),
        "listas": listas,
        "rechazadas": rechazadas,
        "plan": plan,
        "nuevos": cuenta(ACCION_NUEVO),
        "perfiles_agregados": cuenta(ACCION_PERFIL_AGREGADO),
        "ya_existian": cuenta(ACCION_YA_EXISTIA),
    }
