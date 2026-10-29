from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.core.security import usuario_actual
from app.repositories import accesos_repo, correos_enviados_repo, cortes_repo, expedientes_repo
from app.schemas.correo import (
    MAXIMO_EXPEDIENTES_POR_OPERACION,
    EnviarCorreoProveedoresInput,
    EnviarCorreoProveedoresResponse,
    EnviarCorteInput,
    EnviarCorteResponse,
    GenerarCorteInput,
    GenerarCorteResponse,
)
from app.schemas.expediente import Expediente, ExpedienteFiltro
from app.services import cuota_correos_service, email_service, envio_correo_service, excel_service

router = APIRouter(
    prefix="/expedientes",
    tags=["Expedientes"],
    dependencies=[Depends(usuario_actual)],  # requiere login, ver /auth/login
)


@router.get("", response_model=list[Expediente])
def listar_expedientes(
    cl_expediente: Optional[int] = None,
    fecha_inicio: Optional[date] = None,
    fecha_fin: Optional[date] = None,
    cl_servicio: Optional[int] = None,
    cl_subservicio: Optional[int] = None,
    cuentas: Optional[list[int]] = Query(
        default=None, description="Una o varias claves de cuenta (?cuentas=1&cuentas=2)"
    ),
):
    filtro = ExpedienteFiltro(
        cl_expediente=cl_expediente,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        cl_servicio=cl_servicio,
        cl_subservicio=cl_subservicio,
        cuentas=cuentas,
    )
    try:
        return expedientes_repo.listar_expedientes(filtro)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/enviar-correo-proveedores", response_model=EnviarCorreoProveedoresResponse)
def enviar_correo_proveedores(data: EnviarCorreoProveedoresInput, usuario: dict = Depends(usuario_actual)):
    """
    Botón "Enviar correo a proveedores". Es una acción operativa de Cabina --
    Administrador ya no la usa (ahora solo genera el corte/evidencia) y
    Proveedor tampoco.

    La selección debe quedar "pareja": todos en "Abierto" (notificación
    nueva) o todos en "En Espera de Respuesta" (recordatorio) -- nunca
    mezclados, y ningún otro estado. Si no cumple, se cancela el envío
    completo (no se manda nada, ni a los que sí cumplían).

    A quién le llega, el freno de reenvío y el tope diario: ver
    app/services/envio_correo_service.py.
    """
    if len(data.expedientes) > MAXIMO_EXPEDIENTES_POR_OPERACION:
        raise HTTPException(400, f"No se pueden procesar más de {MAXIMO_EXPEDIENTES_POR_OPERACION} expedientes a la vez.")
    return envio_correo_service.enviar_a_proveedores(data.expedientes, usuario, data.confirmar_limite)


def _requerir_administrador(usuario: dict) -> None:
    """
    El corte quedó reservado al perfil Administrador (decisión del jefe):
    Cabina y Proveedor ya no lo generan/descargan/envían.
    """
    if usuario.get("perfil") != accesos_repo.PERFIL_ADMINISTRADOR:
        raise HTTPException(403, "El corte de expedientes es exclusivo del perfil Administrador.")


