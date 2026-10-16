import calendar
from datetime import date

from app.db.connection import as_tvp_rows, call_procedure
from app.repositories import cuentas_etiqueta_repo, estatus_repo
from app.schemas.expediente import Expediente, ExpedienteFiltro, EstatusExpediente
from app.services import semaforo_service

MESES_MAXIMOS_RANGO = 3


def _obtener_estatus_y_fecha_cambio(cl_expediente: int) -> tuple[str, str | None]:
    detalle = estatus_repo.obtener_detalle(cl_expediente)
    if not detalle:
        return EstatusExpediente.ABIERTO.value, None
    return detalle["estatus"], detalle["fecha_cambio"]


def _sumar_meses(fecha: date, meses: int) -> date:
    mes_total = fecha.month - 1 + meses
    anio = fecha.year + mes_total // 12
    mes = mes_total % 12 + 1
    dia = min(fecha.day, calendar.monthrange(anio, mes)[1])
    return date(anio, mes, dia)


def _restar_meses(fecha: date, meses: int) -> date:
    return _sumar_meses(fecha, -meses)


def _piso_fecha_inicio() -> date:
    """No se puede consultar información con más antigüedad que esto (hoy - 3 meses)."""
    return _restar_meses(date.today(), MESES_MAXIMOS_RANGO)


def _validar_rango_fechas(filtro: ExpedienteFiltro) -> None:
    """
    Regla de negocio: si se manda alguna de las dos fechas, se deben mandar
    AMBAS -- si no, un usuario podría mandar solo fecha_inicio (ej. "2022")
    y quedar con una consulta sin límite superior, brincándose por completo
    la regla de los 3 meses. Ya con ambas, el RANGO entre ellas no puede
    exceder MESES_MAXIMOS_RANGO meses (evita consultas pesadas contra el
    SP) -- esto NO prohíbe consultar fechas viejas (ej. dentro de 2025),
    solo limita qué tan ancho puede ser el span que se pide de una vez.

    Excepción: si se busca por cl_expediente (número de expediente puntual),
    esta regla NO aplica -- es una búsqueda exacta por clave, no una consulta
    abierta, y no debe importar en qué fechas quedó el expediente.
    """
    if filtro.cl_expediente:
        return
    if filtro.fecha_inicio and not filtro.fecha_fin:
        raise ValueError("Debes indicar también la fecha fin para poder buscar.")
    if filtro.fecha_fin and not filtro.fecha_inicio:
        raise ValueError("Debes indicar también la fecha inicio para poder buscar.")
    if not filtro.fecha_inicio or not filtro.fecha_fin:
        return
    if filtro.fecha_fin < filtro.fecha_inicio:
        raise ValueError("La fecha fin no puede ser anterior a la fecha inicio.")

    fecha_limite = _sumar_meses(filtro.fecha_inicio, MESES_MAXIMOS_RANGO)
    if filtro.fecha_fin > fecha_limite:
        raise ValueError(
            f"El rango de fechas no puede ser mayor a {MESES_MAXIMOS_RANGO} meses."
        )


def listar_expedientes(filtro: ExpedienteFiltro) -> list[Expediente]:
    _validar_rango_fechas(filtro)
    if filtro.cl_expediente:
        # Búsqueda puntual por número de expediente: es una clave exacta --
        # no debe importar fecha, servicio/subservicio ni cuenta, o el
        # expediente podría no aparecer solo porque esos filtros seguían
        # puestos de una búsqueda anterior.
        fecha_inicio_efectiva = None
        fecha_fin_efectiva = None
        cl_servicio_efectivo = None
        cl_subservicio_efectivo = None
        cuentas_tvp = as_tvp_rows([])
    else:
        # Si no mandan fecha_inicio, se acota por default a los últimos 3 meses --
        # así ninguna consulta (ni siquiera la de "entrar al portal") queda sin
        # límite de fechas.
        fecha_inicio_efectiva = filtro.fecha_inicio or _piso_fecha_inicio()
        fecha_fin_efectiva = filtro.fecha_fin
        cl_servicio_efectivo = filtro.cl_servicio
        cl_subservicio_efectivo = filtro.cl_subservicio
        cuentas_tvp = as_tvp_rows(filtro.cuentas or [])

    rows = call_procedure(
        "dbo.ST_CP_ObtenerExpedientesSinProveedorMedico",
        {
            "clExpediente": filtro.cl_expediente,
            "fechaInicio": fecha_inicio_efectiva,
            "fechaFin": fecha_fin_efectiva,
            "clServicio": cl_servicio_efectivo,
            "clSubServicio": cl_subservicio_efectivo,
            "Cuenta": cuentas_tvp,
        },
    )

    etiquetas = cuentas_etiqueta_repo.BuscadorDeEtiquetas()  # una sola lectura por consulta
    resultado: list[Expediente] = []
    for row in rows:
        etiqueta = etiquetas.buscar(row.get("ClCuenta"), row["Cuenta"])
        estatus, fecha_cambio_estatus = _obtener_estatus_y_fecha_cambio(row["Expediente"])
        color_semaforo = semaforo_service.calcular_color(
            cl_sub_servicio=row["ClSubServicio"],
            estatus=estatus,
            fecha_apertura=row["FechaAperturaCompleta"],
            fecha_cambio_estatus=fecha_cambio_estatus,
        )
        resultado.append(
            Expediente(
                expediente=row["Expediente"],
                cuenta=row["Cuenta"],
                tipo_servicio=row["TipoServicio"],
                tipo_subservicio=row["TipoSubservicio"],
                nombre_titular=row.get("NombreTitular"),
                nombre_paciente=row.get("NombrePaciente"),
                especialidad=row.get("Especialidad"),
                entidad=row.get("Entidad"),
                municipio=row.get("Municipio"),
                fecha_apertura_servicio=row["FechaAperturaServicio"],
                fecha_apertura_completa=row["FechaAperturaCompleta"],
                fecha_asignacion_proveedor=row.get("FechaAsignacionProveedor"),
                fecha_cita=row.get("FechaCita"),
                telefono=row.get("Telefono"),
                email=row.get("Email"),
                estatus=estatus,
                color_semaforo=color_semaforo,
                tiempo_semaforo=semaforo_service.tiempo_transcurrido(
                    estatus=estatus,
                    fecha_apertura=row["FechaAperturaCompleta"],
                    fecha_cambio_estatus=fecha_cambio_estatus,
                ),
                cuenta_color=etiqueta["color"] if etiqueta else None,
                cuenta_prefijo=(etiqueta["prefijo"] or None) if etiqueta else None,
            )
        )
    return resultado


def listar_sin_respuesta_proveedor(horas_minimas: int) -> list[dict]:
    """
    Usado por el cron (jobs/validar_estatus_proveedor.py). A diferencia
    de listar_expedientes(), este SP no depende de filtros de pantalla:
    regresa directo los expedientes con proveedor asignado sin cambio
    de estatus desde hace @horas_minimas horas o más.
    """
    return call_procedure(
        "dbo.ST_CP_ObtenerExpedientesSinRespuestaProveedor",
        {"horasMinimas": horas_minimas},
    )
