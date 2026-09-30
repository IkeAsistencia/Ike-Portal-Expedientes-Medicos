"""
Query root de GraphQL. Cada resolver reutiliza exactamente el mismo
repositorio (app/repositories/) que ya usa el REST — no hay lógica de
negocio duplicada, solo una forma distinta de exponerla.
"""

from typing import Optional

import strawberry

from app.graphql.inputs import ExpedienteFiltroInput
from app.graphql.types import CatalogoItem, CuentaBusqueda, CuentaConfigurada, Expediente
from app.repositories import catalogos_repo, cuentas_config_repo, expedientes_repo
from app.schemas.expediente import ExpedienteFiltro


@strawberry.type
class Query:
    @strawberry.field(description="Pantalla Expedientes: tabla filtrable. Requiere sesión.")
    def expedientes(self, info: strawberry.Info, filtro: Optional[ExpedienteFiltroInput] = None) -> list[Expediente]:
        info.context.requerir_usuario()
        filtro = filtro or ExpedienteFiltroInput()
        filtro_pydantic = ExpedienteFiltro(
            cl_expediente=filtro.cl_expediente,
            fecha_inicio=filtro.fecha_inicio,
            fecha_fin=filtro.fecha_fin,
            cl_servicio=filtro.cl_servicio,
            cl_subservicio=filtro.cl_subservicio,
            cuentas=filtro.cuentas,
        )
        try:
            resultados = expedientes_repo.listar_expedientes(filtro_pydantic)
        except ValueError as e:
            raise Exception(str(e))
        return [Expediente.from_pydantic(r) for r in resultados]

    @strawberry.field(description="Combo Servicio. Requiere sesión.")
    def servicios(self, info: strawberry.Info, cl_servicio: int = 4) -> list[CatalogoItem]:
        info.context.requerir_usuario()
        return [CatalogoItem.from_pydantic(c) for c in catalogos_repo.listar_servicios(cl_servicio)]

    @strawberry.field(description="Combo Subservicio. Requiere sesión.")
    def subservicios(self, info: strawberry.Info, cl_servicio: int = 4) -> list[CatalogoItem]:
        info.context.requerir_usuario()
        return [CatalogoItem.from_pydantic(c) for c in catalogos_repo.listar_subservicios(cl_servicio)]

    @strawberry.field(description="Combo Cuenta / Cuenta Específica. Requiere sesión.")
    def cuentas(self, info: strawberry.Info) -> list[CatalogoItem]:
        info.context.requerir_usuario()
        return [CatalogoItem.from_pydantic(c) for c in catalogos_repo.listar_cuentas()]

    @strawberry.field(description="Typeahead de cuentas (Configuración Cuentas, mín. 3 letras). Requiere sesión.")
    def buscar_cuentas(self, info: strawberry.Info, texto: str) -> list[CuentaBusqueda]:
        info.context.requerir_usuario()
        if len(texto) < 3 or not all(ch.isalpha() or ch.isspace() for ch in texto):
            return []
        return [CuentaBusqueda(cl_cuenta=c["cl_cuenta"], nombre=c["nombre"]) for c in catalogos_repo.buscar_cuentas(texto)]

    @strawberry.field(description="Grid de la pantalla Configuración Cuentas. Requiere sesión.")
    def cuentas_configuradas(self, info: strawberry.Info) -> list[CuentaConfigurada]:
        info.context.requerir_usuario()
        return [CuentaConfigurada(cl_cuenta=c["cl_cuenta"], nombre=c["nombre"]) for c in cuentas_config_repo.listar_cuentas_configuradas()]
