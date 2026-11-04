"""
"Enviar correo a proveedores": a quién le llega, el tope diario y el freno
de reenvío. Lo usan REST (routers/expedientes.py) y GraphQL
(graphql/mutation.py), para que las dos vías apliquen exactamente las mismas
reglas.

Reglas (acordadas 2026-10-29):
  - Sale UN solo correo, igual para todos, con la lista completa de la
    selección. Le llega, en copia oculta, a los proveedores (perfil
    Proveedor, activos, con correo) cuya entidad aparece en al menos un
    expediente de la selección. Los de otras entidades no reciben nada: la
    entidad sirve para que cada quien priorice lo de su estado (todos los
    proveedores pueden atender cualquier expediente desde el portal).
  - Freno de reenvío: un expediente que recibió correo hace menos de
    CORREO_REENVIO_HORAS no se puede volver a mandar. Si la selección trae
    alguno, no se manda nada y se dice cuál y a partir de cuándo se podrá.
  - Tope diario (cuota_correos_service.py): cerca del tope se pide
    confirmación antes de enviar. Si el correo ya no cabe, NO sale, pero los
    expedientes igual pasan a "En Espera de Respuesta" para que el proveedor
    los atienda desde su portal.
"""

import unicodedata
from datetime import datetime, timedelta

from fastapi import HTTPException

from app.config import get_settings
from app.repositories import accesos_repo, correos_enviados_repo, estatus_repo, expedientes_repo
from app.schemas.correo import EnviarCorreoProveedoresResponse
from app.schemas.expediente import EstatusExpediente, ExpedienteFiltro
from app.services import cuota_correos_service, email_service, estatus_service

MOTIVO_LIMITE = "limite"
MOTIVO_SIN_PROVEEDORES = "sin_proveedores"
SIN_ENTIDAD = "Sin entidad"

# Mismo criterio que normalizarEntidad (frontend/js/core/formato.js), con el
# que el portal del proveedor ya filtra por entidad: SQL Server manda
# "CIUDAD DE MEXICO" y el catálogo de accesos dice "Ciudad de México"; y
# dbo.cEntFed llama al Estado de México simplemente "MEXICO".
_ALIAS_ENTIDAD = {"ESTADO DE MEXICO": "MEXICO"}

_FRENO_MAXIMO_EN_MENSAJE = 10
_FORMATO_FECHA = "%Y-%m-%d %H:%M:%S"


def normalizar_entidad(texto: str | None) -> str:
    base = "".join(
        c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn"
    ).upper().strip()
    return _ALIAS_ENTIDAD.get(base, base)


_NOMBRE_EN_CATALOGO = {normalizar_entidad(e): e for e in accesos_repo.ENTIDADES_MEXICO}


def _nombre_entidad(texto: str | None) -> str:
    """Cómo se le muestra la entidad a Cabina ("Ciudad de México", no "CIUDAD DE MEXICO")."""
    if not texto or not texto.strip():
        return SIN_ENTIDAD
    return _NOMBRE_EN_CATALOGO.get(normalizar_entidad(texto), texto.strip())


def _requerir_cabina(usuario: dict) -> None:
    perfil = usuario.get("perfil")
    if perfil == accesos_repo.PERFIL_ADMINISTRADOR:
        raise HTTPException(403, "El perfil Administrador no tiene acceso a esta acción.")
    if perfil == accesos_repo.PERFIL_PROVEEDOR:
        raise HTTPException(403, "El perfil Proveedor no tiene acceso a esta acción.")


def _cargar_registros(cl_expedientes: list[int]) -> list:
    registros = []
    for cl_expediente in cl_expedientes:
        encontrados = expedientes_repo.listar_expedientes(ExpedienteFiltro(cl_expediente=cl_expediente))
        if encontrados:
            registros.append(encontrados[0])
    if not registros:
        raise HTTPException(404, "No se encontró información de los expedientes seleccionados.")
    return registros


