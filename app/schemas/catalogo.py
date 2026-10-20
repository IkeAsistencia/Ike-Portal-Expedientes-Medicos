from pydantic import BaseModel


class CatalogoItem(BaseModel):
    """Item genérico de catálogo (subservicio, cuenta, etc.)."""

    clave: int
    descripcion: str


class CatalogoItemTexto(BaseModel):
    """Igual que CatalogoItem, pero con clave de texto (CodEnt, CodMD -- no
    son numéricos, ej. pueden traer ceros a la izquierda)."""

    clave: str
    descripcion: str


class EntidadFederativa(CatalogoItemTexto):
    """
    Entidad del combo del Alta de médico. Además del CodEnt que usa el
    sistema central ("JC"), trae la clave numérica del INEGI de dos dígitos
    ("14"), que es la que pide el DENUE para acotar por área geográfica
    (ver app/services/denue_service.py).
    """

    clave_inegi: str


class CuentaBusqueda(BaseModel):
    """Resultado del typeahead de sp_S2_BuscaCuenta (Configuración Cuentas)."""

    cl_cuenta: int
    nombre: str
