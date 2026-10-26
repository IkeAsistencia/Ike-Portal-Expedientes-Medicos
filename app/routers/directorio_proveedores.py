from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.security import usuario_actual
from app.repositories import (
    catalogos_repo,
    citas_proveedor_repo,
    especialidades_repo,
    proveedores_repo,
)
from app.repositories.accesos_repo import PERFIL_ADMINISTRADOR, PERFIL_CABINA
from app.services import (
    agenda_proveedores_service,
    cita_texto_service,
    coordinar_cita_service,
    denue_service,
)


def _requerir_proveedor_o_administrador(usuario: dict = Depends(usuario_actual)) -> dict:
    """El Directorio de Proveedores (pantalla "Proveedores", ver
    frontend/js/directorio/*.js) es para los perfiles Proveedor y
    Administrador -- Cabina no lo usa (mismo criterio que
    pantallaPermitida("directorio-proveedores") en frontend/js/app.js)."""
    if usuario.get("perfil") == PERFIL_CABINA:
        raise HTTPException(403, "El Directorio de Proveedores no aplica para el perfil Cabina.")
    return usuario


router = APIRouter(
    prefix="/directorio-proveedores",
    tags=["Directorio de Proveedores"],
    dependencies=[Depends(_requerir_proveedor_o_administrador)],
)


def _requerir_proveedor(usuario: dict = Depends(usuario_actual)) -> dict:
    """Buscar fuera de la red, consultar la agenda y agendar: solo Proveedor.
    El Administrador usa del directorio solo Solicitudes, Alta de médico,
    Carga del catálogo y Métricas (que leen el padrón y las especialidades)."""
    coordinar_cita_service.exigir_perfil_que_coordina(usuario)
    return usuario


class CitaInput(BaseModel):
    clave_proveedor: str = Field(min_length=1, max_length=20)
    fecha: str = Field(min_length=10, max_length=10, description="YYYY-MM-DD")
    hora: str = Field(min_length=5, max_length=5, description="HH:MM")
    # Toda cita es para un expediente (ver app/services/coordinar_cita_service.py):
    # el paciente sale de ahí y cada expediente tiene una sola cita activa.
    cl_expediente: int = Field(ge=1)


@router.get("")
def listar():
    """
    El padrón completo, con los dos orígenes en la misma lista y cada uno
    marcado para que la pantalla los distinga (ver mapearProveedor en
    frontend/js/directorio/datos.js):
      - origen='catalogo' -> llegó en la carga de Excel ("Dentro de la red":
        tiene convenio con IKE).
      - origen='portal'   -> se dio de alta aquí ("Alta rápida": aprobado en
        el portal, sin el proceso formal de convenio).
    Todos traen `clave` (PRV-000001), que es con lo que se agenda una cita:
    no cambia entre cargas, así que las citas nunca quedan huérfanas.
    El frontend busca/filtra sobre esta lista en el navegador.
    """
    return proveedores_repo.listar_padron()


@router.get("/especialidades")
def listar_especialidades():
    """
    Catálogo de especialidades con el KPI de cada una, para las tarjetas del
    Directorio (ver app/repositories/especialidades_repo.py).

    Viene en el orden de `orden_kpi`, ya partido para la pantalla:
      - `tarjetas`: las primeras 16 (4 renglones de 4).
      - `combo`:    el resto, incluidas las que no traen orden asignado.
    Las dos listas traen el mismo contenido por especialidad, así que elegir
    una del combo funciona igual que picarle a una tarjeta.

    `dentro_de_red` / `fuera_de_red` son conteos REALES del padrón, amarrados
    por proveedores.cl_especialidad: una especialidad en 0 significa que no
    hay a quién mandar, no que falte el dato.
    """
    todas = especialidades_repo.kpis()
    corte = especialidades_repo.MAXIMO_TARJETAS_KPI
    # Las que no traen orden nunca van en tarjeta (decisión del usuario):
    # kpis() ya las deja al final, así que basta con cortar.
    con_orden = [x for x in todas if x["orden_kpi"] is not None]
    tarjetas = con_orden[:corte]
    claves_en_tarjeta = {x["cl_especialidad"] for x in tarjetas}
    return {
        "total": len(todas),
        "maximo_tarjetas": corte,
        "tarjetas": tarjetas,
        "combo": [x for x in todas if x["cl_especialidad"] not in claves_en_tarjeta],
    }


