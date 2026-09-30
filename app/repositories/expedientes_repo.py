import calendar
from datetime import date

from app.db.connection import as_tvp_rows, call_procedure
from app.db.local_store import get_local_connection
from app.schemas.expediente import Expediente, ExpedienteFiltro, EstatusExpediente

MESES_MAXIMOS_RANGO = 3


def _obtener_estatus(cl_expediente: int) -> str:
    with get_local_connection() as conn:
        row = conn.execute(
            "SELECT estatus FROM estatus_expediente WHERE cl_expediente = ?",
            (cl_expediente,),
        ).fetchone()
        return row["estatus"] if row else EstatusExpediente.ABIERTO.value


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
        "dbo.ObtenerExpedientesSinProveedorMedico",
        {
            "clExpediente": filtro.cl_expediente,
            "fechaInicio": fecha_inicio_efectiva,
            "fechaFin": fecha_fin_efectiva,
            "clServicio": cl_servicio_efectivo,
            "clSubServicio": cl_subservicio_efectivo,
            "Cuenta": cuentas_tvp,
        },
    )

    resultado: list[Expediente] = []
    for row in rows:
        estatus = _obtener_estatus(row["Expediente"])
        resultado.append(
            Expediente(
                expediente=row["Expediente"],
                cuenta=row["Cuenta"],
                tipo_servicio=row["TipoServicio"],
                tipo_subservicio=row["TipoSubservicio"],
                nombre_titular=row.get("NombreTitular"),
                nombre_paciente=row["NombrePaciente"],
                especialidad=row.get("Especialidad"),
                entidad=row.get("Entidad"),
                municipio=row.get("Municipio"),
                fecha_apertura_servicio=row["FechaAperturaServicio"],
                fecha_asignacion_proveedor=row.get("FechaAsignacionProveedor"),
                fecha_cita=row.get("FechaCita"),
                telefono=row.get("Telefono"),
                email=row.get("Email"),
                estatus=estatus,
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
        "dbo.ObtenerExpedientesSinRespuestaProveedor",
        {"horasMinimas": horas_minimas},
    )
