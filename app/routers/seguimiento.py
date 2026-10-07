from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.core.security import usuario_actual
from app.repositories import (
    accesos_repo,
    comprobantes_repo,
    expedientes_repo,
    pago_anticipado_repo,
    seguimiento_repo,
)
from app.schemas.expediente import EstatusExpediente, ExpedienteFiltro
from app.schemas.seguimiento import (
    ComentarioSeguimiento,
    ComprobanteMeta,
    EstatusInput,
    PagoAnticipadoInput,
    PagoAnticipadoResponse,
    SeguimientoInput,
)
from app.services import estatus_service, seguimiento_service

router = APIRouter(prefix="/seguimiento", tags=["Seguimiento"])

# Proveedor solo debe poder leer comprobante/comentarios/pago-anticipado de
# expedientes que le corresponde atender -- igual que ESTATUS_VISIBLES_PROVEEDOR
# en frontend/js/core/reglas-expedientes.js. Sin esto, cualquier Proveedor autenticado podía leer
# estos datos de CUALQUIER expediente adivinando el número (IDOR).
ESTATUS_VISIBLES_PROVEEDOR = (
    EstatusExpediente.EN_ESPERA_RESPUESTA,
    EstatusExpediente.SEGUIMIENTO_CITA,
    EstatusExpediente.SEGUIMIENTO_PROVEEDOR,
)


def _verificar_proveedor_puede_ver(cl_expediente: int, usuario: dict) -> None:
    """
    No valida "dueño" del expediente -- SQL Server no guarda todavía qué
    Proveedor específico tiene asignado cada expediente (ver sql/README.md).
    Mientras tanto, esto al menos limita a Proveedor a expedientes dentro
    del flujo que le corresponde, en vez de cualquier número adivinado.
    """
    if usuario.get("perfil") != accesos_repo.PERFIL_PROVEEDOR:
        return
    encontrados = expedientes_repo.listar_expedientes(ExpedienteFiltro(cl_expediente=cl_expediente))
    if not encontrados or encontrados[0].estatus not in ESTATUS_VISIBLES_PROVEEDOR:
        raise HTTPException(403, "Este expediente no te corresponde.")


@router.post("/actualizar")
def actualizar_seguimiento(data: SeguimientoInput, usuario: dict = Depends(usuario_actual)):
    """
    Botón 'Actualizar Core': inserta el registro en dbo.Seguimiento.
    Solo el perfil Proveedor (o una sesión SISE sin perfil, para no romper
    lo ya existente) puede usar esto — Cabina lo tiene bloqueado.
    Al completarse, si quien lo hizo es Proveedor, el estatus del
    expediente pasa automáticamente a "Seguimiento Proveedor" — nunca antes.

    Reglas en app/services/seguimiento_service.py (compartidas con la
    mutation equivalente de GraphQL).
    """
    return seguimiento_service.actualizar_seguimiento(data.cl_expediente, data.comentario, usuario)


@router.get("/comentarios/{cl_expediente}", response_model=list[ComentarioSeguimiento])
def obtener_comentarios(cl_expediente: int, usuario: dict = Depends(usuario_actual)):
    """
    Copia local (de solo lectura) de los comentarios que Proveedor ha ido
    dejando para este expediente. Cabina la usa para revisar sin poder
    modificar nada — el modificar solo pasa por 'Actualizar Core'.
    """
    _verificar_proveedor_puede_ver(cl_expediente, usuario)
    return seguimiento_repo.listar_comentarios_local(cl_expediente)


@router.post("/comprobante")
async def subir_comprobante(
    cl_expediente: int = Form(...),
    archivo: UploadFile = File(...),
    usuario: dict = Depends(usuario_actual),
):
    """
    Comprobante de pago (solo expedientes Pago Anticipado). Solo Proveedor
    lo puede subir; Cabina lo consulta en modo lectura (ver GET de abajo).
    """
    if usuario.get("perfil") != accesos_repo.PERFIL_PROVEEDOR:
        raise HTTPException(403, "Solo el perfil Proveedor puede subir el comprobante de pago.")
    _verificar_proveedor_puede_ver(cl_expediente, usuario)
    if archivo.content_type not in comprobantes_repo.TIPOS_MIME_PERMITIDOS:
        raise HTTPException(400, "Formato no permitido. Solo se aceptan PDF, JPG o PNG.")

    contenido = await archivo.read()
    if len(contenido) > comprobantes_repo.TAMANO_MAXIMO_BYTES:
        raise HTTPException(400, "El archivo supera el máximo permitido de 5 MB.")
    if not comprobantes_repo.contenido_coincide_con_tipo(contenido, archivo.content_type):
        raise HTTPException(
            400, "El contenido del archivo no corresponde al formato declarado (PDF, JPG o PNG)."
        )

    identificador = usuario.get("rfc") or usuario.get("usuario") or "desconocido"
    comprobantes_repo.guardar_comprobante(
        cl_expediente, identificador, archivo.filename or "comprobante", archivo.content_type, contenido
    )
    return {"ok": True}


