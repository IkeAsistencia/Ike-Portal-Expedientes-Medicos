"""
Reglas de negocio del cambio manual de estatus (botón 'Estado del Caso' /
POST /seguimiento/estatus), compartidas entre REST (app/routers/seguimiento.py)
y GraphQL (app/graphql/mutation.py) -- ver nota en seguimiento_service.py
sobre por qué esto vive en un módulo propio en vez de duplicarse en cada
superficie.
"""

from fastapi import HTTPException

from app.repositories import accesos_repo, estatus_repo, expedientes_repo, pago_anticipado_repo, seguimiento_repo
from app.schemas.expediente import EstatusExpediente, ExpedienteFiltro
from app.schemas.seguimiento import SeguimientoInput as SeguimientoInputPydantic
from app.services import email_service
from app.services.seguimiento_service import construir_observaciones_core

# Cabina puede regresar el expediente a Proveedor en cualquiera de estos dos
# estatus -- ambos exigen comentario obligatorio, se escriben en Core y
# disparan una notificación por correo.
ESTATUS_DE_REGRESO = (EstatusExpediente.EN_ESPERA_RESPUESTA, EstatusExpediente.SEGUIMIENTO_CITA)

# Botón "Enviar correo a proveedores" (routers/expedientes.py y
# graphql/mutation.py): solo tiene sentido mandarlo si el expediente todavía
# no se le notificó al proveedor ("Abierto") o si ya se le notificó y se le
# quiere recordar porque no ha respondido ("En Espera de Respuesta"). Los
# demás estados ya están en otra etapa del flujo (el proveedor ya respondió,
# o el caso ya cerró) -- mandarle este correo ahí solo confundiría al proveedor.
ESTATUS_PERMITIDOS_ENVIO_CORREO = (EstatusExpediente.ABIERTO, EstatusExpediente.EN_ESPERA_RESPUESTA)


def validar_seleccion_para_correo(registros: list) -> bool:
    """
    Valida la selección de "Enviar correo a proveedores", compartida entre
    REST (routers/expedientes.py) y GraphQL (graphql/mutation.py) para que
    nunca queden las dos reglas desincronizadas:

      - Todos los expedientes deben estar en ESTATUS_PERMITIDOS_ENVIO_CORREO.
      - Y deben estar TODOS en el mismo estatus (no se vale mezclar "Abierto"
        con "En Espera de Respuesta" en un mismo envío).

    Levanta ValueError con el mensaje ya listo para mostrarle al usuario si
    no cumple (quien llama decide cómo convertirlo: HTTPException en REST,
    Exception en GraphQL). Regresa True si es un recordatorio (la selección
    ya estaba en "En Espera de Respuesta"), False si es una notificación
    nueva (estaba en "Abierto").
    """
    no_permitidos = [r for r in registros if r.estatus not in ESTATUS_PERMITIDOS_ENVIO_CORREO]
    if no_permitidos:
        detalle = ", ".join(f"{r.expediente} ({r.estatus.value})" for r in no_permitidos)
        raise ValueError(
            "Solo se pueden enviar expedientes en estado 'Abierto' o 'En Espera de Respuesta'. "
            f"Quita de tu selección: {detalle}."
        )

    estados_seleccionados = {r.estatus for r in registros}
    if len(estados_seleccionados) > 1:
        raise ValueError(
            "No puedes mezclar expedientes 'Abierto' con 'En Espera de Respuesta' en el mismo envío. "
            "Selecciona solo un tipo a la vez."
        )

    return registros[0].estatus == EstatusExpediente.EN_ESPERA_RESPUESTA


