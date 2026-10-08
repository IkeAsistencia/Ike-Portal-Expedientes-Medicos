from typing import Optional

from pydantic import BaseModel, Field


class OpenRouterPromptInput(BaseModel):
    """Body de POST /openrouter: dispara una llamada real a OpenRouter."""

    mensaje: str = Field(..., min_length=1, max_length=8000)
    # Si no se manda, usa OPENROUTER_MODELO_DEFAULT (ver app/config.py).
    modelo: Optional[str] = None
    # Para qué se usó esta llamada (ej. "resumen expediente 1001") -- queda
    # guardado junto con el consumo, para poder identificarlo después en el reporte.
    descripcion: Optional[str] = Field(default=None, max_length=300)


class OpenRouterRespuesta(BaseModel):
    contenido: str
    modelo: str
    tokens_entrada: int
    tokens_salida: int
    tokens_totales: int
    costo_usd: float


class IteracionOpenRouter(BaseModel):
    """Una fila de la bitácora local (tabla openrouter_iteraciones)."""

    id: int
    fecha: str
    modelo: str
    descripcion: Optional[str] = None
    identificador: Optional[str] = None
    tokens_entrada: int
    tokens_salida: int
    tokens_totales: int
    costo_usd: float


class DesgloseModeloOpenRouter(BaseModel):
    modelo: str
    peticiones: int
    tokens_entrada: int
    tokens_salida: int
    tokens_totales: int
    costo_usd: float


class DesgloseDiaOpenRouter(BaseModel):
    fecha: str  # YYYY-MM-DD
    peticiones: int
    tokens_entrada: int
    tokens_salida: int
    tokens_totales: int
    costo_usd: float


class ReporteOpenRouter(BaseModel):
    """GET /openrouter/reporte: lo mínimo para auditar consumo y costo."""

    desde: Optional[str] = None
    hasta: Optional[str] = None
    total_peticiones: int
    tokens_entrada: int
    tokens_salida: int
    tokens_totales: int
    costo_total_usd: float
    costo_promedio_usd: float
    por_modelo: list[DesgloseModeloOpenRouter]
    por_dia: list[DesgloseDiaOpenRouter]
    # Las N peticiones de mayor consumo/costo, para encontrar outliers rápido.
    mayor_consumo_tokens: list[IteracionOpenRouter]
    mayor_costo: list[IteracionOpenRouter]
