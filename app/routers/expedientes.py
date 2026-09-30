from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.core.security import usuario_actual
from app.repositories import accesos_repo, cortes_repo, estatus_repo, expedientes_repo
from app.schemas.correo import (
    EnviarCorreoProveedoresInput,
    EnviarCorreoProveedoresResponse,
    EnviarCorteResponse,
    GenerarCorteInput,
    GenerarCorteResponse,
)
from app.schemas.expediente import Expediente, EstatusExpediente, ExpedienteFiltro
from app.services import email_service, excel_service

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
    Administrador ya no la usa (ver _requerir_administrador de /corte: ahora
    Administrador solo genera el corte/evidencia, no avisa a proveedores).
    Valida que venga al menos un expediente seleccionado (ya lo exige el
    esquema con min_length=1, esto es una segunda validación explícita por
    claridad) y arma el correo con los datos de cada expediente seleccionado.
    """
    if usuario.get("perfil") == accesos_repo.PERFIL_ADMINISTRADOR:
        raise HTTPException(403, "El perfil Administrador no tiene acceso a esta acción.")
    if not data.expedientes:
        raise HTTPException(400, "Selecciona al menos un expediente antes de enviar el correo.")

    registros = []
    for cl_expediente in data.expedientes:
        encontrados = expedientes_repo.listar_expedientes(ExpedienteFiltro(cl_expediente=cl_expediente))
        if encontrados:
            registros.append(encontrados[0])

    if not registros:
        raise HTTPException(404, "No se encontró información de los expedientes seleccionados.")

    resultado = email_service.enviar_correo_proveedores(
        [r.model_dump() for r in registros],
        usuario_nombre=usuario.get("nombre") or usuario["usuario"],
    )

    # Regla de negocio: mandar el correo pasa el expediente a "En Espera de
    # Respuesta" en automático (nadie lo selecciona a mano). Se guarda quién
    # lo mandó -- el corte lo muestra como "RFC Coordinador".
    identificador = usuario.get("rfc") or usuario.get("usuario") or "desconocido"
    for r in registros:
        estatus_repo.actualizar_estatus(r.expediente, EstatusExpediente.EN_ESPERA_RESPUESTA, identificador)

    return EnviarCorreoProveedoresResponse(
        enviados=resultado.enviados,
        expedientes=[r.expediente for r in registros],
    )


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
    (regla del jefe: un corte de "Abierto" no tiene fecha/RFC de envío que
    mostrar, uno de "En Espera de Respuesta" sí -- mezclar estatus en un
    mismo corte no tendría sentido). Cuando el estatus del lote es
    "En Espera de Respuesta", se agregan las columnas RFC Coordinador y
    Fecha de Envío a Proveedor (de lo contrario van en "NA").
    """
    _requerir_administrador(usuario)

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
    estatus_lote = next(iter(estatuses))

    filas_excel = []
    for r in registros:
        fila = r.model_dump()
        if estatus_lote == EstatusExpediente.EN_ESPERA_RESPUESTA:
            detalle = estatus_repo.obtener_detalle(r.expediente) or {}
            fila["rfc_envio"] = detalle.get("rfc_cambio") or "NA"
            fila["fecha_envio"] = detalle.get("fecha_cambio") or "NA"
        else:
            fila["rfc_envio"] = "NA"
            fila["fecha_envio"] = "NA"
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
def enviar_corte(corte_id: int, usuario: dict = Depends(usuario_actual)):
    """
    "Confirmar y enviar": manda por correo (modo simulado mientras no haya
    SMTP real, ver email_service.py) el MISMO archivo que ya se generó/pudo
    descargarse en /corte -- así lo que se ve/descarga es exactamente lo
    que se envía.
    """
    _requerir_administrador(usuario)
    corte = cortes_repo.obtener_corte(corte_id)
    if not corte:
        raise HTTPException(404, "No se encontró ese corte.")

    usuario_nombre = usuario.get("nombre") or usuario.get("usuario") or "desconocido"
    resultado = email_service.enviar_corte_proveedores(
        cantidad=len(corte["expedientes"]),
        tipo_expediente=corte["tipo_expediente"],
        archivo_nombre=corte["nombre_archivo"],
        archivo_bytes=corte["contenido"],
        usuario_nombre=usuario_nombre,
    )
    cortes_repo.marcar_enviado(corte_id, resultado.destinatarios[0])

    return EnviarCorteResponse(
        enviados=resultado.enviados,
        simulado=resultado.simulado,
        destinatario=resultado.destinatarios[0],
    )
