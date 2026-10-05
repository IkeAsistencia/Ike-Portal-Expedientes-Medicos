from fastapi import APIRouter, Depends, Query

from app.core.security import usuario_actual
from app.repositories import catalogos_repo
from app.schemas.catalogo import CatalogoItem, CuentaBusqueda

router = APIRouter(
    prefix="/catalogos",
    tags=["Catálogos"],
    dependencies=[Depends(usuario_actual)],  # requiere login, ver /auth/login
)


@router.get("/servicios", response_model=list[CatalogoItem])
def servicios(cl_servicio: int = 4):
    return catalogos_repo.listar_servicios(cl_servicio)


@router.get("/subservicios", response_model=list[CatalogoItem])
def subservicios(cl_servicio: int = 4):
    return catalogos_repo.listar_subservicios(cl_servicio)


@router.get("/cuentas", response_model=list[CatalogoItem])
def cuentas():
    return catalogos_repo.listar_cuentas()


@router.get("/cuentas/buscar", response_model=list[CuentaBusqueda])
def buscar_cuentas(
    texto: str = Query(..., min_length=3, description="Se busca a partir del 3er carácter"),
):
    # Validación: solo alfabético + espacios (igual que el prototipo)
    if not all(ch.isalpha() or ch.isspace() for ch in texto):
        return []
    return catalogos_repo.buscar_cuentas(texto)
