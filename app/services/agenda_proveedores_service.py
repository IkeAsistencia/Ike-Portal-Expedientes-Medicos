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

Esos horarios son SOLO una sugerencia rápida: la cita se puede agendar en
cualquier día y a cualquier hora (HH:MM), porque lo normal es que el médico
acepte por teléfono una hora que no está en la lista (ej. 12:45). Lo único que
se exige es que no sea en el pasado y que ese médico no tenga ya otra cita en
ese mismo minuto.
"""

import re
from datetime import date, datetime, timedelta

from app.repositories import citas_proveedor_repo

HORARIOS_BASE = ("09:00", "10:30", "12:00", "13:30", "16:00", "17:30", "19:00")
DIAS_SEMANA = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")

DIAS_AGENDA_DEFAULT = 7
DIAS_AGENDA_MAXIMO = 30   # cuántos días se pueden pedir de golpe en la vista de agenda
DIAS_CITA_MAXIMO = 365    # hasta cuándo se puede agendar una cita (fecha libre)

_PATRON_HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def ahora() -> datetime:
    """Hora local del servidor (aparte para poder fijarla en las pruebas)."""
    return datetime.now()


def agenda_disponible(clave_proveedor: str, dias: int = DIAS_AGENDA_DEFAULT, desde: date | None = None) -> list[dict]:
    """Los próximos `dias` días (a partir de `desde`, por default hoy) con los
    horarios sugeridos que siguen libres. Los de hoy que ya pasaron no se ofrecen."""
    inicio = desde or date.today()
    ahora_local = ahora()
    agenda = []
    for desplazamiento in range(dias):
        dia = inicio + timedelta(days=desplazamiento)
        fecha = dia.isoformat()
        ocupados = set(citas_proveedor_repo.horarios_ocupados(clave_proveedor, fecha))
        libres = [
            h for h in HORARIOS_BASE
            if h not in ocupados and not (dia == ahora_local.date() and h <= ahora_local.strftime("%H:%M"))
        ]
        agenda.append({
            "fecha": fecha,
            "dia_semana": DIAS_SEMANA[dia.weekday()],
            "dia_mes": dia.day,
            "horarios": libres,
            "ocupados": len(ocupados),
        })
    return agenda


def horario_valido(hora: str) -> bool:
    """Cualquier hora del día en formato HH:MM de 24 horas (ej. 12:45)."""
    return bool(_PATRON_HORA.match(hora or ""))


def hora_pasada(fecha: str, hora: str) -> bool:
    """True si esa fecha y hora ya pasaron (una cita de hoy a una hora anterior a la actual)."""
    try:
        momento = datetime.combine(date.fromisoformat(fecha), datetime.strptime(hora, "%H:%M").time())
    except ValueError:
        return False
    return momento <= ahora()


def fecha_valida(fecha: str) -> bool:
    """Una cita no se agenda en un día pasado ni más allá de DIAS_CITA_MAXIMO."""
    try:
        dia = date.fromisoformat(fecha)
    except ValueError:
        return False
    hoy = date.today()
    return hoy <= dia <= hoy + timedelta(days=DIAS_CITA_MAXIMO)
