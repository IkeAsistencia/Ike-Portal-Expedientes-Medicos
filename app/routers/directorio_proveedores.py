from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.security import usuario_actual
from app.repositories import citas_proveedor_repo, proveedores_repo
from app.repositories.accesos_repo import PERFIL_CABINA
from app.services import agenda_proveedores_service


def _requerir_proveedor_o_administrador(usuario: dict = Depends(usuario_actual)) -> dict:
    """El Directorio de Proveedores (pantalla "Proveedores", ver
    frontend/js/directorio/*.js) es para los perfiles Proveedor y
    Administrador -- Cabina no lo usa (mismo criterio que
    pantallaPermitida("directorio-proveedores") en frontend/js/app.js)."""
    if usuario.get("perfil") == PERFIL_CABINA:
        raise HTTPException(403, "El Directorio de Proveedores no aplica para el perfil Cabina.")
    return usuario


router = APIRouter(
    prefix="/directorio-proveedores",
    tags=["Directorio de Proveedores"],
    dependencies=[Depends(_requerir_proveedor_o_administrador)],
)


class CitaInput(BaseModel):
    clave_proveedor: str = Field(min_length=1, max_length=20)
    fecha: str = Field(min_length=10, max_length=10, description="YYYY-MM-DD")
    hora: str = Field(min_length=5, max_length=5, description="HH:MM")
    paciente: str | None = Field(default=None, max_length=150)


@router.get("")
def listar():
    """
    El padrón completo, con los dos orígenes en la misma lista y cada uno
    marcado para que la pantalla los distinga (ver mapearProveedor en
    frontend/js/directorio/datos.js):
      - origen='catalogo' -> llegó en la carga de Excel ("Dentro de la red").
      - origen='portal'   -> se dio de alta aquí ("Fuera de la red").
    Todos traen `clave` (PRV-000001), que es con lo que se agenda una cita:
    no cambia entre cargas, así que las citas nunca quedan huérfanas.
    El frontend busca/filtra sobre esta lista en el navegador.
    """
    return proveedores_repo.listar_padron()


@router.get("/citas")
def listar_citas(clave_proveedor: str | None = Query(default=None, max_length=20)):
    return citas_proveedor_repo.listar_citas(clave_proveedor)


@router.post("/citas")
def agendar_cita(data: CitaInput, usuario: dict = Depends(usuario_actual)):
    proveedor = proveedores_repo.obtener_por_clave(data.clave_proveedor)
    if proveedor is None:
        raise HTTPException(404, "No se encontró ese proveedor en el padrón.")
    if not agenda_proveedores_service.fecha_valida(data.fecha):
        raise HTTPException(
            400,
            "La fecha de la cita debe ser de hoy en adelante y dentro de los próximos "
            f"{agenda_proveedores_service.DIAS_AGENDA_MAXIMO} días.",
        )
    if not agenda_proveedores_service.horario_valido(data.hora):
        raise HTTPException(400, "Ese horario no está dentro de los que maneja la agenda.")

    rfc_usuario = usuario.get("rfc") or usuario.get("usuario") or "desconocido"
    try:
        cita = citas_proveedor_repo.agendar(
            data.clave_proveedor, data.fecha, data.hora, data.paciente, rfc_usuario
        )
    except citas_proveedor_repo.HorarioOcupado as e:
        raise HTTPException(409, str(e))
    return {
        **cita,
        "proveedor_nombre": proveedor["nombre"],
        "proveedor_especialidad": proveedor["especialidad"],
    }


@router.post("/citas/{folio}/cancelar")
def cancelar_cita(folio: str):
    if not citas_proveedor_repo.cancelar(folio):
        raise HTTPException(404, "No se encontró esa cita agendada.")
    return {"ok": True}


@router.get("/{clave}/agenda")
def agenda(
    clave: str,
    dias: int = Query(
        default=agenda_proveedores_service.DIAS_AGENDA_DEFAULT,
        ge=1,
        le=agenda_proveedores_service.DIAS_AGENDA_MAXIMO,
    ),
):
    """Horarios realmente libres de ese proveedor (los ya apartados no salen)."""
    if proveedores_repo.obtener_por_clave(clave) is None:
        raise HTTPException(404, "No se encontró ese proveedor en el padrón.")
    return agenda_proveedores_service.agenda_disponible(clave, dias)
