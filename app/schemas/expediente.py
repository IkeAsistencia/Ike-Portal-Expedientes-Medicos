from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict


class EstatusExpediente(str, Enum):
    ABIERTO = "Abierto"
    EN_ESPERA_RESPUESTA = "En Espera de Respuesta"  # automático: Cabina mandó correo. No editable a mano.
    SEGUIMIENTO_PROVEEDOR = "Seguimiento Proveedor"  # automático: Proveedor dejó un comentario (Actualizar Core).
    SEGUIMIENTO_CITA = "Seguimiento de Cita"  # Cabina regresa el expediente de pago anticipado ya con cita aceptada.
    SEGUIMIENTO_COORDINADOR = "Finalizado"


class Expediente(BaseModel):
    """
    Representa una fila del listado de la pantalla Expedientes.
    Refleja el query actualizado de dbo.ST_CP_ObtenerExpedientesSinProveedorMedico.
    """

    model_config = ConfigDict(populate_by_name=True)

    expediente: int
    cuenta: str
    tipo_servicio: str
    tipo_subservicio: str
    nombre_titular: Optional[str] = None
    # Optional: dbo.ST_CP_ObtenerExpedientesSinProveedorMedico ahora hace LEFT JOIN
    # (antes INNER) a S2_ReferciasMedicas / s2_cPuntoVision / Check_Up según
    # el clSubServicio del expediente -- si no hay fila en la fuente que le
    # toca, estos 4 campos llegan en NULL (ver sql/01_..._Medico.sql).
    nombre_paciente: Optional[str] = None
    especialidad: Optional[str] = None
    entidad: Optional[str] = None
    municipio: Optional[str] = None
    fecha_apertura_servicio: date
    fecha_asignacion_proveedor: Optional[date] = None
    fecha_cita: Optional[date] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    # No viene de SQL Server: se resuelve desde la base local (ver estatus_repo.py)
    estatus: EstatusExpediente = EstatusExpediente.ABIERTO


class ExpedienteFiltro(BaseModel):
    """Filtros de la tarjeta 'Filtros' de la pantalla Expedientes."""

    cl_expediente: Optional[int] = None
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None
    cl_servicio: Optional[int] = None
    cl_subservicio: Optional[int] = None
    cuentas: Optional[list[int]] = None  # una o varias claves de cuenta
