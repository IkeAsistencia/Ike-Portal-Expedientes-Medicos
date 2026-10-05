from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.security import usuario_actual
from app.repositories import accesos_repo, cuentas_config_repo


def _requerir_no_cabina_ni_proveedor(usuario: dict = Depends(usuario_actual)) -> dict:
    """
    Configuración Cuentas es exclusiva de Administrador (Cabina y Proveedor
    ya no la ven). Una sesión SISE legada (sin 'perfil' en el token) se
    deja pasar para no romper lo ya existente (pruebas/GraphQL).
    """
    if usuario.get("perfil") in (accesos_repo.PERFIL_CABINA, accesos_repo.PERFIL_PROVEEDOR):
        raise HTTPException(403, "Configuración Cuentas es exclusiva del perfil Administrador.")
    return usuario


router = APIRouter(
    prefix="/configuracion/cuentas",
    tags=["Configuración Cuentas"],
    dependencies=[Depends(_requerir_no_cabina_ni_proveedor)],
)


class CuentaConfigInput(BaseModel):
    cl_cuenta: int
    nombre: str


@router.get("")
def listar():
    return cuentas_config_repo.listar_cuentas_configuradas()


@router.post("")
def agregar(data: CuentaConfigInput):
    try:
        cuentas_config_repo.agregar_cuenta_configurada(data.cl_cuenta, data.nombre)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@router.delete("/{cl_cuenta}")
def eliminar(cl_cuenta: int):
    eliminado = cuentas_config_repo.eliminar_cuenta_configurada(cl_cuenta)
    if not eliminado:
        raise HTTPException(404, "Cuenta no encontrada en la configuración.")
    return {"ok": True}


@router.post("/limpiar")
def limpiar():
    """Botón 'Cancelar': vacía completamente el grid."""
    cuentas_config_repo.limpiar_cuentas_configuradas()
    return {"ok": True}
