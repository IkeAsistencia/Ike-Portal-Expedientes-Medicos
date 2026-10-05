"""
Tipos GraphQL de entrada (lo que el cliente manda como argumento).
"""

from datetime import date
from typing import Optional

import strawberry

from app.graphql.types import EstatusExpedienteGQL


@strawberry.input
class ExpedienteFiltroInput:
    cl_expediente: Optional[int] = None
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None
    cl_servicio: Optional[int] = None
    cl_subservicio: Optional[int] = None
    cuentas: Optional[list[int]] = None


@strawberry.input
class LoginInput:
    usuario: str
    password: str


@strawberry.input
class SeguimientoInput:
    cl_expediente: int
    comentario: str


@strawberry.input
class EstatusInput:
    cl_expediente: int
    estatus: EstatusExpedienteGQL


@strawberry.input
class CuentaConfigInput:
    cl_cuenta: int
    nombre: str


@strawberry.input
class EnviarCorreoProveedoresInput:
    expedientes: list[int]
