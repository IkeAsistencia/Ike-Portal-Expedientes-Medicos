from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.core.security import usuario_actual
from app.repositories import accesos_repo, comprobantes_repo, estatus_repo, expedientes_repo, seguimiento_repo
from app.schemas.expediente import EstatusExpediente, ExpedienteFiltro
from app.schemas.seguimiento import ComentarioSeguimiento, ComprobanteMeta, EstatusInput, SeguimientoInput
from app.services import email_service

router = APIRouter(prefix="/seguimiento", tags=["Seguimiento"])

LONGITUD_MINIMA_COMENTARIO_PROVEEDOR = 50


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
    # "En Espera de Respuesta" -- si ya lo mandó antes (quedó "Seguimiento
    # Proveedor") o está en cualquier otro estatus, no le corresponde y no
    # se puede volver a mandar aunque se llame al endpoint directo.
    if usuario.get("perfil") == accesos_repo.PERFIL_PROVEEDOR:
        encontrados = expedientes_repo.listar_expedientes(ExpedienteFiltro(cl_expediente=data.cl_expediente))
        if not encontrados or encontrados[0].estatus != EstatusExpediente.EN_ESPERA_RESPUESTA:
            raise HTTPException(
                400, "Este expediente ya no está en espera de respuesta, no puedes actualizarlo."
            )

    # Pago Anticipado: obligatorio subir el comprobante antes de poder continuar.
    if (
        data.tipo_expediente == "anticipado"
        and usuario.get("perfil") == accesos_repo.PERFIL_PROVEEDOR
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

    if usuario.get("perfil") == accesos_repo.PERFIL_PROVEEDOR:
        estatus_repo.actualizar_estatus(data.cl_expediente, EstatusExpediente.SEGUIMIENTO_PROVEEDOR, identificador)

    return resultado


@router.get("/comentarios/{cl_expediente}", response_model=list[ComentarioSeguimiento])
def obtener_comentarios(cl_expediente: int, usuario: dict = Depends(usuario_actual)):
    """
    Copia local (de solo lectura) de los comentarios que Proveedor ha ido
    dejando para este expediente. Cabina la usa para revisar sin poder
    modificar nada — el modificar solo pasa por 'Actualizar Core'.
    """
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
    if archivo.content_type not in comprobantes_repo.TIPOS_MIME_PERMITIDOS:
        raise HTTPException(400, "Formato no permitido. Solo se aceptan PDF, JPG o PNG.")

    contenido = await archivo.read()
    if len(contenido) > comprobantes_repo.TAMANO_MAXIMO_BYTES:
        raise HTTPException(400, "El archivo supera el máximo permitido de 5 MB.")

    identificador = usuario.get("rfc") or usuario.get("usuario") or "desconocido"
    comprobantes_repo.guardar_comprobante(
        cl_expediente, identificador, archivo.filename or "comprobante", archivo.content_type, contenido
    )
    return {"ok": True}


@router.get("/comprobante/{cl_expediente}", response_model=ComprobanteMeta)
def obtener_comprobante_meta(cl_expediente: int, usuario: dict = Depends(usuario_actual)):
    comprobante = comprobantes_repo.obtener_comprobante(cl_expediente)
    if not comprobante:
        raise HTTPException(404, "Este expediente todavía no tiene comprobante de pago.")
    return ComprobanteMeta(
        rfc=comprobante["rfc"], nombre_archivo=comprobante["nombre_archivo"],
        tipo_mime=comprobante["tipo_mime"], fecha=comprobante["fecha"],
    )


@router.get("/comprobante/{cl_expediente}/archivo")
def descargar_comprobante(cl_expediente: int, usuario: dict = Depends(usuario_actual)):
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
    # Regla de negocio: "En Espera de Respuesta" se activa solo o cuando Cabina
    # regresa el expediente a mano (si detectó un error en lo que mandó
    # Proveedor, para que lo vuelva a llenar). Nadie más lo puede asignar.
    if estatus == EstatusExpediente.EN_ESPERA_RESPUESTA and usuario.get("perfil") != accesos_repo.PERFIL_CABINA:
        raise HTTPException(400, "'En Espera de Respuesta' no se puede asignar a mano desde este perfil.")
    # "Seguimiento Proveedor" solo se activa automático desde "Actualizar Core"
    # (ver arriba). Cabina no puede ponerlo a mano — no le corresponde esa etapa.
    if estatus == EstatusExpediente.SEGUIMIENTO_PROVEEDOR and usuario.get("perfil") == accesos_repo.PERFIL_CABINA:
        raise HTTPException(400, "'Seguimiento Proveedor' es automático, Cabina no puede asignarlo a mano.")

    identificador = usuario.get("rfc") or usuario.get("usuario") or "desconocido"

    if estatus == EstatusExpediente.EN_ESPERA_RESPUESTA:
        # Cabina está regresando el expediente a Proveedor: exige el motivo,
        # lo escribe en SISE (igual que el comentario del Proveedor) y avisa
        # por correo. No es un simple cambio de estatus como los demás.
        comentario = (data.comentario or "").strip()
        if not comentario:
            raise HTTPException(400, "Debes indicar el motivo por el que regresas el expediente.")

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
                data.cl_expediente, registro.cuenta, registro.nombre_paciente, comentario, identificador
            )

    estatus_repo.actualizar_estatus(data.cl_expediente, estatus, identificador)
    return {"cl_expediente": data.cl_expediente, "estatus": estatus.value}
