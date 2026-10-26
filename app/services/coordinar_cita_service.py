"""
Reglas para agendar una cita: SIEMPRE es para un expediente.

Se llega por dos caminos y los dos terminan igual (regresan a Seguimiento del
expediente con los datos de la cita copiados en Observaciones):
  - "Coordinar cita" en Seguimiento: el expediente ya viene elegido.
  - Desde el Directorio de Proveedores por el menú: al presionar "Agendar" se
    elige el expediente (ver expedientes_para_cita).

Reglas:
  - Coordina solo el perfil Proveedor (ver PERFILES_QUE_COORDINAN).
  - El expediente tiene que seguir en una etapa en la que se puede actuar:
    "En Espera de Respuesta" o "Seguimiento de Cita" -- las mismas que
    habilitan "Registrar seguimiento" al Proveedor (ver seguimiento_service.py).
  - El paciente sale del expediente, no de lo que mande el navegador.
  - Un expediente tiene UNA sola cita activa; para cambiarla primero se cancela.
"""

from fastapi import HTTPException

from app.repositories import (
    accesos_repo, citas_proveedor_repo, estatus_repo, expedientes_repo, pago_anticipado_repo, proveedores_repo,
    seguimiento_repo,
)
from app.schemas.expediente import EstatusExpediente, Expediente, ExpedienteFiltro
from app.schemas.seguimiento import SeguimientoInput
from app.services import cita_texto_service
from app.services.seguimiento_service import construir_observaciones_bitacora

MOTIVO_CANCELACION_MINIMO = 10
MOTIVO_CANCELACION_MAXIMO = 500

ESTATUS_PARA_COORDINAR = (EstatusExpediente.EN_ESPERA_RESPUESTA, EstatusExpediente.SEGUIMIENTO_CITA)
# Solo el Proveedor agenda (2026-10-26): una cita termina en el Seguimiento del
# expediente, pantalla que el Administrador no tiene. El Administrador en el
# directorio solo revisa solicitudes, da de alta médicos, carga el catálogo y
# ve métricas.
PERFILES_QUE_COORDINAN = (accesos_repo.PERFIL_PROVEEDOR,)


def exigir_perfil_que_coordina(usuario: dict) -> None:
    if usuario.get("perfil") not in PERFILES_QUE_COORDINAN:
        raise HTTPException(403, "Agendar citas es exclusivo del perfil Proveedor.")


def expediente_para_coordinar(cl_expediente: int, usuario: dict) -> Expediente:
    """Regresa el expediente si se le puede coordinar cita; si no, lanza el
    error con un mensaje listo para mostrarse."""
    exigir_perfil_que_coordina(usuario)
    encontrados = expedientes_repo.listar_expedientes(ExpedienteFiltro(cl_expediente=cl_expediente))
    if not encontrados:
        raise HTTPException(404, "No se encontró el expediente.")
    expediente = encontrados[0]
    if expediente.estatus not in ESTATUS_PARA_COORDINAR:
        raise HTTPException(
            400, "Este expediente ya no está en espera de respuesta, no puedes coordinar ni cambiar su cita."
        )
    return expediente


def cancelar_cita(folio: str, motivo: str, usuario: dict) -> dict:
    """
    Cancela una cita con su motivo y lo deja asentado en la BITÁCORA del
    expediente (dbo.Seguimiento, la misma que "Actualizar Seguimiento"), además
    de la copia local de comentarios que muestra el portal.

    A diferencia de "Actualizar Seguimiento", este registro NO cambia el
    estatus del expediente: se cancela para agendar otra, así que el
    expediente tiene que seguir en manos de quien coordina.

    Si la bitácora no se puede escribir (falla de conexión con el sistema
    central), la cita NO se cancela: una cancelación sin su registro no debe
    existir. El intento queda en la bitácora propia del portal para revisión
    (ver seguimiento_repo.registrar_fallo_local).
    """
    motivo_limpio = " ".join((motivo or "").split())
    if len(motivo_limpio) < MOTIVO_CANCELACION_MINIMO:
        raise HTTPException(
            400, f"Escribe el motivo de la cancelación (al menos {MOTIVO_CANCELACION_MINIMO} caracteres)."
        )
    if len(motivo_limpio) > MOTIVO_CANCELACION_MAXIMO:
        raise HTTPException(400, f"El motivo no puede pasar de {MOTIVO_CANCELACION_MAXIMO} caracteres.")

    cita = citas_proveedor_repo.obtener_por_folio(folio)
    if cita is None or cita["estatus"] != citas_proveedor_repo.ESTATUS_AGENDADA:
        raise HTTPException(404, "No se encontró esa cita agendada.")

    # Una cita ligada a un expediente solo se cambia mientras todavía se puede
    # actuar sobre él; después queda en manos del coordinador. Las citas viejas
    # sin expediente (de antes de que fuera obligatorio) solo las cancela el
    # Administrador.
    es_admin = usuario.get("perfil") == accesos_repo.PERFIL_ADMINISTRADOR
    if not es_admin:
        if not cita["cl_expediente"]:
            raise HTTPException(403, "Esta cita no está ligada a un expediente: solo un Administrador puede cancelarla.")
        expediente_para_coordinar(cita["cl_expediente"], usuario)

    identificador = usuario.get("rfc") or usuario.get("usuario") or "desconocido"
    if cita["cl_expediente"]:
        _registrar_cancelacion_en_bitacora(cita, motivo_limpio, usuario, identificador)

    if not citas_proveedor_repo.cancelar(folio, motivo_limpio, identificador):
        raise HTTPException(404, "No se encontró esa cita agendada.")
    return {"ok": True, "registrada_en_bitacora": bool(cita["cl_expediente"])}


