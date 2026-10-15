from datetime import datetime
from enum import Enum

from app.db.local_store import ahora_local
from app.schemas.expediente import EstatusExpediente

FORMATO_FECHA_LOCAL = "%Y-%m-%d %H:%M:%S"


class ColorSemaforo(str, Enum):
    VERDE = "verde"
    AMARILLO = "amarillo"
    NARANJA = "naranja"
    ROJO = "rojo"


# Grupos de subservicio según "Puntos a modificar.docx" (Cabina Médica,
# octubre 2026). "Dental" y las consultas de primer contacto por
# especialidad (medicina interna, pediatría, medicina general,
# ginecología) se piden explícitamente dejar fuera por ahora -- "no están
# identificadas" (no tienen un clSubServicio propio todavía).
#
# Servicios de primer contacto y específicos (226/377/420/432).
GRUPO_PRIMER_CONTACTO = frozenset({226, 377, 420, 432})
# Servicios de segundo contacto -- 383 "Consulta Médica en Consultorio" es
# el que el documento describe como "todos los casos que no estén
# contemplados en la clasificación de primer contacto".
GRUPO_SEGUNDO_CONTACTO = frozenset({383, 376, 404, 403})

# Horas desde FechaApertura, mientras el expediente sigue "Abierto" (aún no
# se ha escalado a un proveedor).
_HORAS_PRIMER_CONTACTO = {"amarillo": 6, "naranja": 12, "rojo": 24}
_HORAS_SEGUNDO_CONTACTO = {"amarillo": 12, "naranja": 48, "rojo": 72}

# Minutos desde que el expediente pasó a "En Espera de Respuesta" (se le
# mandó el correo al proveedor), independiente del subservicio.
_MINUTOS_ESCALACION_NARANJA = 120
_MINUTOS_ESCALACION_ROJO = 180

# Estatus en los que ya hay respuesta/avance del proveedor o del coordinador
# -- el semáforo de "sin atender" ya no aplica (ver sección 1 del
# documento: el color es sobre el Expediente mientras está pendiente).
_ESTATUS_SIN_SEMAFORO = (
    EstatusExpediente.SEGUIMIENTO_PROVEEDOR,
    EstatusExpediente.SEGUIMIENTO_CITA,
    EstatusExpediente.SEGUIMIENTO_COORDINADOR,
)


def _horas_desde(fecha: datetime) -> float:
    ahora = datetime.strptime(ahora_local(), FORMATO_FECHA_LOCAL)
    return (ahora - fecha).total_seconds() / 3600


def _minutos_desde(fecha_texto: str) -> float:
    ahora = datetime.strptime(ahora_local(), FORMATO_FECHA_LOCAL)
    fecha = datetime.strptime(fecha_texto, FORMATO_FECHA_LOCAL)
    return (ahora - fecha).total_seconds() / 60


def _color_por_umbrales(valor: float, umbrales: dict) -> ColorSemaforo:
    if valor < umbrales["amarillo"]:
        return ColorSemaforo.VERDE
    if valor < umbrales["naranja"]:
        return ColorSemaforo.AMARILLO
    if valor < umbrales["rojo"]:
        return ColorSemaforo.NARANJA
    return ColorSemaforo.ROJO


def calcular_color(
    cl_sub_servicio: int,
    estatus: EstatusExpediente,
    fecha_apertura: datetime,
    fecha_cambio_estatus: str | None,
) -> ColorSemaforo | None:
    """
    Semáforo del Expediente (distinto del badge de Estado): ver sección 1
    y 2 de "Puntos a modificar.docx". Se calcula en el momento de cada
    consulta -- no se guarda ningún color en la base, así que siempre
    refleja el tiempo transcurrido real ("semáforo dinámico").

    - Mientras el expediente sigue "Abierto" (sin escalar a proveedor):
      colores por hora desde FechaApertura, según el grupo de su
      subservicio (primer o segundo contacto).
    - En cuanto pasa a "En Espera de Respuesta" (se mandó a proveedor):
      colores por minuto desde ESE cambio de estatus (verde/naranja/rojo,
      sin amarillo en esta fase).
    - De ahí en adelante (ya hay respuesta o el coordinador avanzó el
      caso) no aplica semáforo -- regresa None.
    """
    if estatus in _ESTATUS_SIN_SEMAFORO:
        return None

    if estatus == EstatusExpediente.EN_ESPERA_RESPUESTA:
        if not fecha_cambio_estatus:
            return ColorSemaforo.VERDE
        minutos = _minutos_desde(fecha_cambio_estatus)
        if minutos <= _MINUTOS_ESCALACION_NARANJA:
            return ColorSemaforo.VERDE
        if minutos <= _MINUTOS_ESCALACION_ROJO:
            return ColorSemaforo.NARANJA
        return ColorSemaforo.ROJO

    # Abierto (o cualquier otro estatus no contemplado arriba): reglas por
    # grupo de subservicio, horas desde la apertura del expediente.
    if cl_sub_servicio in GRUPO_PRIMER_CONTACTO:
        umbrales = _HORAS_PRIMER_CONTACTO
    elif cl_sub_servicio in GRUPO_SEGUNDO_CONTACTO:
        umbrales = _HORAS_SEGUNDO_CONTACTO
    else:
        # No debería pasar -- el SP solo trae estos 8 subservicios -- pero
        # si algún día se agrega uno nuevo sin clasificar, mejor no
        # inventar un color que confunda al usuario.
        return None

    return _color_por_umbrales(_horas_desde(fecha_apertura), umbrales)


def _formato_duracion(minutos: float) -> str:
    """Texto corto del tiempo transcurrido: '45 min', '13 h 20 min', '2 d 3 h'."""
    minutos = max(0, int(minutos))
    if minutos < 60:
        return f"{minutos} min"
    horas, resto = divmod(minutos, 60)
    if horas < 24:
        return f"{horas} h {resto} min" if resto else f"{horas} h"
    dias, horas = divmod(horas, 24)
    return f"{dias} d {horas} h" if horas else f"{dias} d"


def tiempo_transcurrido(
    estatus: EstatusExpediente,
    fecha_apertura: datetime,
    fecha_cambio_estatus: str | None,
) -> str | None:
    """
    Texto del tiempo que lleva el expediente en la etapa que mide el
    semáforo (el mismo que usa calcular_color): desde la apertura mientras
    está "Abierto", desde que se mandó al proveedor en "En Espera de
    Respuesta". None donde no aplica semáforo.
    """
    if estatus in _ESTATUS_SIN_SEMAFORO:
        return None
    if estatus == EstatusExpediente.EN_ESPERA_RESPUESTA:
        if not fecha_cambio_estatus:
            return None
        return _formato_duracion(_minutos_desde(fecha_cambio_estatus))
    return _formato_duracion(_horas_desde(fecha_apertura) * 60)
