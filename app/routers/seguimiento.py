from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.core.security import usuario_actual
from app.repositories import (
    accesos_repo,
    comprobantes_repo,
    estatus_repo,
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
from app.services import email_service

# Cabina puede regresar el expediente a Proveedor en cualquiera de estos dos
# estatus -- ambos exigen comentario obligatorio, se escriben en Core y
# disparan una notificación por correo (ver /estatus más abajo).
ESTATUS_DE_REGRESO = (EstatusExpediente.EN_ESPERA_RESPUESTA, EstatusExpediente.SEGUIMIENTO_CITA)

router = APIRouter(prefix="/seguimiento", tags=["Seguimiento"])

LONGITUD_MINIMA_COMENTARIO_PROVEEDOR = 50

# Proveedor solo debe poder leer comprobante/comentarios/pago-anticipado de
# expedientes que le corresponde atender -- igual que ESTATUS_VISIBLES_PROVEEDOR
# en frontend/index.html. Sin esto, cualquier Proveedor autenticado podía leer
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
    """
    if usuario.get("perfil") == accesos_repo.PERFIL_CABINA:
        raise HTTPException(403, "El perfil Cabina no tiene acceso a Registrar seguimiento.")
    comentario_limpio = data.comentario.strip()
    if not comentario_limpio:
        raise HTTPException(400, "El comentario no puede estar vacío.")
    if len(comentario_limpio) < LONGITUD_MINIMA_COMENTARIO_PROVEEDOR:
        raise HTTPException(
            400,
            f"El comentario debe tener al menos {LONGITUD_MINIMA_COMENTARIO_PROVEEDOR} caracteres "
            "para poder actualizar.",
        )

    # Proveedor solo puede registrar seguimiento mientras el expediente está
    # "En Espera de Respuesta" (primer envío) o "Seguimiento de Cita" (ya con
    # la cita aceptada, segundo envío con el comprobante) -- en cualquier
    # otro estatus no le corresponde, aunque se llame al endpoint directo.
    es_proveedor = usuario.get("perfil") == accesos_repo.PERFIL_PROVEEDOR
    estatus_actual = None
    if es_proveedor:
        encontrados = expedientes_repo.listar_expedientes(ExpedienteFiltro(cl_expediente=data.cl_expediente))
        if not encontrados:
            raise HTTPException(404, "No se encontró el expediente.")
        estatus_actual = encontrados[0].estatus
        if estatus_actual not in (EstatusExpediente.EN_ESPERA_RESPUESTA, EstatusExpediente.SEGUIMIENTO_CITA):
            raise HTTPException(
                400, "Este expediente ya no está en espera de respuesta, no puedes actualizarlo."
            )

    # Pago Anticipado: el comprobante se vuelve obligatorio hasta la segunda
    # vuelta, cuando Cabina ya regresó el expediente como "Seguimiento de
    # Cita" (cita aceptada) -- no en el primer envío.
    if (
        es_proveedor
        and estatus_actual == EstatusExpediente.SEGUIMIENTO_CITA
        and pago_anticipado_repo.es_anticipado(data.cl_expediente)
        and not comprobantes_repo.existe_comprobante(data.cl_expediente)
    ):
        raise HTTPException(400, "Debes subir el comprobante de pago antes de continuar.")

    cl_usr_app = usuario.get("cl_usr_app")
    if cl_usr_app is None:
        # Ver nota en accesos_repo.CL_USR_APP_PLACEHOLDER_RFC.
        cl_usr_app = accesos_repo.CL_USR_APP_PLACEHOLDER_RFC

    resultado = seguimiento_repo.registrar_seguimiento(data, cl_usr_app=cl_usr_app)

    # Copia local: Cabina no puede escribir aquí, pero sí necesita poder leerlo.
    identificador = usuario.get("rfc") or usuario.get("usuario") or "desconocido"
    seguimiento_repo.guardar_comentario_local(data.cl_expediente, identificador, data.comentario, origen="proveedor")

    if es_proveedor:
        estatus_repo.actualizar_estatus(data.cl_expediente, EstatusExpediente.SEGUIMIENTO_PROVEEDOR, identificador)
        # A partir del primer envío, si marcó (o no) la casilla de pago
        # anticipado, ya no se puede volver a cambiar.
        pago_anticipado_repo.bloquear(data.cl_expediente)

    return resultado


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
    """Cambia el estatus del expediente a mano. Solo vive en la app (no en SQL Server)."""
    if usuario.get("perfil") == accesos_repo.PERFIL_PROVEEDOR:
        raise HTTPException(403, "El perfil Proveedor no puede cambiar el estado manualmente.")
    try:
        estatus = EstatusExpediente(data.estatus)
    except ValueError:
        opciones = ", ".join(e.value for e in EstatusExpediente)
        raise HTTPException(400, f"Estado inválido: '{data.estatus}'. Opciones: {opciones}")
    # Regla de negocio: "En Espera de Respuesta" y "Seguimiento de Cita" se
    # activan solo cuando Cabina regresa el expediente a mano (corrección, o
    # cita aceptada en pago anticipado). Nadie más los puede asignar.
    if estatus in ESTATUS_DE_REGRESO and usuario.get("perfil") != accesos_repo.PERFIL_CABINA:
        raise HTTPException(400, f"'{estatus.value}' no se puede asignar a mano desde este perfil.")
    # "Seguimiento Proveedor" solo se activa automático desde "Actualizar Core"
    # (ver arriba). Cabina no puede ponerlo a mano — no le corresponde esa etapa.
    if estatus == EstatusExpediente.SEGUIMIENTO_PROVEEDOR and usuario.get("perfil") == accesos_repo.PERFIL_CABINA:
        raise HTTPException(400, "'Seguimiento Proveedor' es automático, Cabina no puede asignarlo a mano.")
    # "Seguimiento de Cita" es exclusivo de expedientes que el Proveedor marcó
    # como pago anticipado -- no tiene sentido en cualquier otro caso.
    if estatus == EstatusExpediente.SEGUIMIENTO_CITA and not pago_anticipado_repo.es_anticipado(data.cl_expediente):
        raise HTTPException(400, "Este expediente no está marcado como pago anticipado.")

    identificador = usuario.get("rfc") or usuario.get("usuario") or "desconocido"

    if estatus in ESTATUS_DE_REGRESO:
        # Cabina está regresando el expediente a Proveedor: exige el motivo,
        # lo escribe en Core (igual que el comentario del Proveedor) y avisa
        # por correo. No es un simple cambio de estatus como los demás.
        comentario = (data.comentario or "").strip()
        if not comentario:
            raise HTTPException(400, "Debes indicar un comentario para regresar el expediente.")

        cl_usr_app = usuario.get("cl_usr_app")
        if cl_usr_app is None:
            cl_usr_app = accesos_repo.CL_USR_APP_PLACEHOLDER_RFC
        seguimiento_repo.registrar_seguimiento(
            SeguimientoInput(cl_expediente=data.cl_expediente, comentario=comentario),
            cl_usr_app=cl_usr_app,
        )
        seguimiento_repo.guardar_comentario_local(data.cl_expediente, identificador, comentario, origen="cabina")

        encontrados = expedientes_repo.listar_expedientes(ExpedienteFiltro(cl_expediente=data.cl_expediente))
        if encontrados:
            registro = encontrados[0]
            email_service.enviar_notificacion_regreso(
                data.cl_expediente, registro.cuenta, registro.nombre_paciente, comentario, identificador,
                nuevo_estatus=estatus.value,
            )

    estatus_repo.actualizar_estatus(data.cl_expediente, estatus, identificador)
    return {"cl_expediente": data.cl_expediente, "estatus": estatus.value}
