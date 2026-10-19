"""
Agenda de citas del Directorio de Proveedores.

Qué horarios se ofrecen y cuáles ya están tomados se decide AQUÍ (servidor),
no en el navegador: es el único lugar que sabe de verdad qué citas existen.
Antes la pantalla los inventaba con un hash, así que dos personas veían el
mismo horario libre y nada quedaba registrado.

El bloque de horarios es el mismo para todos los médicos mientras el padrón
no traiga la agenda real de cada consultorio (el Excel solo trae el "horario
de atención" como texto libre, ej. "Lun-Vie 09:00-14:00", que se muestra en
la ficha como referencia).
"""

from datetime import date, timedelta

from app.repositories import citas_proveedor_repo

HORARIOS_BASE = ("09:00", "10:30", "12:00", "13:30", "16:00", "17:30", "19:00")
DIAS_SEMANA = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")

DIAS_AGENDA_DEFAULT = 7
DIAS_AGENDA_MAXIMO = 30


def agenda_disponible(clave_proveedor: str, dias: int = DIAS_AGENDA_DEFAULT) -> list[dict]:
    """Los próximos `dias` días con los horarios que siguen libres."""
    hoy = date.today()
    agenda = []
    for desplazamiento in range(dias):
        dia = hoy + timedelta(days=desplazamiento)
        fecha = dia.isoformat()
        ocupados = set(citas_proveedor_repo.horarios_ocupados(clave_proveedor, fecha))
        libres = [h for h in HORARIOS_BASE if h not in ocupados]
        agenda.append({
            "fecha": fecha,
            "dia_semana": DIAS_SEMANA[dia.weekday()],
            "dia_mes": dia.day,
            "horarios": libres,
            "ocupados": len(ocupados),
        })
    return agenda


def horario_valido(hora: str) -> bool:
    return hora in HORARIOS_BASE


def fecha_valida(fecha: str) -> bool:
    """Una cita no se agenda en el pasado ni más allá de la ventana visible."""
    try:
        dia = date.fromisoformat(fecha)
    except ValueError:
        return False
    hoy = date.today()
    return hoy <= dia <= hoy + timedelta(days=DIAS_AGENDA_MAXIMO)
