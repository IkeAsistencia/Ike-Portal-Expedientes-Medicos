from fastapi import APIRouter, Depends, HTTPException

from app.core.security import usuario_actual
from app.repositories import proveedores_catalogo_repo, solicitudes_alta_medico_repo
from app.repositories.accesos_repo import PERFIL_CABINA


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


@router.get("")
def listar():
    """
    Une dos fuentes, cada una marcada con su "origen" para distinguirlas en
    el frontend (ver mapearProveedor en frontend/js/directorio/datos.js):
      - "core": el catálogo que carga Administrador desde Excel (ver
        app/routers/proveedores_catalogo.py) -- tiene cl_proveedor real.
      - "portal": médicos dados de alta desde esta misma pantalla y ya
        aprobados (ver app/routers/solicitudes_alta_medico.py) -- no vienen
        de Core, por eso no tienen cl_proveedor y se identifican por folio.
    El frontend busca/filtra sobre esta lista unida en el navegador, igual
    que ya hacía antes con los datos simulados.
    """
    core = proveedores_catalogo_repo.listar_catalogo()
    for fila in core:
        fila["origen"] = "core"
    return core + solicitudes_alta_medico_repo.listar_aprobados_como_directorio()
