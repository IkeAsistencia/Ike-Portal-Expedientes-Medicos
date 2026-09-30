"""
Tipos GraphQL de salida (lo que el cliente puede consultar).

Se generan a partir de los modelos Pydantic ya existentes en
app/schemas/, usando la integración nativa de Strawberry con Pydantic
(strawberry.experimental.pydantic). Así evitamos mantener dos
definiciones separadas de "qué es un Expediente" — la fuente de verdad
sigue siendo app/schemas/expediente.py.

Cada tipo generado así trae, gratis, un método .from_pydantic(instancia)
para convertir el modelo Pydantic que ya regresan los repositorios.
"""

import strawberry
import strawberry.experimental.pydantic as sp

from app.schemas.auth import LoginResponse as LoginResponsePydantic
from app.schemas.catalogo import CatalogoItem as CatalogoItemPydantic
from app.schemas.catalogo import CuentaBusqueda as CuentaBusquedaPydantic
from app.schemas.correo import EnviarCorreoProveedoresResponse as EnviarCorreoResponsePydantic
from app.schemas.expediente import Expediente as ExpedientePydantic

# El enum de estatus se reutiliza tal cual (mismos valores: "Abierto", etc.)
from app.schemas.expediente import EstatusExpediente

EstatusExpedienteGQL = strawberry.enum(EstatusExpediente, name="EstatusExpediente")


@sp.type(model=ExpedientePydantic, all_fields=True)
class Expediente:
    """Una fila del listado de la pantalla Expedientes."""


@sp.type(model=CatalogoItemPydantic, all_fields=True)
class CatalogoItem:
    """Item genérico de catálogo (Servicio, Subservicio, Cuenta)."""


@sp.type(model=CuentaBusquedaPydantic, all_fields=True)
class CuentaBusqueda:
    """Resultado del typeahead de cuentas (Configuración Cuentas)."""


@sp.type(model=LoginResponsePydantic, all_fields=True)
class LoginResult:
    """Resultado de la mutation login."""


@sp.type(model=EnviarCorreoResponsePydantic, all_fields=True)
class EnviarCorreoResultado:
    """Resultado de la mutation enviarCorreoProveedores."""


@strawberry.type
class CuentaConfigurada:
    """Una fila del grid de la pantalla Configuración Cuentas (dato local, no viene de un modelo Pydantic dedicado)."""

    cl_cuenta: int
    nombre: str


@strawberry.type
class OperacionOk:
    """Resultado genérico para mutations que solo confirman éxito (eliminar, limpiar, actualizar estatus)."""

    ok: bool
    mensaje: str = ""
