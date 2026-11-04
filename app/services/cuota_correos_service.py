"""
Tope diario de correos del portal.

La cuenta de correo que nos asignaron permite SMTP_LIMITE_DIARIO envíos al
día (100). El tope es uno solo para todo el portal: "Enviar correo a
proveedores" (Cabina) y el envío del corte (Administrador) lo comparten.

  - Cada correo que sale aparta su parte del tope ANTES de mandarse
    (correos_salientes_repo.reservar). Si no cabe, no se manda.
  - Cuánto cuenta un correo depende de SMTP_CUENTA_POR_DESTINATARIO: 1 por
    destinatario (lo más seguro, mientras no se confirme cómo cuenta el
    servidor) o 1 por mensaje.
  - Los envíos simulados (sin SMTP configurado, en local) también cuentan,
    para que el contador se pueda probar sin mandar correos reales.
  - El día se corta a medianoche del centro de México. Se usa UTC-6 fijo:
    México dejó el horario de verano en 2022, y así no depende de la zona
    horaria del servidor (en AWS suele estar en UTC).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.config import get_settings
from app.repositories import correos_salientes_repo

_HORA_CENTRO_MEXICO = timezone(timedelta(hours=-6))

NIVEL_NORMAL = "normal"
NIVEL_AVISO = "aviso"
NIVEL_AGOTADO = "agotado"


def dia_actual() -> str:
    return datetime.now(_HORA_CENTRO_MEXICO).strftime("%Y-%m-%d")


@dataclass
class EstadoCuota:
    usados: int
    limite: int
    aviso: int

    @property
    def restantes(self) -> int:
        return max(self.limite - self.usados, 0)

    @property
    def nivel(self) -> str:
        if self.usados >= self.limite:
            return NIVEL_AGOTADO
        if self.usados >= self.aviso:
            return NIVEL_AVISO
        return NIVEL_NORMAL

    def como_dict(self) -> dict:
        return {
            "usados": self.usados,
            "limite": self.limite,
            "aviso": self.aviso,
            "restantes": self.restantes,
            "nivel": self.nivel,
            "reenvio_horas": get_settings().correo_reenvio_horas,
        }


def estado() -> EstadoCuota:
    settings = get_settings()
    return EstadoCuota(
        usados=correos_salientes_repo.usados_del_dia(dia_actual()),
        limite=settings.smtp_limite_diario,
        aviso=settings.smtp_aviso_limite,
    )


def unidades_para(destinatarios: int) -> int:
    """Cuánto gasta del tope un correo con ese número de destinatarios."""
    if destinatarios <= 0:
        return 0
    return destinatarios if get_settings().smtp_cuenta_por_destinatario else 1


def reservar(origen: str, unidades: int) -> int | None:
    """Aparta `unidades` del tope de hoy. None si ya no caben."""
    settings = get_settings()
    return correos_salientes_repo.reservar(
        dia_actual(), origen, unidades, settings.smtp_limite_diario, simulado=not settings.smtp_configurado
    )


def liberar(reserva_id: int) -> None:
    correos_salientes_repo.liberar(reserva_id)
