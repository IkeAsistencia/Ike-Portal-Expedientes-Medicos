"""
Pantalla "Administración de accesos": alta/baja de RFC, perfiles y
entidad de los Proveedores, y reseteo de contraseña. Exclusivo del
perfil Administrador (ver `requerir_administrador` más abajo, usado
también por otros routers como cuentas_etiquetas.py y seguimiento.py
para su propio control de acceso).
"""

import io
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.core.log_seguro import sanear_para_log
from app.core.rate_limit import verificar_limite
from app.core.security import usuario_actual
from app.repositories import accesos_repo
from app.schemas.acceso import (
    AccesoListado,
    ActualizarEntidadInput,
    AgregarPerfilInput,
    AltaAccesoInput,
    CargaUsuariosFila,
    CargaUsuariosResponse,
)
from app.services import carga_usuarios_service

logger = logging.getLogger("admin_accesos")

router = APIRouter(prefix="/admin/accesos", tags=["Administración de accesos"])

TAMANO_MAXIMO_CARGA_BYTES = 2 * 1024 * 1024  # 2 MB: un Excel de usuarios pesa unos KB
FIRMA_XLSX = b"PK\x03\x04"  # un .xlsx es un ZIP; el Content-Type lo manda el cliente y no es confiable
MAXIMO_CARGAS_POR_VENTANA = 30
VENTANA_CARGAS_SEGUNDOS = 600


@router.get("/entidades", response_model=list[str])
def listar_entidades(_: dict = Depends(usuario_actual)):
    """Catálogo fijo de las 32 entidades, para el combo de alta de Proveedor."""
    return accesos_repo.ENTIDADES_MEXICO


def requerir_administrador(usuario: dict = Depends(usuario_actual)) -> dict:
    """
    Solo el perfil Administrador puede dar de alta/baja RFC y perfiles.
    Una sesión SISE legada (sin 'perfil' en el token) NO cuenta como
    administrador aquí — a diferencia de otros endpoints, esta pantalla
    maneja accesos y debe quedar estrictamente limitada.
    """
    if usuario.get("perfil") != accesos_repo.PERFIL_ADMINISTRADOR:
        raise HTTPException(403, "Esta sección es exclusiva del perfil Administrador.")
    return usuario


@router.get("", response_model=list[AccesoListado])
def listar_accesos(_: dict = Depends(requerir_administrador)):
    return accesos_repo.listar_accesos()


@router.post("")
def dar_de_alta(data: AltaAccesoInput, _: dict = Depends(requerir_administrador)):
    if accesos_repo.buscar_acceso(data.rfc):
        raise HTTPException(
            409, "Ya existe un acceso registrado con ese RFC. Para darle otro perfil usa «Agregar perfil» en su renglón."
        )
    accesos_repo.alta_acceso(data.rfc, data.nombre, data.perfil, data.entidad, data.correo)
    return {"ok": True}


