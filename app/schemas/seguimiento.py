from typing import Literal, Optional

from pydantic import BaseModel, Field


class SeguimientoInput(BaseModel):
    """
    Body del POST /seguimiento/actualizar (botón 'Actualizar en SISE').
    El clUsrApp NO va aquí: se toma del usuario autenticado (token JWT).

    tipo_expediente: lo determina el frontend según desde qué pantalla se
    abrió el expediente ("normal" = Expedientes, "anticipado" = Pago
    Anticipado) -- por ahora ambas pantallas jalan los mismos datos de SISE,
    en lo que se configura un campo/consulta real que los distinga.
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
    comentario: str
    origen: str = "proveedor"
    fecha: str


class ComprobanteMeta(BaseModel):
    """Metadatos del comprobante de pago (sin el contenido del archivo)."""

    rfc: str
    nombre_archivo: str
    tipo_mime: str
    fecha: str
