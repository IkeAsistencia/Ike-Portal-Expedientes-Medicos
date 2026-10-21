"""
Texto que se copia al campo "Observaciones" de Seguimiento cuando el Proveedor
coordina una cita desde el Directorio de Proveedores.

Antes el Proveedor tenía que escribir a mano con qué médico, a qué hora, el
domicilio y los datos de contacto. Ahora todo eso ya está en el padrón y en la
cita, así que se arma aquí -- en el servidor, para que el formato sea siempre
el mismo y esté probado -- y la pantalla solo lo pega en el campo para que el
Proveedor lo revise, le agregue notas y presione "Actualizar Seguimiento".

Un dato vacío no se imprime (una línea que dijera "Convenio: " sin nada no
informa), salvo teléfono y correo: ahí lo útil es saber que NO están
registrados, para llamar o buscar otro medio.
"""

from datetime import date

from app.services.agenda_proveedores_service import DIAS_SEMANA

# Lo que cabe en Observaciones es 1500 caracteres menos el encabezado con el
# nombre de quien escribe (ver app/repositories/seguimiento_repo.py); este
# tope deja margen para que el Proveedor agregue sus notas.
LARGO_MAXIMO_TEXTO = 1000


def _limpio(valor) -> str:
    return "" if valor is None else " ".join(str(valor).split())


def _domicilio(proveedor: dict) -> str:
    cp = _limpio(proveedor.get("codigo_postal"))
    partes = [
        _limpio(proveedor.get("calle_num_ext_int")),
        _limpio(proveedor.get("colonia")),
        f"C.P. {cp.zfill(5)}" if cp.isdigit() else cp,
        _limpio(proveedor.get("municipio")),
        _limpio(proveedor.get("estado")),
    ]
    return ", ".join(p for p in partes if p)


def _costo(valor) -> str:
    texto = _limpio(valor)
    if not texto:
        return ""
    return texto if texto.startswith("$") else (f"${texto}" if texto.replace(".", "", 1).isdigit() else texto)


def _fecha_hora(fecha: str, hora: str) -> str:
    try:
        dia = date.fromisoformat(fecha)
    except ValueError:
        return f"{fecha} {hora} hrs"
    return f"{DIAS_SEMANA[dia.weekday()]} {dia.strftime('%d/%m/%Y')}, {hora} hrs"


def observaciones_de_cita(proveedor: dict, cita: dict, paciente: str | None) -> str:
    lineas = [f"CITA COORDINADA - Folio {cita['folio']}"]

    def agregar(etiqueta: str, valor, siempre: bool = False, vacio: str = "No registrado") -> None:
        texto = _limpio(valor)
        if texto:
            lineas.append(f"{etiqueta}: {texto}")
        elif siempre:
            lineas.append(f"{etiqueta}: {vacio}")

    agregar("Paciente", paciente)
    agregar("Médico", proveedor.get("nombre"))
    agregar("Especialidad", proveedor.get("especialidad"))
    agregar("Consultorio", proveedor.get("consultorio"))
    agregar("Domicilio", _domicilio(proveedor))
    agregar("Teléfono", proveedor.get("telefono"), siempre=True)
    agregar("Correo", proveedor.get("email"), siempre=True)
    agregar("Fecha y hora de la cita", _fecha_hora(cita["fecha"], cita["hora"]))
    agregar("Horario de atención", proveedor.get("horario"))
    agregar("Costo de consulta", _costo(proveedor.get("costo_consulta")))
    agregar("Convenio", proveedor.get("convenio"))
    if proveedor.get("teleconsulta"):
        agregar("Teleconsulta", "Sí")
    agregar("Clave del proveedor", proveedor.get("clave"))

    texto = "\n".join(lineas)
    return texto if len(texto) <= LARGO_MAXIMO_TEXTO else texto[: LARGO_MAXIMO_TEXTO - 1].rstrip() + "…"
