from fastapi import APIRouter, Depends, HTTPException

from app.core.security import usuario_actual
from app.repositories import accesos_repo
from app.schemas.acceso import AccesoListado, ActualizarEntidadInput, AltaAccesoInput

router = APIRouter(prefix="/admin/accesos", tags=["Administración de accesos"])


@router.get("/entidades", response_model=list[str])
def listar_entidades(_: dict = Depends(usuario_actual)):
    """Catálogo fijo de las 32 entidades, para el combo de alta de Proveedor."""
    return accesos_repo.ENTIDADES_MEXICO


def requerir_administrador(usuario: dict = Depends(usuario_actual)) -> dict:
    """
    Solo el perfil Administrador puede dar de alta/baja RFC y perfiles.
    Una sesión SISE legada (sin 'perfil' en el token) NO cuenta como
    administrador aquí — a diferencia de otros endpoints, esta pantalla
    maneja accesos y debe quedar estrictamente limitada.
    """
    if usuario.get("perfil") != accesos_repo.PERFIL_ADMINISTRADOR:
        raise HTTPException(403, "Esta sección es exclusiva del perfil Administrador.")
    return usuario


@router.get("", response_model=list[AccesoListado])
def listar_accesos(_: dict = Depends(requerir_administrador)):
    return accesos_repo.listar_accesos()


@router.post("")
def dar_de_alta(data: AltaAccesoInput, _: dict = Depends(requerir_administrador)):
    if accesos_repo.buscar_acceso(data.rfc):
        raise HTTPException(409, "Ya existe un acceso registrado con ese RFC.")
    accesos_repo.alta_acceso(data.rfc, data.nombre, data.perfil, data.entidad, data.correo)
    return {"ok": True}


@router.post("/{rfc}/entidad")
def cambiar_entidad(rfc: str, data: ActualizarEntidadInput, _: dict = Depends(requerir_administrador)):
    """
    Cambia la entidad de un Proveedor ya dado de alta (ej. si en el futuro
    se reasigna a otro estado) -- antes solo se podía fijar al crearlo.
    """
    acceso = accesos_repo.buscar_acceso(rfc)
    if not acceso:
        raise HTTPException(404, "No se encontró ese RFC.")
    if acceso["perfil"] != accesos_repo.PERFIL_PROVEEDOR:
        raise HTTPException(400, "Solo se puede cambiar la entidad a un usuario con perfil Proveedor.")
    accesos_repo.actualizar_entidad(rfc, data.entidad)
    return {"ok": True}


@router.post("/{rfc}/inactivar")
def inactivar_acceso(rfc: str, _: dict = Depends(requerir_administrador)):
    """
    Baja lógica (no se borra el registro, para conservar el track de
    quién tuvo acceso). La persona ya no puede iniciar sesión.
    """
    if not accesos_repo.inactivar_acceso(rfc):
        raise HTTPException(404, "No se encontró ese RFC, o ya estaba inactivo.")
    return {"ok": True}


@router.post("/{rfc}/reactivar")
def reactivar_acceso(rfc: str, _: dict = Depends(requerir_administrador)):
    if not accesos_repo.reactivar_acceso(rfc):
        raise HTTPException(404, "No se encontró ese RFC, o ya estaba activo.")
    return {"ok": True}


@router.post("/{rfc}/resetear-password")
def resetear_password(rfc: str, _: dict = Depends(requerir_administrador)):
    if not accesos_repo.resetear_password(rfc):
        raise HTTPException(404, "No se encontró ese RFC.")
    return {"ok": True}