def _revisar_freno(registros: list) -> None:
    """Rechaza toda la selección si algún expediente recibió correo hace muy poco."""
    horas = get_settings().correo_reenvio_horas
    if horas <= 0:
        return
    desde = (datetime.now() - timedelta(hours=horas)).strftime(_FORMATO_FECHA)
    ultimos = correos_enviados_repo.ultimo_correo_desde([r.expediente for r in registros], desde)
    if not ultimos:
        return

    def cuando(fecha: str) -> str:
        return (datetime.strptime(fecha, _FORMATO_FECHA) + timedelta(hours=horas)).strftime("%Y-%m-%d %H:%M")

    frenados = sorted(ultimos.items(), key=lambda par: par[1])
    detalle = ", ".join(f"{exp} (a partir de {cuando(fecha)})" for exp, fecha in frenados[:_FRENO_MAXIMO_EN_MENSAJE])
    if len(frenados) > _FRENO_MAXIMO_EN_MENSAJE:
        detalle += f" y {len(frenados) - _FRENO_MAXIMO_EN_MENSAJE} más"
    raise HTTPException(
        400,
        f"No se envió nada: a los proveedores ya se les mandó correo de estos expedientes hace menos de "
        f"{horas} horas. Podrás reenviarlos: {detalle}. Quítalos de tu selección para enviar los demás.",
    )


def _destinatarios(registros: list) -> tuple[list[str], list[str]]:
    """
    (correos de los proveedores a los que les llega, entidades de la
    selección que no tienen ningún proveedor). Un proveedor dado de alta en
    una entidad que no aparece en la selección no recibe nada.
    """
    entidades = {}
    for r in registros:
        entidades.setdefault(normalizar_entidad(r.entidad), _nombre_entidad(r.entidad))

    correos: dict[str, str] = {}  # minúsculas -> como se capturó (sin repetir)
    cubiertas = set()
    for proveedor in accesos_repo.listar_proveedores_con_correo():
        entidad = normalizar_entidad(proveedor["entidad"])
        if entidad and entidad in entidades:
            cubiertas.add(entidad)
            correos.setdefault(proveedor["correo"].lower(), proveedor["correo"])

    sin_proveedor = sorted(nombre for clave, nombre in entidades.items() if clave not in cubiertas)
    return sorted(correos.values(), key=str.lower), sin_proveedor


