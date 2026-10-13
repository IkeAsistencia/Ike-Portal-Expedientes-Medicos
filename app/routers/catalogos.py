from fastapi import APIRouter, Depends, Query

from app.core.security import usuario_actual
from app.repositories import catalogos_repo
from app.schemas.catalogo import CatalogoItem, CuentaBusqueda

router = APIRouter(
    prefix="/catalogos",
    tags=["Catálogos"],
    dependencies=[Depends(usuario_actual)],  # requiere login, ver /auth/login
)

# clServicio es una clave del catálogo de Core (el portal trabaja con la 4,
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