def _registrar_cancelacion_en_bitacora(cita: dict, motivo: str, usuario: dict, identificador: str) -> None:
    cl_expediente = cita["cl_expediente"]
    proveedor = proveedores_repo.obtener_por_clave(cita["clave_proveedor"]) or {}
    comentario = cita_texto_service.texto_cancelacion(proveedor, cita, motivo)
    # Mismo criterio que "Actualizar Seguimiento": en pago anticipado, lo que
    # escribe el portal en la bitácora empieza con "PA-".
    if pago_anticipado_repo.es_anticipado(cl_expediente):
        comentario = seguimiento_repo.PREFIJO_PAGO_ANTICIPADO + comentario
    observaciones = construir_observaciones_bitacora(seguimiento_repo.ETIQUETA_BITACORA_PROVEEDOR, usuario, comentario)
    cl_usr_app = usuario.get("cl_usr_app")
    if cl_usr_app is None:
        cl_usr_app = accesos_repo.CL_USR_APP_PLACEHOLDER_RFC
    nombre = usuario.get("nombre") or identificador
    try:
        seguimiento_repo.registrar_seguimiento(
            SeguimientoInput(cl_expediente=cl_expediente, comentario=observaciones), cl_usr_app=cl_usr_app, nombre=nombre,
        )
    except seguimiento_repo.ErrorRegistroSeguimiento as e:
        raise HTTPException(
            503, "No se canceló la cita: no se pudo registrar la cancelación en la bitácora del expediente. " + str(e)
        )
    seguimiento_repo.guardar_comentario_local(cl_expediente, identificador, comentario, origen="proveedor")


def expedientes_para_cita(usuario: dict) -> list[Expediente]:
    """
    Los expedientes a los que se les puede agendar cita ahora: en estatus
    accionable y sin una cita activa. Es la lista del paso "¿Para qué
    expediente?" del Directorio.

    El estatus vive en la base local, así que de ahí salen los candidatos. Sus
    datos (paciente, especialidad, zona) vienen del sistema central: primero
    con UNA consulta del rango por default (los últimos meses, igual que la
    pantalla Expedientes) y, solo para los que no hayan salido ahí (más
    viejos), uno por uno.
    """
    exigir_perfil_que_coordina(usuario)
    candidatos = estatus_repo.expedientes_en_estatus(ESTATUS_PARA_COORDINAR)
    candidatos -= citas_proveedor_repo.expedientes_con_cita_activa()
    if not candidatos:
        return []

    encontrados = {
        e.expediente: e
        for e in expedientes_repo.listar_expedientes(ExpedienteFiltro())
        if e.expediente in candidatos
    }
    for cl in candidatos - encontrados.keys():
        uno = expedientes_repo.listar_expedientes(ExpedienteFiltro(cl_expediente=cl))
        if uno:
            encontrados[cl] = uno[0]

    # El estatus se vuelve a revisar con el dato ya armado (pudo cambiar entre
    # las dos lecturas). Los más recientes primero.
    return sorted(
        (e for e in encontrados.values() if e.estatus in ESTATUS_PARA_COORDINAR),
        key=lambda e: e.expediente,
        reverse=True,
    )
