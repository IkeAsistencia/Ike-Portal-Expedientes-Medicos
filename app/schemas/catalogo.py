from pydantic import BaseModel


class CatalogoItem(BaseModel):
    """Item genérico de catálogo (subservicio, cuenta, etc.)."""

    clave: int
    descripcion: str


class CuentaBusqueda(BaseModel):
    """Resultado del typeahead de sp_S2_BuscaCuenta (Configuración Cuentas)."""

    cl_cuenta: int
    nombre: str
