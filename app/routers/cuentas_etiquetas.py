from fastapi import APIRouter, Depends, HTTPException

from app.repositories import catalogos_repo, cuentas_etiqueta_repo
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
    # Solo se etiquetan cuentas del catálogo del portal (las de Expedientes: las
    # actuales y las que se agregaron en "Agregar cuenta"). Una que ya tenía
    # color se puede seguir editando aunque después salga del catálogo.
    en_catalogo = any(c.clave == data.cl_cuenta for c in catalogos_repo.listar_cuentas())
    ya_etiquetada = any(e["cl_cuenta"] == data.cl_cuenta for e in cuentas_etiqueta_repo.listar())
    if not en_catalogo and not ya_etiquetada:
        raise HTTPException(400, "Esa cuenta no está en el catálogo del portal. Agrégala primero en Agregar cuenta.")
    rfc = usuario.get("rfc") or usuario.get("usuario") or "desconocido"
    existia = cuentas_etiqueta_repo.guardar(data.cl_cuenta, data.nombre.strip(), data.prefijo, data.color, rfc)
    return {"ok": True, "actualizada": existia}


@router.delete("/{cl_cuenta}")
def quitar(cl_cuenta: int, _: dict = Depends(requerir_administrador)):
    if not cuentas_etiqueta_repo.eliminar(cl_cuenta):
        raise HTTPException(404, "Esa cuenta no tiene color asignado.")
    return {"ok": True}