@router.post("/carga-excel", response_model=CargaUsuariosResponse)
def carga_masiva_desde_excel(
    archivo: UploadFile = File(...),
    tipo: str = Form(...),
    aplicar: bool = Form(False),
    usuario: dict = Depends(requerir_administrador),
):
    """
    Carga masiva de accesos desde un Excel. Con aplicar=false solo revisa el archivo y
    regresa la vista previa (no escribe nada); la pantalla manda el mismo archivo otra
    vez con aplicar=true cuando quien carga confirma. Cada acceso queda sin contraseña:
    la persona la crea al entrar. Ver app/services/carga_usuarios_service.py.
    """
    if tipo not in carga_usuarios_service.TIPOS_DE_CARGA:
        raise HTTPException(400, "Tipo de carga inválido.")
    rfc_quien_carga = usuario.get("rfc") or usuario.get("usuario") or "desconocido"
    verificar_limite(f"carga-usuarios:{rfc_quien_carga}", MAXIMO_CARGAS_POR_VENTANA, VENTANA_CARGAS_SEGUNDOS)

    if not (archivo.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(400, "El archivo debe ser un Excel (.xlsx).")
    contenido = archivo.file.read(TAMANO_MAXIMO_CARGA_BYTES + 1)
    if len(contenido) > TAMANO_MAXIMO_CARGA_BYTES:
        raise HTTPException(400, "El archivo supera el máximo permitido de 2 MB.")
    if not contenido.startswith(FIRMA_XLSX):
        raise HTTPException(400, "El archivo no es un Excel (.xlsx) válido.")

    rol, entidad = carga_usuarios_service.TIPOS_DE_CARGA[tipo]
    try:
        resultado = carga_usuarios_service.sembrar_desde_excel(
            io.BytesIO(contenido), aplicar=aplicar, rol_por_defecto=rol, entidad_por_defecto=entidad
        )
    except carga_usuarios_service.ErrorCargaUsuarios as err:
        raise HTTPException(400, str(err))

    def fila(datos: dict, resultado_fila: str, motivo: str | None = None) -> CargaUsuariosFila:
        return CargaUsuariosFila(
            hoja=datos["hoja"], renglon=datos["renglon"], rfc=datos["rfc"], nombre=datos["nombre"],
            rol=datos["rol"], entidad=datos["entidad"], correo=datos["correo"],
            resultado=resultado_fila, motivo=motivo,
        )

    filas = [fila(d, "rechazada", motivo) for d, motivo in resultado["rechazadas"]]
    filas += [fila(d, accion) for d, accion in resultado["plan"]]
    if aplicar:
        logger.warning(
            "Carga masiva de usuarios por %s (%s): %d nuevos, %d perfiles agregados, %d ya existían, %d rechazadas.",
            sanear_para_log(rfc_quien_carga), sanear_para_log(tipo), resultado["nuevos"],
            resultado["perfiles_agregados"], resultado["ya_existian"], len(resultado["rechazadas"]),
        )
    return CargaUsuariosResponse(
        aplicado=aplicar,
        total=resultado["total"],
        nuevos=resultado["nuevos"],
        perfiles_agregados=resultado["perfiles_agregados"],
        ya_existian=resultado["ya_existian"],
        rechazadas=len(resultado["rechazadas"]),
        filas=filas,
    )


@router.post("/{rfc}/entidad")
def cambiar_entidad(rfc: str, data: ActualizarEntidadInput, _: dict = Depends(requerir_administrador)):
    """
    Cambia la entidad de un Proveedor ya dado de alta (ej. si en el futuro
    se reasigna a otro estado) -- antes solo se podía fijar al crearlo.
    """
    acceso = accesos_repo.buscar_acceso(rfc)
    if not acceso:
        raise HTTPException(404, "No se encontró ese RFC.")
    if accesos_repo.PERFIL_PROVEEDOR not in acceso["perfiles"]:
        raise HTTPException(400, "Solo se puede cambiar la entidad a un usuario con perfil Proveedor.")
    accesos_repo.actualizar_entidad(rfc, data.entidad)
    return {"ok": True}


def _traducir_error_perfil(err: accesos_repo.ErrorPerfil) -> HTTPException:
    codigo = {accesos_repo.AccesoNoEncontrado: 404, accesos_repo.PerfilYaAsignado: 409}.get(type(err), 400)
    return HTTPException(codigo, str(err))


@router.post("/{rfc}/perfiles")
def agregar_perfil(rfc: str, data: AgregarPerfilInput, _: dict = Depends(requerir_administrador)):
    """
    Le suma un perfil a una persona que ya tiene acceso: misma contraseña y mismo
    RFC, y al entrar elige con cuál.
    """
    try:
        accesos_repo.agregar_perfil(rfc, data.perfil, data.entidad, data.correo)
    except accesos_repo.ErrorPerfil as err:
        raise _traducir_error_perfil(err)
    return {"ok": True}


@router.delete("/{rfc}/perfiles/{perfil}")
def quitar_perfil(rfc: str, perfil: int, _: dict = Depends(requerir_administrador)):
    try:
        accesos_repo.quitar_perfil(rfc, perfil)
    except accesos_repo.ErrorPerfil as err:
        raise _traducir_error_perfil(err)
    return {"ok": True}


@router.post("/{rfc}/inactivar")
def inactivar_acceso(rfc: str, _: dict = Depends(requerir_administrador)):
    """
    Baja lógica (no se borra el registro, para conservar el track de
    quién tuvo acceso). La persona ya no puede iniciar sesión.
    """
    if not accesos_repo.inactivar_acceso(rfc):
        raise HTTPException(404, "No se encontró ese RFC, o ya estaba inactivo.")
    return {"ok": True}


@router.post("/{rfc}/reactivar")
def reactivar_acceso(rfc: str, _: dict = Depends(requerir_administrador)):
    if not accesos_repo.reactivar_acceso(rfc):
        raise HTTPException(404, "No se encontró ese RFC, o ya estaba activo.")
    return {"ok": True}


@router.post("/{rfc}/resetear-password")
def resetear_password(rfc: str, _: dict = Depends(requerir_administrador)):
    if not accesos_repo.resetear_password(rfc):
        raise HTTPException(404, "No se encontró ese RFC.")
    return {"ok": True}
