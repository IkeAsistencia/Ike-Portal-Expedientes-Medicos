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


class CuentaBusqueda(BaseModel):
    """Resultado del typeahead de sp_S2_BuscaCuenta (Configuración Cuentas)."""

    cl_cuenta: int
    nombre: str
