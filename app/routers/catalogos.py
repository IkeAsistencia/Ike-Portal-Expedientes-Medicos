from fastapi import APIRouter, Depends, Query

from app.core.security import usuario_actual
from app.repositories import catalogos_repo
from app.repositories.catalogos_repo import CL_SERVICIO_MAXIMO, CL_SERVICIO_MINIMO
from app.schemas.catalogo import (
    CatalogoItem,
    CatalogoItemTexto,
    CuentaBusqueda,
    EntidadFederativa,
)

router = APIRouter(
    prefix="/catalogos",
    tags=["Catálogos"],
    dependencies=[Depends(usuario_actual)],  # requiere login, ver /auth/login
)

# El typeahead de cuentas recorre el texto carácter por carácter para
# validarlo; sin tope, un texto de varios MB se vuelve ese mismo número de
# iteraciones.
LARGO_MAXIMO_BUSQUEDA_CUENTA = 60


@router.get("/servicios", response_model=list[CatalogoItem])
def servicios(cl_servicio: int = Query(4, ge=CL_SERVICIO_MINIMO, le=CL_SERVICIO_MAXIMO)):
    return catalogos_repo.listar_servicios(cl_servicio)


@router.get("/subservicios", response_model=list[CatalogoItem])
def subservicios(cl_servicio: int = Query(4, ge=CL_SERVICIO_MINIMO, le=CL_SERVICIO_MAXIMO)):
    return catalogos_repo.listar_subservicios(cl_servicio)


@router.get("/cuentas", response_model=list[CatalogoItem])
def cuentas():
    return catalogos_repo.listar_cuentas()


@router.get("/entidades", response_model=list[EntidadFederativa])
def entidades():
    """Combo Entidad del Alta de médico (Directorio de Proveedores) -- con
    CodEnt real, para después pedir municipios (ver /catalogos/municipios).
    Sin opción "Todas": a diferencia del filtro de Expedientes, aquí se
    está dando de alta a UN médico, siempre hace falta una entidad puntual.

    Trae además `clave_inegi` (la clave de entidad del INEGI, dos dígitos),
    que usa el frontend para encuadrar el mapa de "Buscar fuera de la red"."""
    return catalogos_repo.listar_entidades()


@router.get("/municipios", response_model=list[CatalogoItemTexto])
def municipios(cod_ent: str = Query(..., min_length=1, max_length=2)):
    return catalogos_repo.listar_municipios(cod_ent)


@router.get("/cuentas/buscar", response_model=list[CuentaBusqueda])
def buscar_cuentas(
    texto: str = Query(
        ...,
        min_length=3,
        max_length=LARGO_MAXIMO_BUSQUEDA_CUENTA,
        description="Se busca a partir del 3er carácter",
    ),
):
    # Revalidación explícita del tope ya exigido por Query(max_length=...)
    # arriba, para que quede visible justo antes del recorrido carácter por
    # carácter de abajo (CWE-606).
    if len(texto) > LARGO_MAXIMO_BUSQUEDA_CUENTA:
        return []
    # Validación: solo alfabético + espacios (igual que el prototipo)
    if not all(ch.isalpha() or ch.isspace() for ch in texto):
        return []
    return catalogos_repo.buscar_cuentas(texto)
