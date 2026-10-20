from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import usuario_actual
from app.repositories import accesos_repo, solicitudes_alta_medico_repo
from app.repositories.accesos_repo import PERFIL_CABINA


def _requerir_proveedor_o_administrador(usuario: dict = Depends(usuario_actual)) -> dict:
    """Mismo criterio que app/routers/directorio_proveedores.py: "Alta de
    médico" vive dentro de la pantalla "Proveedores" (Proveedor y
    Administrador) -- Cabina no la usa."""
    if usuario.get("perfil") == PERFIL_CABINA:
        raise HTTPException(403, "Esta función no aplica para el perfil Cabina.")
    return usuario


def _requerir_administrador(usuario: dict = Depends(usuario_actual)) -> dict:
    """
    Resolver una solicitud (aprobar/rechazar) y corregirla antes de
    resolverla son actos de REVISIÓN: solo Administrador (decisión del
    usuario, 2026-10-19). Cualquier perfil puede capturar su alta, pero
    nadie se aprueba a sí mismo -- aprobar inserta un proveedor real en el
    padrón, igual que la carga de Excel, que también es exclusiva de
    Administrador (ver app/routers/proveedores_catalogo.py).
    """
    try:
        accesos_repo.verificar_rol_administrador(usuario)
    except ValueError:
        raise HTTPException(
            403, "Revisar solicitudes de alta es exclusivo del perfil Administrador."
        )
    return usuario


router = APIRouter(
    prefix="/solicitudes-alta-medico",
    tags=["Directorio de Proveedores -- Alta de médico"],
    dependencies=[Depends(_requerir_proveedor_o_administrador)],
)


class SolicitudAltaInput(BaseModel):
    """
    Alta real de un médico en el portal. El domicilio va desglosado y es el
    del lugar DONDE DA LA CONSULTA (mismo criterio que la carga de Excel,
    ver app/services/proveedores_excel_service.py).
    """

    nombre: str = Field(min_length=1, max_length=150)
    especialidad: str = Field(min_length=1, max_length=100)
    cedula: str = Field(min_length=1, max_length=20)
    rfc: str | None = Field(default=None, max_length=20)
    estado: str | None = Field(default=None, max_length=60)
    municipio: str | None = Field(default=None, max_length=80)
    calle_num_ext_int: str | None = Field(default=None, max_length=180)
    colonia: str | None = Field(default=None, max_length=120)
    codigo_postal: str | None = Field(default=None, max_length=10)
    telefono: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=120)


class EstatusInput(BaseModel):
    estatus: str


@router.get("")
def listar():
    return solicitudes_alta_medico_repo.listar_solicitudes()


@router.post("")
def crear(data: SolicitudAltaInput, usuario: dict = Depends(usuario_actual)):
    rfc_usuario = usuario.get("rfc") or usuario.get("usuario") or "desconocido"
    return solicitudes_alta_medico_repo.crear_solicitud(data.model_dump(), rfc_usuario)


@router.put("/{folio}", dependencies=[Depends(_requerir_administrador)])
def editar(folio: str, data: SolicitudAltaInput):
    """
    Corrige los datos de una solicitud ANTES de resolverla (botón "Editar").
    Solo mientras siga "En revisión": una vez aprobada ya existe el
    proveedor en el padrón con su clave y sus citas, y una vez rechazada el
    expediente quedó cerrado -- en ninguno de los dos casos se edita desde
    aquí.
    """
    try:
        solicitud = solicitudes_alta_medico_repo.actualizar_solicitud(folio, data.model_dump())
    except solicitudes_alta_medico_repo.SolicitudYaResuelta as e:
        raise HTTPException(409, str(e))
    if solicitud is None:
        raise HTTPException(404, "No se encontró esa solicitud.")
    return {"ok": True, "folio": folio}


@router.post("/{folio}/estatus", dependencies=[Depends(_requerir_administrador)])
def actualizar_estatus(folio: str, data: EstatusInput):
    """
    Aprobar da de alta al médico en el padrón con origen='portal' ("Fuera de
    la red") y le asigna su clave -- por eso se regresa `clave_proveedor`:
    es con la que ya se le pueden agendar citas.
    """
    if data.estatus not in solicitudes_alta_medico_repo.ESTATUS_VALIDOS:
        raise HTTPException(400, "Estatus inválido.")
    solicitud = solicitudes_alta_medico_repo.cambiar_estatus(folio, data.estatus)
    if solicitud is None:
        raise HTTPException(404, "No se encontró esa solicitud.")
    return {"ok": True, "clave_proveedor": solicitud.get("clave_proveedor")}
