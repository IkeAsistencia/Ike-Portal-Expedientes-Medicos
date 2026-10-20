from app.config import get_settings
from app.db.connection import as_tvp_rows, call_procedure, get_connection
from app.repositories import cuentas_config_repo
from app.schemas.catalogo import CatalogoItem, CatalogoItemTexto, EntidadFederativa


# Únicos subservicios que trabaja dbo.ST_CP_ObtenerExpedientesSinProveedorMedico
# (sql/01_..._Medico.sql) -- el resto del catálogo de clServicio=4 (Ambulancia,
# Consulta Médica Virtual, Médico a Domicilio, etc.) siempre regresaría 0
# resultados en esta pantalla, así que no tiene caso ofrecerlo en el combo.
#   226 Referencias Médicas, 376 Segunda Opinión, 377 Check Up,
#   383 Consulta Médica en Consultorio, 403 Renta de Equipo Médico,
#   404 Enfermería a Domicilio, 420 Plan Visión, 432 Envío de Medicamentos
SUBSERVICIOS_PERMITIDOS = frozenset({226, 376, 377, 383, 403, 404, 420, 432})


def listar_servicios(cl_servicio: int = 4) -> list[CatalogoItem]:
    rows = call_procedure("dbo.ST_CP_ObtenerCatalogoServicio", {"clServicio": cl_servicio})
    return [CatalogoItem(clave=r["clServicio"], descripcion=r["dsServicio"]) for r in rows]


def listar_subservicios(cl_servicio: int = 4) -> list[CatalogoItem]:
    """
    Combo Subservicio. Usa dbo.ST_CP_ObtenerServicioMedico (sql/07_...sql),
    que reemplaza al SP legado dbo.sp_GetSubServicios2 — ese requería
    @clCuenta (filtra por cobertura de una sola cuenta), lo cual no
    encaja con el filtro Cuenta de la pantalla Expedientes (permite
    varias a la vez).
    """
    rows = call_procedure("dbo.ST_CP_ObtenerServicioMedico", {"clServicio": cl_servicio})
    return [
        CatalogoItem(clave=r["clSubServicio"], descripcion=r["dsSubServicio"])
        for r in rows
        if r["clSubServicio"] in SUBSERVICIOS_PERMITIDOS
    ]


def listar_cuentas() -> list[CatalogoItem]:
    """
    Combo Cuenta (filtro de Expedientes) y lista de Cuentas Especiales: son las
    cuentas que ya se jalaban (lista fija CUENTAS_PERMITIDAS del .env) MÁS las
    adicionales que el Administrador agregó en "Agregar cuenta". Los nombres
    se leen de Core. Si CUENTAS_PERMITIDAS está vacía no hay restricción (salen
    todas las de Core) y las adicionales no cambian nada.
    """
    settings = get_settings()
    base = settings.parse_int_list(settings.cuentas_permitidas)
    if base:
        adicionales = [c["cl_cuenta"] for c in cuentas_config_repo.listar_cuentas_configuradas()]
        permitidos = as_tvp_rows(base + [c for c in adicionales if c not in base])
    else:
        permitidos = as_tvp_rows([])
    rows = call_procedure(
        "dbo.ST_CP_ObtenerCatalogoCuentas",
        {"CuentasPermitidas": permitidos},
    )
    return [CatalogoItem(clave=r["clCuenta"], descripcion=r["Nombre"]) for r in rows]


def listar_entidades() -> list[EntidadFederativa]:
    """
    Combo Entidad del Alta de médico (Directorio de Proveedores) -- mismas
    32 entidades que ya usa Seguimiento/Expedientes, pero con su CodEnt real
    (dbo.cEntFed), necesario para después pedir los municipios de esa
    entidad a dbo.sp_GetMun (ver listar_municipios).

    También se trae clEntFed (1 a 32) como `clave_inegi`, con dos dígitos:
    es la clave de entidad federativa del INEGI, que pide el DENUE para
    acotar el área geográfica en la búsqueda fuera de la red (ver
    app/services/denue_service.py). Se lee de la misma tabla en vez de
    mantener aquí una equivalencia "JC -> 14" a mano, que se desincronizaría
    en silencio.

    CONFIRMADO contra la base real (2026-10-20): las 32 entidades coinciden
    una a una con el orden oficial del INEGI (01 Aguascalientes ... 32
    Zacatecas); JC -> 14 Jalisco, y con CodMD "00039" el área "14039" devuelve
    Guadalajara en el DENUE. Para volver a revisarlo:
    GET /directorio-proveedores/fuera-de-red regresa en `area` la clave que
    armó, así se compara contra el catálogo del INEGI sin leer la base.

    ÚNICA excepción a "solo Stored Procedures" de este módulo: cEntFed es
    una tabla de catálogo de solo lectura, sin ningún valor interpolado en
    la consulta (0% superficie de inyección) -- no existe un SP equivalente
    a sp_GetMun para entidades (confirmado con el usuario, 2026-10-19).
    clEntFed BETWEEN 1 AND 32 -- mismo filtro que dio el usuario, para
    quedarse solo con las 32 entidades (la tabla real trae renglones fuera
    de ese rango que no aplican aquí).
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT CodEnt, dsEntFed, clEntFed FROM dbo.cEntFed "
            "WHERE clEntFed BETWEEN 1 AND 32 ORDER BY dsEntFed"
        )
        filas = cursor.fetchall()
    return [
        EntidadFederativa(
            clave=f.CodEnt.strip(),
            descripcion=f.dsEntFed,
            clave_inegi=str(int(f.clEntFed)).zfill(2),
        )
        for f in filas
    ]


def clave_inegi_de_entidad(cod_ent: str) -> str | None:
    """
    CodEnt del sistema central ("JC") -> clave de entidad del INEGI ("14"),
    que es la que necesita el DENUE. None si ese CodEnt no está en el
    catálogo.
    """
    for entidad in listar_entidades():
        if entidad.clave.upper() == (cod_ent or "").strip().upper():
            return entidad.clave_inegi
    return None


def listar_municipios(cod_ent: str) -> list[CatalogoItemTexto]:
    """
    Municipios de una entidad, vía el SP legado dbo.sp_GetMun -- @clExpediente
    siempre en 0 (no aplica para este catálogo). Columnas de salida
    confirmadas por el usuario, 2026-10-19: CodMD, dsMunDel, CodEnt -- se
    busca sin distinguir mayúsculas/minúsculas por si acaso, ya que no hay
    una definición de este SP en sql/*.sql para confirmar la casing exacta.
    """
    filas = call_procedure("dbo.sp_GetMun", {"CodEnt": cod_ent, "clExpediente": 0})
    resultado = []
    for fila in filas:
        por_minuscula = {clave.lower(): valor for clave, valor in fila.items()}
        resultado.append(CatalogoItemTexto(
            clave=str(por_minuscula["codmd"]).strip(),
            descripcion=por_minuscula["dsmundel"],
        ))
    return resultado


def buscar_cuentas(texto: str) -> list[dict]:
    """
    Typeahead de la pantalla Configuración Cuentas, usando el SP YA
    EXISTENTE dbo.sp_S2_BuscaCuenta.

    NOTA: no tenemos el nombre exacto de su parámetro de entrada, así
    que se llama posicionalmente (un solo parámetro). Si el SP requiere
    más parámetros o en otro orden, ajustar aquí.
    """
    rows = call_procedure("dbo.sp_S2_BuscaCuenta", (texto,))
    return [{"cl_cuenta": r["clCuenta"], "nombre": r["Nombre"]} for r in rows]
