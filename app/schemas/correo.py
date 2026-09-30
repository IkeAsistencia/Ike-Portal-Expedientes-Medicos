from typing import Literal

from pydantic import BaseModel, Field


class EnviarCorreoProveedoresInput(BaseModel):
    """Body de POST /expedientes/enviar-correo-proveedores."""

    expedientes: list[int] = Field(..., min_length=1)


class EnviarCorreoProveedoresResponse(BaseModel):
    enviados: int
    expedientes: list[int]


class GenerarCorteInput(BaseModel):
    """Body de POST /expedientes/corte."""

    expedientes: list[int] = Field(..., min_length=1)
    tipo_expediente: Literal["normal", "anticipado"] = "normal"


class GenerarCorteResponse(BaseModel):
    corte_id: int
    archivo_nombre: str
    total: int
    expedientes: list[int]


class EnviarCorteResponse(BaseModel):
    enviados: int
    simulado: bool
    destinatario: str
