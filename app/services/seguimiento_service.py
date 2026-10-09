"""
Reglas de negocio de 'Actualizar Core' (botón del Proveedor), compartidas
entre REST (app/routers/seguimiento.py) y GraphQL (app/graphql/mutation.py).

Antes, la mutation de GraphQL llamaba directo a seguimiento_repo sin pasar
por ninguna de estas reglas (perfil Cabina bloqueado, longitud mínima del
comentario, expediente en el estatus correcto, comprobante de pago
anticipado obligatorio) -- lo que permitía a cualquier usuario autenticado
escribir en Core saltándose todas las validaciones que sí tiene el REST.
Centralizar la lógica aquí garantiza que ambas superficies impongan
exactamente las mismas reglas.
"""

from fastapi import HTTPException

from app.repositories import accesos_repo, comprobantes_repo, estatus_repo, expedientes_repo, pago_anticipado_repo, seguimiento_repo
from app.schemas.expediente import EstatusExpediente, ExpedienteFiltro
from app.schemas.seguimiento import SeguimientoInput as SeguimientoInputPydantic

LONGITUD_MINIMA_COMENTARIO_PROVEEDOR = 50


def construir_observaciones_core(etiqueta: str, usuario: dict, comentario: str) -> str:
    """Arma el texto que se inserta en Core con el encabezado de quién lo
    escribió (ver seguimiento_repo.observaciones_para_core) y valida que
    quepa en @Observaciones: si no, se rechaza en vez de que SQL Server lo
    corte en silencio."""
    nombre = usuario.get("nombre") or usuario.get("rfc") or usuario.get("usuario") or "desconocido"
    observaciones = seguimiento_repo.observaciones_para_core(etiqueta, nombre, comentario)
    sobran = len(observaciones) - seguimiento_repo.LONGITUD_MAXIMA_OBSERVACIONES_CORE
    if sobran > 0:
        raise HTTPException(
            400,
            f"El comentario es demasiado largo para Core: quítale {sobran} caracter(es). "
            f"El registro admite {seguimiento_repo.LONGITUD_MAXIMA_OBSERVACIONES_CORE} caracteres "
            "contando el encabezado con tu nombre.",
        )
    return observaciones


def actualizar_seguimiento(cl_expediente: int, comentario: str, usuario: dict) -> dict:
    """
    Botón 'Actualizar Core': inserta el registro en dbo.Seguimiento.
    Solo el perfil Proveedor (o una sesión SISE sin perfil, para no romper
    lo ya existente) puede usar esto — Cabina lo tiene bloqueado.
    Al completarse, si quien lo hizo es Proveedor, el estatus del
    expediente pasa automáticamente a "Seguimiento Proveedor" — nunca antes.
    """
    if usuario.get("perfil") == accesos_repo.PERFIL_CABINA:
        raise HTTPException(403, "El perfil Cabina no tiene acceso a Registrar seguimiento.")
    comentario_limpio = comentario.strip()
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
        encontrados = expedientes_repo.listar_expedientes(ExpedienteFiltro(cl_expediente=cl_expediente))
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
        and pago_anticipado_repo.es_anticipado(cl_expediente)
        and not comprobantes_repo.existe_comprobante(cl_expediente)
    ):
        raise HTTPException(400, "Debes subir el comprobante de pago antes de continuar.")

    cl_usr_app = usuario.get("cl_usr_app")
    if cl_usr_app is None:
        # Ver nota en accesos_repo.CL_USR_APP_PLACEHOLDER_RFC.
        cl_usr_app = accesos_repo.CL_USR_APP_PLACEHOLDER_RFC

    # Pago anticipado: el comentario del Proveedor debe empezar con "PA-"
    # (así lo identifican en Core). El portal ya lo pone al marcar la
    # casilla; esto lo garantiza aunque lo borren a mano.
    if pago_anticipado_repo.es_anticipado(cl_expediente) and not comentario_limpio.startswith(
        seguimiento_repo.PREFIJO_PAGO_ANTICIPADO
    ):
        comentario_limpio = seguimiento_repo.PREFIJO_PAGO_ANTICIPADO + comentario_limpio

    observaciones = construir_observaciones_core(seguimiento_repo.ETIQUETA_CORE_PROVEEDOR, usuario, comentario_limpio)
    nombre_usuario = usuario.get("nombre") or usuario.get("rfc") or usuario.get("usuario") or "desconocido"
    try:
        resultado = seguimiento_repo.registrar_seguimiento(
            SeguimientoInputPydantic(cl_expediente=cl_expediente, comentario=observaciones),
            cl_usr_app=cl_usr_app,
            nombre=nombre_usuario,
        )
    except seguimiento_repo.ErrorRegistroSeguimiento as e:
        raise HTTPException(503, str(e))

    # Copia local (sin el encabezado: el portal ya muestra quién lo escribió).
    # Cabina no puede escribir aquí, pero sí necesita poder leerlo.
    identificador = usuario.get("rfc") or usuario.get("usuario") or "desconocido"
    seguimiento_repo.guardar_comentario_local(cl_expediente, identificador, comentario_limpio, origen="proveedor")

    if es_proveedor:
        estatus_repo.actualizar_estatus(cl_expediente, EstatusExpediente.SEGUIMIENTO_PROVEEDOR, identificador)
        # A partir del primer envío, si marcó (o no) la casilla de pago
        # anticipado, ya no se puede volver a cambiar.
        pago_anticipado_repo.bloquear(cl_expediente)

    return resultado