@router.get("/pago-anticipado/{cl_expediente}", response_model=PagoAnticipadoResponse)
def obtener_pago_anticipado(cl_expediente: int, usuario: dict = Depends(usuario_actual)):
    """
    Solo el Proveedor sabe si un expediente es de pago anticipado -- Cabina
    también puede consultarlo (de solo lectura) para decidir si le
    corresponde regresarlo como "Seguimiento de Cita".
    """
    _verificar_proveedor_puede_ver(cl_expediente, usuario)
    row = pago_anticipado_repo.obtener(cl_expediente)
    if not row:
        return PagoAnticipadoResponse(es_anticipado=False, bloqueado=False)
    return PagoAnticipadoResponse(es_anticipado=bool(row["es_anticipado"]), bloqueado=bool(row["bloqueado"]))


@router.post("/pago-anticipado/{cl_expediente}")
def marcar_pago_anticipado(
    cl_expediente: int, data: PagoAnticipadoInput, usuario: dict = Depends(usuario_actual)
):
    """Casilla '¿Es un expediente de pago anticipado?' -- exclusiva de Proveedor, y solo antes de su primer envío."""
    if usuario.get("perfil") != accesos_repo.PERFIL_PROVEEDOR:
        raise HTTPException(403, "Solo el perfil Proveedor puede marcar si un expediente es de pago anticipado.")
    _verificar_proveedor_puede_ver(cl_expediente, usuario)
    actual = pago_anticipado_repo.obtener(cl_expediente)
    if actual and actual["bloqueado"]:
        raise HTTPException(400, "Ya no se puede cambiar: el expediente ya fue enviado.")
    identificador = usuario.get("rfc") or usuario.get("usuario") or "desconocido"
    pago_anticipado_repo.marcar(cl_expediente, data.es_anticipado, identificador)
    return {"ok": True}


@router.get("/comprobante/{cl_expediente}", response_model=ComprobanteMeta)
def obtener_comprobante_meta(cl_expediente: int, usuario: dict = Depends(usuario_actual)):
    _verificar_proveedor_puede_ver(cl_expediente, usuario)
    comprobante = comprobantes_repo.obtener_comprobante(cl_expediente)
    if not comprobante:
        raise HTTPException(404, "Este expediente todavía no tiene comprobante de pago.")
    return ComprobanteMeta(
        rfc=comprobante["rfc"], nombre_archivo=comprobante["nombre_archivo"],
        tipo_mime=comprobante["tipo_mime"], fecha=comprobante["fecha"],
    )


@router.get("/comprobante/{cl_expediente}/archivo")
def descargar_comprobante(cl_expediente: int, usuario: dict = Depends(usuario_actual)):
    _verificar_proveedor_puede_ver(cl_expediente, usuario)
    comprobante = comprobantes_repo.obtener_comprobante(cl_expediente)
    if not comprobante:
        raise HTTPException(404, "Este expediente todavía no tiene comprobante de pago.")
    return Response(
        content=comprobante["contenido"],
        media_type=comprobante["tipo_mime"],
        headers={"Content-Disposition": f'inline; filename="{comprobante["nombre_archivo"]}"'},
    )


@router.post("/estatus")
def actualizar_estatus(data: EstatusInput, usuario: dict = Depends(usuario_actual)):
    """
    Cambia el estatus del expediente a mano. Solo vive en la app (no en SQL Server).

    Reglas en app/services/estatus_service.py (compartidas con la mutation
    equivalente de GraphQL).
    """
    return estatus_service.actualizar_estatus(data.cl_expediente, data.estatus, usuario, data.comentario)