def _cuantos(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _los_expedientes(n: int) -> str:
    return "el expediente" if n == 1 else f"los {n} expedientes"


def _aviso_para_confirmar(cuota, unidades: int, expedientes: int) -> str:
    pasaran = "pasará" if expedientes == 1 else "pasarán"
    sin_correo = (
        f"Si continúas, no se enviará correo: {_los_expedientes(expedientes)} {pasaran} a "
        "\"En Espera de Respuesta\" y los proveedores los verán en su portal."
    )
    if cuota.usados >= cuota.limite:
        return f"Ya se alcanzó el límite de {cuota.limite} correos por día. {sin_correo}"
    if cuota.usados + unidades > cuota.limite:
        return (
            f"Este envío necesita {_cuantos(unidades, 'correo', 'correos')} y solo quedan {cuota.restantes} de los "
            f"{cuota.limite} del día. {sin_correo}"
        )
    return (
        f"Estás a punto de alcanzar el límite de correos por día: van {cuota.usados} de {cuota.limite} "
        f"y este envío usa {unidades}. ¿Quieres continuar?"
    )


def _mensaje_resultado(
    motivo: str | None, destinatarios: int, expedientes: int, sin_proveedor: list[str], limite: int, simulado: bool
) -> str:
    quedaron = "quedó" if expedientes == 1 else "quedaron"
    quedaron = f"{_los_expedientes(expedientes).capitalize()} {quedaron} en \"En Espera de Respuesta\""
    if motivo == MOTIVO_LIMITE:
        return (
            f"Se alcanzó el límite de {limite} correos por día: no se envió correo. "
            f"{quedaron} y los proveedores los verán en su portal."
        )
    if motivo == MOTIVO_SIN_PROVEEDORES:
        return f"No se envió correo: no hay proveedores dados de alta en {', '.join(sin_proveedor)}. {quedaron}."
    mensaje = (
        f"Correo enviado a {_cuantos(destinatarios, 'proveedor', 'proveedores')} con "
        f"{_cuantos(expedientes, 'expediente', 'expedientes')}."
    )
    if sin_proveedor:
        mensaje += f" Sin proveedor dado de alta en: {', '.join(sin_proveedor)}."
    if simulado:
        mensaje += " (Simulado: falta configurar el SMTP.)"
    return mensaje


def enviar_a_proveedores(
    cl_expedientes: list[int], usuario: dict, confirmar_limite: bool = False
) -> EnviarCorreoProveedoresResponse:
    _requerir_cabina(usuario)
    registros = _cargar_registros(cl_expedientes)
    try:
        es_recordatorio = estatus_service.validar_seleccion_para_correo(registros)
    except ValueError as e:
        raise HTTPException(400, str(e))
    _revisar_freno(registros)

    destinatarios, sin_proveedor = _destinatarios(registros)
    unidades = cuota_correos_service.unidades_para(len(destinatarios))
    cuota = cuota_correos_service.estado()

    if unidades and not confirmar_limite and cuota.usados + unidades >= cuota.aviso:
        return EnviarCorreoProveedoresResponse(
            enviados=0,
            expedientes=[],
            destinatarios=len(destinatarios),
            entidades_sin_proveedor=sin_proveedor,
            requiere_confirmacion=True,
            mensaje=_aviso_para_confirmar(cuota, unidades, len(registros)),
            usados_hoy=cuota.usados,
            limite_diario=cuota.limite,
        )

    motivo = None if unidades else MOTIVO_SIN_PROVEEDORES
    reserva = cuota_correos_service.reservar("proveedores", unidades) if unidades else None
    if unidades and reserva is None:
        motivo = MOTIVO_LIMITE

    simulado = True
    if motivo is None:
        try:
            resultado = email_service.enviar_correo_proveedores(
                [r.model_dump() for r in registros],
                usuario_nombre=usuario.get("nombre") or usuario.get("usuario") or "desconocido",
                destinatarios=destinatarios,
                es_recordatorio=es_recordatorio,
            )
        except email_service.ErrorEnvioCorreo:
            cuota_correos_service.liberar(reserva)
            raise HTTPException(
                503,
                "No se pudo enviar el correo: el servidor de correo no respondió. No se cambió ningún "
                "expediente; intenta de nuevo en unos minutos.",
            )
        simulado = resultado.simulado

    identificador = usuario.get("rfc") or usuario.get("usuario") or "desconocido"
    correos_enviados_repo.registrar_envio(
        tipo="recordatorio" if es_recordatorio else "nuevo",
        destinatario=", ".join(destinatarios) if motivo is None else "",
        expedientes=[r.expediente for r in registros],
        rfc_envio=identificador,
        simulado=simulado,
        motivo_sin_correo=motivo,
    )

    # Regla de negocio: mandar el correo pasa el expediente a "En Espera de
    # Respuesta" en automático (nadie lo selecciona a mano), AUNQUE no haya
    # salido correo por el tope: así el proveedor lo ve y lo atiende desde su
    # portal. Se guarda quién lo mandó -- el corte lo muestra como "RFC Coordinador".
    for r in registros:
        estatus_repo.actualizar_estatus(r.expediente, EstatusExpediente.EN_ESPERA_RESPUESTA, identificador)

    cuota = cuota_correos_service.estado()
    return EnviarCorreoProveedoresResponse(
        enviados=len(registros),
        expedientes=[r.expediente for r in registros],
        correo_enviado=motivo is None,
        motivo_sin_correo=motivo,
        destinatarios=len(destinatarios),
        entidades_sin_proveedor=sin_proveedor,
        mensaje=_mensaje_resultado(motivo, len(destinatarios), len(registros), sin_proveedor, cuota.limite, simulado),
        simulado=simulado,
        usados_hoy=cuota.usados,
        limite_diario=cuota.limite,
    )
