from fastapi import APIRouter, Depends, Query

from app.core.security import usuario_actual
from app.repositories import catalogos_repo
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

# clServicio es una clave del catálogo del sistema central (el portal trabaja con la 4,
# "Servicios Médicos"). Se acota el rango para que no llegue cualquier
# número: sin tope, el valor pasa directo al SP y lo que regrese se recorre
# completo del lado de la API (CWE-606, iteraciones sin límite).
CL_SERVICIO_MINIMO = 1
CL_SERVICIO_MAXIMO = 9999

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
    que es la que pide el DENUE en la búsqueda fuera de la red."""
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
    # Validación: solo alfabético + espacios (igual que el prototipo)
    if not all(ch.isalpha() or ch.isspace() for ch in texto):
        return []
    return catalogos_repo.buscar_cuentas(texto)