@router.get("/fuera-de-red", dependencies=[Depends(_requerir_proveedor)])
def buscar_fuera_de_red(
    cod_ent: str = Query(min_length=1, max_length=5, description="CodEnt de la entidad (ej. JC)"),
    especialidad: str = Query(min_length=3, max_length=60),
    cod_mun: str | None = Query(default=None, max_length=10, description="CodMD del municipio (ej. 00039)"),
):
    """
    Candidatos a contratar cuando no hay nadie de la red en esa zona: son
    consultorios del DENUE (INEGI), NO proveedores del portal.

    No se guarda nada: cada consulta va en vivo al INEGI. Para incorporar a
    uno hay que darlo de alta por "Alta de médico", con su validación de
    cédula y la aprobación de un Administrador -- el DENUE solo dice que ahí
    hay un consultorio, no que esté certificado ni que acepte las tarifas.

    OJO con `tipo_consultado`: el DENUE clasifica por tipo de consultorio, no
    por especialidad médica, así que la especialidad solo sirve para elegir
    el tipo (ver app/services/denue_service.py). La pantalla lo avisa.
    """
    clave_inegi = catalogos_repo.clave_inegi_de_entidad(cod_ent)
    if clave_inegi is None:
        raise HTTPException(400, f'La entidad "{cod_ent}" no está en el catálogo.')

    try:
        candidatos, tipo = denue_service.buscar_candidatos(clave_inegi, cod_mun, especialidad)
    except denue_service.DenueNoConfigurado as e:
        raise HTTPException(503, str(e))
    except denue_service.ErrorDenue as e:
        raise HTTPException(502, str(e))

    return {
        "fuente": "DENUE (INEGI)",
        "area": denue_service.construir_area(clave_inegi, cod_mun),
        "tipo_consultado": tipo,
        "tipo_descripcion": denue_service.ETIQUETA_TIPO.get(tipo, tipo),
        "total": len(candidatos),
        "candidatos": candidatos,
    }


@router.get("/citas")
def listar_citas(clave_proveedor: str | None = Query(default=None, max_length=20)):
    return citas_proveedor_repo.listar_citas(clave_proveedor)


@router.post("/citas", dependencies=[Depends(_requerir_proveedor)])
def agendar_cita(data: CitaInput, usuario: dict = Depends(usuario_actual)):
    proveedor = proveedores_repo.obtener_por_clave(data.clave_proveedor)
    if proveedor is None:
        raise HTTPException(404, "No se encontró ese proveedor en el padrón.")
    if not agenda_proveedores_service.fecha_valida(data.fecha):
        raise HTTPException(
            400,
            "La fecha de la cita debe ser de hoy en adelante y dentro de los próximos "
            f"{agenda_proveedores_service.DIAS_CITA_MAXIMO} días.",
        )
    if not agenda_proveedores_service.horario_valido(data.hora):
        raise HTTPException(400, "La hora debe tener el formato HH:MM de 24 horas (por ejemplo 12:45).")
    if agenda_proveedores_service.hora_pasada(data.fecha, data.hora):
        raise HTTPException(400, "Esa hora de hoy ya pasó: elige una posterior o cambia la fecha.")
    fuera_de_horario = agenda_proveedores_service.fuera_del_horario(proveedor.get("horario"), data.fecha, data.hora)
    if fuera_de_horario:
        raise HTTPException(400, fuera_de_horario)

    expediente = coordinar_cita_service.expediente_para_coordinar(data.cl_expediente, usuario)
    paciente = expediente.nombre_paciente
    vigente = citas_proveedor_repo.cita_activa_de_expediente(data.cl_expediente)
    if vigente:
        raise HTTPException(409, _mensaje_expediente_con_cita(vigente))

    rfc_usuario = usuario.get("rfc") or usuario.get("usuario") or "desconocido"
    try:
        cita = citas_proveedor_repo.agendar(
            data.clave_proveedor, data.fecha, data.hora, paciente, rfc_usuario, data.cl_expediente
        )
    except citas_proveedor_repo.HorarioOcupado as e:
        raise HTTPException(409, str(e))
    except citas_proveedor_repo.ExpedienteConCita as e:
        raise HTTPException(409, str(e))
    return {
        **cita,
        "proveedor_nombre": proveedor["nombre"],
        "proveedor_especialidad": proveedor["especialidad"],
        # Lo que la pantalla pega en "Observaciones" para revisarlo (ver
        # app/services/cita_texto_service.py).
        "observaciones_sugeridas": cita_texto_service.observaciones_de_cita(proveedor, cita, paciente),
    }


