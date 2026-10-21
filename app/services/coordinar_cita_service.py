"""
Reglas de "Coordinar cita" (botón del Proveedor en Seguimiento): una cita que
se agenda DESDE un expediente.

Lo que cambia respecto a agendar una cita suelta en el directorio:
  - Solo el perfil Proveedor coordina (es quien registra el seguimiento).
  - El expediente tiene que seguir en una etapa en la que el Proveedor puede
    actuar: "En Espera de Respuesta" o "Seguimiento de Cita" -- las mismas que
    habilitan "Registrar seguimiento" (ver seguimiento_service.py).
  - El paciente sale del expediente, no de lo que mande el navegador.
  - Un expediente tiene UNA sola cita activa; para cambiarla primero se cancela.
"""

from fastapi import HTTPException

from app.repositories import accesos_repo, expedientes_repo
from app.schemas.expediente import EstatusExpediente, Expediente, ExpedienteFiltro

ESTATUS_PARA_COORDINAR = (EstatusExpediente.EN_ESPERA_RESPUESTA, EstatusExpediente.SEGUIMIENTO_CITA)


def exigir_proveedor(usuario: dict) -> None:
    if usuario.get("perfil") != accesos_repo.PERFIL_PROVEEDOR:
        raise HTTPException(403, "Coordinar una cita desde un expediente es exclusivo del perfil Proveedor.")


def expediente_para_coordinar(cl_expediente: int, usuario: dict) -> Expediente:
    """Regresa el expediente si el Proveedor puede coordinarle cita; si no,
    lanza el error con un mensaje listo para mostrarse."""
    exigir_proveedor(usuario)
    encontrados = expedientes_repo.listar_expedientes(ExpedienteFiltro(cl_expediente=cl_expediente))
    if not encontrados:
        raise HTTPException(404, "No se encontró el expediente.")
    expediente = encontrados[0]
    if expediente.estatus not in ESTATUS_PARA_COORDINAR:
        raise HTTPException(
            400, "Este expediente ya no está en espera de respuesta, no puedes coordinar ni cambiar su cita."
        )
    return expediente
