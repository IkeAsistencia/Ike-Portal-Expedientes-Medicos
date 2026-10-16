from fastapi import APIRouter, Depends, HTTPException

from app.repositories import cuentas_etiqueta_repo
from app.routers.admin_accesos import requerir_administrador
from app.schemas.cuenta_etiqueta import PALETA, ColorPaleta, CuentaEtiquetaInput, CuentaEtiquetaRegistro

router = APIRouter(prefix="/admin/cuentas-etiquetas", tags=["Colores de cuentas"])


@router.get("/paleta", response_model=list[ColorPaleta])
def paleta(_: dict = Depends(requerir_administrador)):
    return PALETA


@router.get("", response_model=list[CuentaEtiquetaRegistro])
def listar(_: dict = Depends(requerir_administrador)):
    return cuentas_etiqueta_repo.listar()


@router.put("")
def guardar(data: CuentaEtiquetaInput, usuario: dict = Depends(requerir_administrador)):
    """Pone o cambia el color y el prefijo de una cuenta."""
    rfc = usuario.get("rfc") or usuario.get("usuario") or "desconocido"
    existia = cuentas_etiqueta_repo.guardar(data.cl_cuenta, data.nombre.strip(), data.prefijo, data.color, rfc)
    return {"ok": True, "actualizada": existia}


@router.delete("/{cl_cuenta}")
def quitar(cl_cuenta: int, _: dict = Depends(requerir_administrador)):
    if not cuentas_etiqueta_repo.eliminar(cl_cuenta):
        raise HTTPException(404, "Esa cuenta no tiene color asignado.")
    return {"ok": True}