def actualizar_estatus(cl_expediente: int, estatus_valor: str, usuario: dict, comentario: str | None = None) -> dict:
    """Cambia el estatus del expediente a mano. Solo vive en la app (no en SQL Server)."""
    if usuario.get("perfil") == accesos_repo.PERFIL_PROVEEDOR:
        raise HTTPException(403, "El perfil Proveedor no puede cambiar el estado manualmente.")
    try:
        estatus = EstatusExpediente(estatus_valor)
    except ValueError:
        opciones = ", ".join(e.value for e in EstatusExpediente)
        raise HTTPException(400, f"Estado inválido: '{estatus_valor}'. Opciones: {opciones}")
    # Regla de negocio: "En Espera de Respuesta" y "Seguimiento de Cita" se
    # activan solo cuando Cabina regresa el expediente a mano (corrección, o
    # cita aceptada en pago anticipado). Nadie más los puede asignar.
    if estatus in ESTATUS_DE_REGRESO and usuario.get("perfil") != accesos_repo.PERFIL_CABINA:
        raise HTTPException(400, f"'{estatus.value}' no se puede asignar a mano desde este perfil.")
    # "Seguimiento Proveedor" solo se activa automático desde "Actualizar Core"
    # (ver seguimiento_service.py). Cabina no puede ponerlo a mano -- no le
    # corresponde esa etapa.
    if estatus == EstatusExpediente.SEGUIMIENTO_PROVEEDOR and usuario.get("perfil") == accesos_repo.PERFIL_CABINA:
        raise HTTPException(400, "'Seguimiento Proveedor' es automático, Cabina no puede asignarlo a mano.")
    # "Seguimiento de Cita" es exclusivo de expedientes que el Proveedor marcó
    # como pago anticipado -- no tiene sentido en cualquier otro caso.
    if estatus == EstatusExpediente.SEGUIMIENTO_CITA and not pago_anticipado_repo.es_anticipado(cl_expediente):
        raise HTTPException(400, "Este expediente no está marcado como pago anticipado.")

    identificador = usuario.get("rfc") or usuario.get("usuario") or "desconocido"

    if estatus in ESTATUS_DE_REGRESO:
        # Cabina está regresando el expediente a Proveedor: exige el motivo,
        # lo escribe en Core (igual que el comentario del Proveedor) y avisa
        # por correo. No es un simple cambio de estatus como los demás.
        comentario_limpio = (comentario or "").strip()
        if not comentario_limpio:
            raise HTTPException(400, "Debes indicar un comentario para regresar el expediente.")

        cl_usr_app = usuario.get("cl_usr_app")
        if cl_usr_app is None:
            cl_usr_app = accesos_repo.CL_USR_APP_PLACEHOLDER_RFC
        observaciones = construir_observaciones_core(seguimiento_repo.ETIQUETA_CORE_CABINA, usuario, comentario_limpio)
        nombre_usuario = usuario.get("nombre") or usuario.get("rfc") or usuario.get("usuario") or "desconocido"
        try:
            seguimiento_repo.registrar_seguimiento(
                SeguimientoInputPydantic(cl_expediente=cl_expediente, comentario=observaciones),
                cl_usr_app=cl_usr_app,
                nombre=nombre_usuario,
            )
        except seguimiento_repo.ErrorRegistroSeguimiento as e:
            raise HTTPException(503, str(e))
        seguimiento_repo.guardar_comentario_local(cl_expediente, identificador, comentario_limpio, origen="cabina")

        # Pausado a propósito (decisión 2026-10-08): por ahora solo se manda
        # correo en los 2 escenarios confirmados -- "Enviar correo a
        # proveedores" (enviar_correo_proveedores) y "Generar corte"
        # (enviar_corte_proveedores). Este aviso de regreso se retoma cuando
        # se pida su plantilla; mientras tanto, el cambio de estatus, el
        # registro en Core y el comentario local siguen funcionando igual.
        # encontrados = expedientes_repo.listar_expedientes(ExpedienteFiltro(cl_expediente=cl_expediente))
        # if encontrados:
        #     registro = encontrados[0]
        #     email_service.enviar_notificacion_regreso(
        #         cl_expediente, registro.cuenta, registro.nombre_paciente or "N/A", comentario_limpio, identificador,
        #         nuevo_estatus=estatus.value,
        #     )

    estatus_repo.actualizar_estatus(cl_expediente, estatus, identificador)
    return {"cl_expediente": cl_expediente, "estatus": estatus.value}
