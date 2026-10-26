"""
Agenda de citas del Directorio de Proveedores.

Qué horarios se ofrecen y cuáles ya están tomados se decide AQUÍ (servidor),
no en el navegador: es el único lugar que sabe de verdad qué citas existen.
Antes la pantalla los inventaba con un hash, así que dos personas veían el
mismo horario libre y nada quedaba registrado.

Los horarios sugeridos salen del HORARIO DE ATENCIÓN del médico cuando se
puede leer ("Lun-Vie 09:00-14:00; Sáb 09:00-13:00", el formato que arma el
alta del portal y que trae el Excel): cada media hora dentro de sus rangos, y
nada los días que no atiende. Si el horario no está o viene en otro formato
(texto libre del Excel), se ofrece el bloque genérico HORARIOS_BASE.

La cita se puede agendar a cualquier hora (HH:MM, ej. 12:45), no solo en las
sugeridas, pero DENTRO del horario de atención cuando se conoce: un médico
que consulta de 15:00 a 18:00 no recibe una cita a las 09:00. Además no puede
ser en el pasado ni en el mismo minuto que otra cita de ese médico.
"""

import re
from datetime import date, datetime, timedelta

from app.repositories import citas_proveedor_repo

HORARIOS_BASE = ("09:00", "10:30", "12:00", "13:30", "16:00", "17:30", "19:00")
DIAS_SEMANA = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")

DIAS_AGENDA_DEFAULT = 7
DIAS_AGENDA_MAXIMO = 30   # cuántos días se pueden pedir de golpe en la vista de agenda
DIAS_CITA_MAXIMO = 365    # hasta cuándo se puede agendar una cita (fecha libre)

MINUTOS_ENTRE_SUGERIDOS = 30

_PATRON_HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

# Días como los escribe el selector del alta; también sin acento, por si el
# Excel los trae así.
_INDICE_DIA = {d.lower(): i for i, d in enumerate(DIAS_SEMANA)}
_INDICE_DIA.update({"mie": 2, "sab": 5})
_BLOQUE = re.compile(r"^(.+?)\s+((?:[01]\d|2[0-3]):[0-5]\d)\s*-\s*((?:[01]\d|2[0-3]):[0-5]\d)$")


def ahora() -> datetime:
    """Hora local del servidor (aparte para poder fijarla en las pruebas)."""
    return datetime.now()


def _dias_de(texto: str) -> list[int] | None:
    texto = texto.strip().lower()
    if "-" in texto and "," not in texto:
        partes = [p.strip() for p in texto.split("-")]
        if len(partes) != 2 or partes[0] not in _INDICE_DIA or partes[1] not in _INDICE_DIA:
            return None
        a, b = _INDICE_DIA[partes[0]], _INDICE_DIA[partes[1]]
        return list(range(a, b + 1)) if a <= b else None
    dias = [_INDICE_DIA.get(p.strip()) for p in texto.split(",")]
    return None if any(d is None for d in dias) else dias


def horario_por_dia(horario: str | None) -> dict[int, list[tuple[str, str]]] | None:
    """
    El horario de atención como {día (0 = Lun): [(desde, hasta), ...]}.
    None si no hay horario o no se puede leer completo: en ese caso no se
    restringe nada (mejor sugerir de más que bloquear una cita válida por un
    texto que no entendimos).
    """
    if not horario or not horario.strip():
        return None
    resultado: dict[int, list[tuple[str, str]]] = {}
    for bloque in re.split(r"\s*;\s*", horario.strip()):
        m = _BLOQUE.match(bloque)
        if not m:
            return None
        dias = _dias_de(m.group(1))
        desde, hasta = m.group(2), m.group(3)
        if not dias or desde >= hasta:
            return None
        for d in dias:
            resultado.setdefault(d, []).append((desde, hasta))
    return resultado


def _horas_cada(desde: str, hasta: str, minutos: int) -> list[str]:
    actual = datetime.strptime(desde, "%H:%M")
    fin = datetime.strptime(hasta, "%H:%M")
    horas = []
    while actual < fin:
        horas.append(actual.strftime("%H:%M"))
        actual += timedelta(minutes=minutos)
    return horas


def fuera_del_horario(horario: str | None, fecha: str, hora: str) -> str | None:
    """Si la cita cae fuera del horario de atención del médico, el mensaje
    para mostrar; None si está dentro o si el horario no se conoce."""
    por_dia = horario_por_dia(horario)
    if por_dia is None:
        return None
    try:
        dia = date.fromisoformat(fecha).weekday()
    except ValueError:
        return None
    rangos = por_dia.get(dia)
    if not rangos:
        return f"El médico no atiende ese día. Su horario de atención es: {horario.strip()}."
    if not any(desde <= hora < hasta for desde, hasta in rangos):
        return f"Esa hora queda fuera del horario de atención del médico ({horario.strip()})."
    return None


def agenda_disponible(
    clave_proveedor: str, dias: int = DIAS_AGENDA_DEFAULT, desde: date | None = None, horario: str | None = None,
) -> list[dict]:
    """Los próximos `dias` días (a partir de `desde`, por default hoy) con los
    horarios sugeridos que siguen libres. Los de hoy que ya pasaron no se
    ofrecen. `atiende` es False los días fuera de su horario de atención."""
    inicio = desde or date.today()
    ahora_local = ahora()
    por_dia = horario_por_dia(horario)
    agenda = []
    for desplazamiento in range(dias):
        dia = inicio + timedelta(days=desplazamiento)
        fecha = dia.isoformat()
        if por_dia is None:
            sugeridos, atiende = list(HORARIOS_BASE), True
        else:
            rangos = por_dia.get(dia.weekday(), [])
            sugeridos = sorted({h for d, h_fin in rangos for h in _horas_cada(d, h_fin, MINUTOS_ENTRE_SUGERIDOS)})
            atiende = bool(rangos)
        ocupados = set(citas_proveedor_repo.horarios_ocupados(clave_proveedor, fecha))
        libres = [
            h for h in sugeridos
            if h not in ocupados and not (dia == ahora_local.date() and h <= ahora_local.strftime("%H:%M"))
        ]
        agenda.append({
            "fecha": fecha,
            "dia_semana": DIAS_SEMANA[dia.weekday()],
            "dia_mes": dia.day,
            "horarios": libres,
            "ocupados": len(ocupados),
            "atiende": atiende,
            "segun_horario": por_dia is not None,
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
