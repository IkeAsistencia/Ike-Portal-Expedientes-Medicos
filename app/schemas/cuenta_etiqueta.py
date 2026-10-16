"""
Etiqueta de color y prefijo por cuenta (módulo "Colores de Cuentas", solo
Administrador). El color es una clave de la paleta fija de abajo, no un hex
libre: así el frontend solo necesita una clase CSS por clave y nadie puede
meter un valor raro que se pinte tal cual.
"""
import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator

# Paleta en tonos pastel (los estilos viven en frontend/css/componentes.css,
# clases .cta-<clave>). Se evitaron el rojo, naranja y amarillo puros para no
# confundirse con el semáforo ni con los badges de Estado.
PALETA = [
    {"clave": "rosa", "nombre": "Rosa"},
    {"clave": "fucsia", "nombre": "Fucsia"},
    {"clave": "morado", "nombre": "Morado"},
    {"clave": "azul", "nombre": "Azul"},
    {"clave": "celeste", "nombre": "Celeste"},
    {"clave": "turquesa", "nombre": "Turquesa"},
    {"clave": "verde", "nombre": "Verde"},
    {"clave": "arena", "nombre": "Arena"},
    {"clave": "gris", "nombre": "Gris"},
]
COLORES_VALIDOS = {c["clave"] for c in PALETA}

LARGO_MAXIMO_PREFIJO = 12
_PATRON_PREFIJO = re.compile(r"^[A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ .\-]*$")
MENSAJE_PREFIJO = (
    f"El prefijo admite hasta {LARGO_MAXIMO_PREFIJO} caracteres: letras, números, espacio, punto y guion."
)


class CuentaEtiquetaInput(BaseModel):
    cl_cuenta: int = Field(..., ge=1)
    nombre: str = Field(..., min_length=1, max_length=200)
    prefijo: str = Field("", max_length=LARGO_MAXIMO_PREFIJO)
    color: str = Field(..., min_length=1, max_length=20)

    @field_validator("prefijo")
    @classmethod
    def _prefijo_valido(cls, v: str) -> str:
        v = v.strip()
        if not _PATRON_PREFIJO.match(v):
            raise ValueError(MENSAJE_PREFIJO)
        return v

    @field_validator("color")
    @classmethod
    def _color_valido(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in COLORES_VALIDOS:
            raise ValueError("Color inválido: elige uno de la paleta.")
        return v


class CuentaEtiquetaRegistro(BaseModel):
    cl_cuenta: int
    nombre: str
    prefijo: str
    color: str
    actualizado: Optional[str] = None
    actualizado_por: Optional[str] = None


class ColorPaleta(BaseModel):
    clave: str
    nombre: str
