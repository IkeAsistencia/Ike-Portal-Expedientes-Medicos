from typing import Literal, Optional

from pydantic import BaseModel, Field


class SeguimientoInput(BaseModel):
    """
    Body del POST /seguimiento/actualizar (botón 'Actualizar Core').
    El clUsrApp NO va aquí: se toma del usuario autenticado (token JWT).

    tipo_expediente: ya no se usa para decidir si el comprobante es
    obligatorio (ver pago_anticipado_repo.py) -- se deja solo por
    compatibilidad, sin efecto en el router.
    """

    cl_expediente: int
    comentario: str = Field(..., min_length=1, max_length=1500)
    tipo_expediente: Literal["normal", "anticipado"] = "normal"


class EstatusInput(BaseModel):
    """Body del POST /seguimiento/estatus (cambio de estatus, solo-app)."""

    cl_expediente: int
    estatus: str  # se valida contra EstatusExpediente en el router
    # Obligatorio cuando Cabina regresa el expediente a Proveedor (estatus
    # "En Espera de Respuesta"): el motivo del regreso, ver router.
    comentario: Optional[str] = Field(default=None, max_length=1500)


class ComentarioSeguimiento(BaseModel):
    """
    Copia local de cada comentario registrado en Core: los del Proveedor
    ('Actualizar Core') y los del Coordinador de Cabina ('Regresar a
    Proveedor'). Se guarda aparte para poder consultarlos en modo lectura
    sin depender de leer Core directamente.
    """

    rfc: str
    nombre: str  # nombre de quien lo escribió (o su RFC si ya no está dado de alta)
    comentario: str
    origen: str = "proveedor"
    fecha: str


class ComprobanteMeta(BaseModel):
    """Metadatos del comprobante de pago (sin el contenido del archivo)."""

    rfc: str
    nombre_archivo: str
    tipo_mime: str
    fecha: str


class PagoAnticipadoInput(BaseModel):
    """Body del POST /seguimiento/pago-anticipado/{cl_expediente}."""

    es_anticipado: bool


class PagoAnticipadoResponse(BaseModel):
    es_anticipado: bool
    bloqueado: bool


class SeguimientoFalloLocal(BaseModel):
    """
    Bitácora PROPIA del portal (tabla seguimiento_core_fallidos): intentos
    de 'Actualizar Core' / 'Regresar a Proveedor' que no se pudieron
    insertar en dbo.Seguimiento por un error de base de datos -- ver
    app/repositories/seguimiento_repo.py:registrar_fallo_local.
    """

    id: int
    cl_expediente: int
    observaciones: str
    cl_usr_app: Optional[int] = None
    nombre: Optional[str] = None
    error: Optional[str] = None
    fecha: str


class SeguimientoSiseItem(BaseModel):
    """
    Una fila del resultado de dbo.sp_S2_Seguimiento (bitácora de Core/SISE
    para el expediente). El SP también regresa 'Accion' y 'CSSRow' (usados
    por la pantalla original de SISE para botones/estilo de fila) -- no se
    exponen aquí, no aplican al portal.
    """

    fecha: Optional[str] = None
    estatus: Optional[str] = None
    proveedor: Optional[str] = None
    nombre: Optional[str] = None
    observaciones: Optional[str] = None
