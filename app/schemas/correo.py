from typing import Literal

from pydantic import BaseModel, Field

# Tope de expedientes por operación. Tanto el corte como el envío de correo
# recorren la lista haciendo una consulta al SP por cada expediente: sin un
# máximo, un body con cientos de miles de claves deja al servidor trabajando
# indefinidamente (CWE-606, iteraciones sin límite). El número es holgado
# frente a lo que se puede marcar en pantalla, incluso con "seleccionar
# todo" sobre el rango máximo de búsqueda (3 meses).
MAXIMO_EXPEDIENTES_POR_OPERACION = 2000


class EnviarCorreoProveedoresInput(BaseModel):
    """Body de POST /expedientes/enviar-correo-proveedores."""

    expedientes: list[int] = Field(..., min_length=1, max_length=MAXIMO_EXPEDIENTES_POR_OPERACION)


class EnviarCorreoProveedoresResponse(BaseModel):
    enviados: int
    expedientes: list[int]


class GenerarCorteInput(BaseModel):
    """Body de POST /expedientes/corte."""

    expedientes: list[int] = Field(..., min_length=1, max_length=MAXIMO_EXPEDIENTES_POR_OPERACION)
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


class CorreoEnviadoRegistro(BaseModel):
    """Una fila del historial de 'Enviar correo a proveedores' (panel de Administrador)."""

    id: int
    tipo: Literal["nuevo", "recordatorio"]
    destinatario: str
    expedientes: list[int]
    rfc_envio: str
    nombre_envio: str
    simulado: bool
    fecha: str
