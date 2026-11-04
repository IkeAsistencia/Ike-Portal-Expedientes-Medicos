from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import usuario_actual
from app.repositories import accesos_repo, correos_enviados_repo
from app.schemas.correo import CorreoEnviadoRegistro, CuotaCorreos
from app.services import cuota_correos_service

router = APIRouter(prefix="/correos-enviados", tags=["Historial de correos"])


def _requerir_administrador(usuario: dict) -> None:
    if usuario.get("perfil") != accesos_repo.PERFIL_ADMINISTRADOR:
        raise HTTPException(403, "Esta sección es exclusiva del perfil Administrador.")


@router.get("/cuota", response_model=CuotaCorreos)
def cuota_de_hoy(usuario: dict = Depends(usuario_actual)):
    """
    Contador "Correos de hoy: X de 100" que ven Cabina (junto a "Enviar
    correo a proveedores") y Administrador (al enviar el corte). Proveedor
    no envía correos, así que no lo necesita.
    """
    if usuario.get("perfil") == accesos_repo.PERFIL_PROVEEDOR:
        raise HTTPException(403, "El perfil Proveedor no tiene acceso a esta sección.")
    return cuota_correos_service.estado().como_dict()


@router.get("", response_model=list[CorreoEnviadoRegistro])
def listar_correos_enviados(
    cl_expediente: Optional[int] = Query(default=None, description="Filtra por un expediente en concreto"),
    usuario: dict = Depends(usuario_actual),
):
    """
    Panel de Administrador: historial de "Enviar correo a proveedores" --
    quién lo mandó, a quién, cuándo y de qué expediente(s). Evidencia para
    cuando un proveedor dice que nunca se le notificó.
    """
    _requerir_administrador(usuario)
    return correos_enviados_repo.listar(cl_expediente=cl_expediente)
