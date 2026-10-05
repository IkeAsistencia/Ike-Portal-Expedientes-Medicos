from app.config import get_settings
from app.db.connection import as_tvp_rows, call_procedure
from app.schemas.catalogo import CatalogoItem


def listar_servicios(cl_servicio: int = 4) -> list[CatalogoItem]:
    rows = call_procedure("dbo.ObtenerCatalogoServicio", {"clServicio": cl_servicio})
    return [CatalogoItem(clave=r["clServicio"], descripcion=r["dsServicio"]) for r in rows]


def listar_subservicios(cl_servicio: int = 4) -> list[CatalogoItem]:
    """
    Combo Subservicio. Usa dbo.ObtenerServicioMedico (sql/09_...sql),
    que reemplaza al SP legado dbo.sp_GetSubServicios2 — ese requería
    @clCuenta (filtra por cobertura de una sola cuenta), lo cual no
    encaja con el filtro Cuenta de la pantalla Expedientes (permite
    varias a la vez). Ver sql/08_subservicios_sp_GetSubServicios2_NOTAS.md.
    """
    rows = call_procedure("dbo.ObtenerServicioMedico", {"clServicio": cl_servicio})
    return [CatalogoItem(clave=r["clSubServicio"], descripcion=r["dsSubServicio"]) for r in rows]


def listar_cuentas() -> list[CatalogoItem]:
    settings = get_settings()
    permitidos = as_tvp_rows(settings.parse_int_list(settings.cuentas_permitidas))
    rows = call_procedure(
        "dbo.ObtenerCatalogoCuentas",
        {"CuentasPermitidas": permitidos},
    )
    return [CatalogoItem(clave=r["clCuenta"], descripcion=r["Nombre"]) for r in rows]


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