@router.get("/expedientes-para-cita", dependencies=[Depends(_requerir_proveedor)])
def expedientes_para_cita(usuario: dict = Depends(usuario_actual)):
    """Los expedientes a los que se les puede agendar cita ahora (estatus
    accionable y sin cita activa): la lista del paso "¿Para qué expediente?"
    al agendar desde el directorio. Mismo formato que GET /expedientes."""
    return coordinar_cita_service.expedientes_para_cita(usuario)


def _mensaje_expediente_con_cita(cita: dict) -> str:
    medico = cita.get("proveedor_nombre") or "un médico"
    return (
        f"Este expediente ya tiene una cita agendada con {medico} "
        f"({cita['fecha']} a las {cita['hora']}, folio {cita['folio']}). "
        "Para agendar otra, primero cancela la que tiene."
    )


@router.get("/citas/expediente/{cl_expediente}")
def cita_del_expediente(cl_expediente: int, usuario: dict = Depends(usuario_actual)):
    """La cita vigente de un expediente, con el texto listo para copiar a
    Observaciones. Regresa {"cita": null} si no tiene."""
    if usuario.get("perfil") != PERFIL_ADMINISTRADOR:
        # El nombre del paciente viaja en la cita: solo se entrega si el
        # Proveedor realmente puede actuar sobre ese expediente.
        coordinar_cita_service.expediente_para_coordinar(cl_expediente, usuario)
    cita = citas_proveedor_repo.cita_activa_de_expediente(cl_expediente)
    if not cita:
        return {"cita": None}
    proveedor = proveedores_repo.obtener_por_clave(cita["clave_proveedor"]) or {}
    return {"cita": {**cita, "observaciones_sugeridas": cita_texto_service.observaciones_de_cita(
        proveedor, cita, cita.get("paciente"))}}


class CancelarCitaInput(BaseModel):
    motivo: str = Field(min_length=1, max_length=coordinar_cita_service.MOTIVO_CANCELACION_MAXIMO + 100)


@router.post("/citas/{folio}/cancelar")
def cancelar_cita(folio: str, data: CancelarCitaInput, usuario: dict = Depends(usuario_actual)):
    """Cancelar exige el motivo, y la cancelación queda en la bitácora del
    expediente (ver coordinar_cita_service.cancelar_cita)."""
    return coordinar_cita_service.cancelar_cita(folio, data.motivo, usuario)


@router.get("/{clave}/agenda", dependencies=[Depends(_requerir_proveedor)])
def agenda(
    clave: str,
    dias: int = Query(
        default=agenda_proveedores_service.DIAS_AGENDA_DEFAULT,
        ge=1,
        le=agenda_proveedores_service.DIAS_AGENDA_MAXIMO,
    ),
    desde: str | None = Query(default=None, description="YYYY-MM-DD; por default hoy"),
):
    """Horarios sugeridos que siguen libres de ese proveedor (los ya apartados
    no salen), dentro de su horario de atención si se puede leer. Con `desde`
    se consulta otro día (ej. el que se eligió en la fecha libre)."""
    proveedor = proveedores_repo.obtener_por_clave(clave)
    if proveedor is None:
        raise HTTPException(404, "No se encontró ese proveedor en el padrón.")
    if desde is not None and not agenda_proveedores_service.fecha_valida(desde):
        raise HTTPException(400, "La fecha debe ser de hoy en adelante y dentro del tiempo permitido.")
    inicio = date.fromisoformat(desde) if desde else None
    return agenda_proveedores_service.agenda_disponible(clave, dias, inicio, proveedor.get("horario"))