@router.post("/corte", response_model=GenerarCorteResponse)
def generar_corte(data: GenerarCorteInput, usuario: dict = Depends(usuario_actual)):
    """
    Botón "Generar corte" (independiente de "Enviar correo a proveedores"):
    arma el Excel de los expedientes seleccionados y lo deja listo -- desde
    el front, después de esto se puede descargar, previsualizar y por
    separado "Confirmar y enviar" (ver endpoints de abajo). No cambia el
    estatus de ningún expediente, es solo evidencia/corte.

    Todos los expedientes seleccionados deben compartir el MISMO estatus
    (mezclar estatus en un mismo corte no tendría sentido).

    Las columnas "Coordinador" y "Fecha Envío a Proveedor" muestran quién y
    cuándo se le mandó el expediente al proveedor la PRIMERA vez (ver
    correos_enviados_repo.obtener_envio_original) -- ese dato queda fijo
    desde el envío original y no cambia aunque el expediente siga avanzando
    después (a "Seguimiento Proveedor", "Finalizado", etc.). Un expediente
    "Abierto" que nunca se le ha mandado a nadie sale en "NA" porque de
    verdad no hay dato, no por una regla que lo fuerce.
    """
    _requerir_administrador(usuario)

    # GenerarCorteInput.expedientes ya trae Field(max_length=...); se
    # revalida aquí, en la misma función que arma el `for` de abajo, para
    # que el tope quede explícito en el código (CWE-606).
    if len(data.expedientes) > MAXIMO_EXPEDIENTES_POR_OPERACION:
        raise HTTPException(400, f"No se pueden procesar más de {MAXIMO_EXPEDIENTES_POR_OPERACION} expedientes a la vez.")

    registros = []
    for cl_expediente in data.expedientes:
        encontrados = expedientes_repo.listar_expedientes(ExpedienteFiltro(cl_expediente=cl_expediente))
        if encontrados:
            registros.append(encontrados[0])

    if not registros:
        raise HTTPException(404, "No se encontró información de los expedientes seleccionados.")

    estatuses = {r.estatus for r in registros}
    if len(estatuses) > 1:
        raise HTTPException(
            400,
            "Todos los expedientes seleccionados deben tener el mismo estatus para generar el corte "
            f"(seleccionaste: {', '.join(sorted(e.value for e in estatuses))}).",
        )

    filas_excel = []
    for r in registros:
        fila = r.model_dump()
        envio = correos_enviados_repo.obtener_envio_original(r.expediente)
        fila["rfc_envio"] = envio["nombre_envio"] if envio else "NA"
        fila["fecha_envio"] = envio["fecha"] if envio else "NA"
        filas_excel.append(fila)

    usuario_nombre = usuario.get("nombre") or usuario.get("usuario") or "desconocido"
    archivo_bytes = excel_service.generar_corte_excel(filas_excel, data.tipo_expediente, usuario_nombre)
    fecha_archivo = date.today().isoformat()
    etiqueta = "pago_anticipado" if data.tipo_expediente == "anticipado" else "expedientes"
    archivo_nombre = f"corte_{etiqueta}_{fecha_archivo}.xlsx"

    identificador = usuario.get("rfc") or usuario.get("usuario") or "desconocido"
    corte_id = cortes_repo.crear_corte(
        identificador, data.tipo_expediente, [r.expediente for r in registros], archivo_nombre, archivo_bytes
    )

    return GenerarCorteResponse(
        corte_id=corte_id,
        archivo_nombre=archivo_nombre,
        total=len(registros),
        expedientes=[r.expediente for r in registros],
    )


@router.get("/corte/{corte_id}/descargar")
def descargar_corte(corte_id: int, usuario: dict = Depends(usuario_actual)):
    _requerir_administrador(usuario)
    corte = cortes_repo.obtener_corte(corte_id)
    if not corte:
        raise HTTPException(404, "No se encontró ese corte.")
    return Response(
        content=corte["contenido"],
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{corte["nombre_archivo"]}"'},
    )


@router.post("/corte/{corte_id}/enviar", response_model=EnviarCorteResponse)
def enviar_corte(corte_id: int, data: EnviarCorteInput, usuario: dict = Depends(usuario_actual)):
    """
    "Enviar": manda por correo (modo simulado mientras no haya SMTP real, ver
    email_service.py) el MISMO archivo que ya se generó/pudo descargarse en
    /corte -- así lo que se ve/descarga es exactamente lo que se envía.

    El corte es para Cabina, no para proveedores: va a UNA sola dirección,
    la que escribe el Administrador. Cuenta contra el tope diario de correos;
    si ya no hay lugar, no se envía (el Excel se puede seguir descargando).
    """
    _requerir_administrador(usuario)
    corte = cortes_repo.obtener_corte(corte_id)
    if not corte:
        raise HTTPException(404, "No se encontró ese corte.")

    reserva = cuota_correos_service.reservar("corte", cuota_correos_service.unidades_para(1))
    if reserva is None:
        limite = cuota_correos_service.estado().limite
        raise HTTPException(
            409,
            f"Se alcanzó el límite de {limite} correos por día: el corte no se envió. "
            "Puedes descargar el Excel y compartirlo por otro medio.",
        )

    usuario_nombre = usuario.get("nombre") or usuario.get("usuario") or "desconocido"
    try:
        resultado = email_service.enviar_corte_proveedores(
            cantidad=len(corte["expedientes"]),
            tipo_expediente=corte["tipo_expediente"],
            archivo_nombre=corte["nombre_archivo"],
            archivo_bytes=corte["contenido"],
            usuario_nombre=usuario_nombre,
            destinatario=data.destinatario,
            fecha_generado=corte["fecha_generado"],
        )
    except email_service.ErrorEnvioCorreo:
        cuota_correos_service.liberar(reserva)
        raise HTTPException(503, "No se pudo enviar el corte: el servidor de correo no respondió. Intenta de nuevo en unos minutos.")
    cortes_repo.marcar_enviado(corte_id, resultado.destinatarios[0])

    return EnviarCorteResponse(
        enviados=resultado.enviados,
        simulado=resultado.simulado,
        destinatario=resultado.destinatarios[0],
    )
