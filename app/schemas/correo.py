from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.services.validacion_rfc_cedula_service import DatoInvalido, revisar_correo

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
    # Cerca del tope diario (o ya sin lugar), el primer intento NO envía nada:
    # regresa requiere_confirmacion=True y el aviso. Quien envía lo lee y, si
    # está de acuerdo, vuelve a mandar la misma selección con esto en True.
    confirmar_limite: bool = False


class EnviarCorreoProveedoresResponse(BaseModel):
    # Expedientes procesados (pasaron a "En Espera de Respuesta"), haya salido
    # correo o no. 0 cuando requiere_confirmacion=True (no se hizo nada).
    enviados: int
    expedientes: list[int]
    correo_enviado: bool = False
    # 'limite' | 'sin_proveedores' cuando no salió correo; None si sí salió.
    motivo_sin_correo: Optional[str] = None
    # A cuántos proveedores les llegó (o les habría llegado) el correo.
    destinatarios: int = 0
    # Entidades de la selección sin ningún proveedor activo dado de alta.
    entidades_sin_proveedor: list[str] = []
    requiere_confirmacion: bool = False
    # Texto listo para mostrar: el aviso a confirmar o el resultado del envío.
    mensaje: str = ""
    simulado: bool = False
    usados_hoy: int = 0
    limite_diario: int = 0


class GenerarCorteInput(BaseModel):
    """Body de POST /expedientes/corte."""

    expedientes: list[int] = Field(..., min_length=1, max_length=MAXIMO_EXPEDIENTES_POR_OPERACION)
    tipo_expediente: Literal["normal", "anticipado"] = "normal"


class GenerarCorteResponse(BaseModel):
    corte_id: int
    archivo_nombre: str
    total: int
    expedientes: list[int]


class EnviarCorteInput(BaseModel):
    """Body de POST /expedientes/corte/{id}/enviar: UNA sola dirección."""

    destinatario: str = Field(..., max_length=120)

    @field_validator("destinatario")
    @classmethod
    def _validar_destinatario(cls, v: str) -> str:
        try:
            return revisar_correo(v)
        except DatoInvalido as e:
            raise ValueError(str(e)) from e


class EnviarCorteResponse(BaseModel):
    enviados: int
    simulado: bool
    destinatario: str


class CuotaCorreos(BaseModel):
    """GET /correos-enviados/cuota: cuántos correos van hoy contra el tope."""

    usados: int
    limite: int
    aviso: int
    restantes: int
    nivel: Literal["normal", "aviso", "agotado"]
    reenvio_horas: int


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
    motivo_sin_correo: Optional[str] = None
