"""
Reglas para agendar una cita: SIEMPRE es para un expediente.

Se llega por dos caminos y los dos terminan igual (regresan a Seguimiento del
expediente con los datos de la cita copiados en Observaciones):
  - "Coordinar cita" en Seguimiento: el expediente ya viene elegido.
  - Desde el Directorio de Proveedores por el menú: al presionar "Agendar" se
    elige el expediente (ver expedientes_para_cita).

Reglas:
  - Coordinan los perfiles Proveedor y Administrador (los dos registran
    seguimiento; Cabina no usa el directorio).
  - El expediente tiene que seguir en una etapa en la que se puede actuar:
    "En Espera de Respuesta" o "Seguimiento de Cita" -- las mismas que
    habilitan "Registrar seguimiento" al Proveedor (ver seguimiento_service.py).
  - El paciente sale del expediente, no de lo que mande el navegador.
  - Un expediente tiene UNA sola cita activa; para cambiarla primero se cancela.
"""

from fastapi import HTTPException

from app.repositories import accesos_repo, citas_proveedor_repo, estatus_repo, expedientes_repo
from app.schemas.expediente import EstatusExpediente, Expediente, ExpedienteFiltro

ESTATUS_PARA_COORDINAR = (EstatusExpediente.EN_ESPERA_RESPUESTA, EstatusExpediente.SEGUIMIENTO_CITA)
PERFILES_QUE_COORDINAN = (accesos_repo.PERFIL_PROVEEDOR, accesos_repo.PERFIL_ADMINISTRADOR)


def exigir_perfil_que_coordina(usuario: dict) -> None:
    if usuario.get("perfil") not in PERFILES_QUE_COORDINAN:
        raise HTTPException(403, "Agendar citas es exclusivo de los perfiles Proveedor y Administrador.")


def expediente_para_coordinar(cl_expediente: int, usuario: dict) -> Expediente:
    """Regresa el expediente si se le puede coordinar cita; si no, lanza el
    error con un mensaje listo para mostrarse."""
    exigir_perfil_que_coordina(usuario)
    encontrados = expedientes_repo.listar_expedientes(ExpedienteFiltro(cl_expediente=cl_expediente))
    if not encontrados:
        raise HTTPException(404, "No se encontró el expediente.")
    expediente = encontrados[0]
    if expediente.estatus not in ESTATUS_PARA_COORDINAR:
        raise HTTPException(
            400, "Este expediente ya no está en espera de respuesta, no puedes coordinar ni cambiar su cita."
        )
    return expediente


def expedientes_para_cita(usuario: dict) -> list[Expediente]:
    """
    Los expedientes a los que se les puede agendar cita ahora: en estatus
    accionable y sin una cita activa. Es la lista del paso "¿Para qué
    expediente?" del Directorio.

    El estatus vive en la base local, así que de ahí salen los candidatos. Sus
    datos (paciente, especialidad, zona) vienen del sistema central: primero
    con UNA consulta del rango por default (los últimos meses, igual que la
    pantalla Expedientes) y, solo para los que no hayan salido ahí (más
    viejos), uno por uno.
    """
    exigir_perfil_que_coordina(usuario)
    candidatos = estatus_repo.expedientes_en_estatus(ESTATUS_PARA_COORDINAR)
    candidatos -= citas_proveedor_repo.expedientes_con_cita_activa()
    if not candidatos:
        return []

    encontrados = {
        e.expediente: e
        for e in expedientes_repo.listar_expedientes(ExpedienteFiltro())
        if e.expediente in candidatos
    }
    for cl in candidatos - encontrados.keys():
        uno = expedientes_repo.listar_expedientes(ExpedienteFiltro(cl_expediente=cl))
        if uno:
            encontrados[cl] = uno[0]

    # El estatus se vuelve a revisar con el dato ya armado (pudo cambiar entre
    # las dos lecturas). Los más recientes primero.
    return sorted(
        (e for e in encontrados.values() if e.estatus in ESTATUS_PARA_COORDINAR),
        key=lambda e: e.expediente,
        reverse=True,
    )
