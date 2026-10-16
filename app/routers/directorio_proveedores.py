from fastapi import APIRouter, Depends, HTTPException

from app.core.security import usuario_actual
from app.repositories import proveedores_catalogo_repo
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
    Catálogo completo cargado por Administrador (ver
    app/routers/proveedores_catalogo.py) -- el frontend busca/filtra sobre
    esta lista en el navegador, igual que ya hacía antes con los datos
    simulados (ver frontend/js/directorio/datos.js).
    """
    return proveedores_catalogo_repo.listar_catalogo()
