"""
Validación del RFC y de la cédula profesional del "Alta de médico".

Solo se revisa que el dato ESTÉ BIEN FORMADO; no se consulta al SAT ni al
Registro Nacional de Profesionistas (no hay API pública gratuita y sus
portales tienen captcha). Para confirmar que existen, la pantalla de
Solicitudes ofrece ir directo a cada sitio oficial con el dato ya copiado.

RFC:
  - Persona física: 4 letras + fecha AAMMDD + homoclave de 3 = 13 caracteres.
  - Persona moral:  3 letras + fecha AAMMDD + homoclave de 3 = 12 caracteres.
  Se aceptan los dos: un médico puede facturar como persona física o a
  través de su consultorio constituido como empresa.

  El último carácter es un dígito verificador que el SAT calcula con un
  algoritmo público. Que NO cuadre es una ADVERTENCIA, no un rechazo: hay RFC
  vigentes asignados con un dígito que no sigue el algoritmo (el genérico
  XAXX010101000 es el ejemplo más conocido), y rechazarlos dejaría fuera a un
  médico real. Quien revisa la solicitud ve la advertencia y lo confirma en
  el SAT.
"""
import re
from dataclasses import dataclass
from datetime import date

TIPO_FISICA = "fisica"
TIPO_MORAL = "moral"

_LETRAS_POR_TIPO = {TIPO_FISICA: 4, TIPO_MORAL: 3}
_PATRON_POR_TIPO = {
    TIPO_FISICA: re.compile(r"^[A-ZÑ&]{4}\d{6}[A-Z0-9]{3}$"),
    TIPO_MORAL: re.compile(r"^[A-ZÑ&]{3}\d{6}[A-Z0-9]{3}$"),
}
_TIPO_POR_LARGO = {13: TIPO_FISICA, 12: TIPO_MORAL}

# Valor de cada carácter en el cálculo del dígito verificador (tabla del SAT).
_VALORES_DIGITO = "0123456789ABCDEFGHIJKLMN&OPQRSTUVWXYZ Ñ"

# RFC genéricos del SAT ("público en general" y "residente en el
# extranjero"): no identifican a nadie, así que no sirven para dar de alta.
_RFC_GENERICOS = {"XAXX010101000", "XEXX010101000"}

_PATRON_CEDULA = re.compile(r"^\d{7,8}$")


class DatoInvalido(ValueError):
    """El RFC o la cédula no tienen un formato válido (el mensaje dice por qué)."""


@dataclass(frozen=True)
class RevisionRfc:
    rfc: str               # ya normalizado (mayúsculas, sin espacios ni guiones)
    tipo: str              # TIPO_FISICA o TIPO_MORAL
    digito_correcto: bool  # False = advertencia, ver el docstring del módulo


def normalizar_rfc(texto: str | None) -> str:
    return re.sub(r"[\s-]", "", texto or "").upper()


def digito_verificador(rfc: str) -> str:
    """Dígito verificador que le corresponde a un RFC de 12 o 13 caracteres.
    Al de persona moral se le antepone un espacio para que las dos formas
    pesen igual (así lo define el SAT)."""
    base = rfc[:-1].rjust(12)
    suma = sum(_VALORES_DIGITO.index(c) * (13 - i) for i, c in enumerate(base))
    resultado = 11 - suma % 11
    if resultado == 11:
        return "0"
    if resultado == 10:
        return "A"
    return str(resultado)


def _fecha_existe(aammdd: str) -> bool:
    # El año viene a dos dígitos: basta con que la fecha exista en alguno de
    # los dos siglos (el 29 de febrero depende del siglo).
    aa, mm, dd = int(aammdd[:2]), int(aammdd[2:4]), int(aammdd[4:])
    for siglo in (1900, 2000):
        try:
            date(siglo + aa, mm, dd)
            return True
        except ValueError:
            pass
    return False


def revisar_rfc(texto: str | None) -> RevisionRfc:
    """Lanza DatoInvalido si el RFC está mal formado; si está bien formado,
    regresa su tipo y si el dígito verificador cuadra."""
    rfc = normalizar_rfc(texto)
    if not rfc:
        raise DatoInvalido("El RFC es obligatorio.")
    if rfc in _RFC_GENERICOS:
        raise DatoInvalido(
            "Ese es un RFC genérico del SAT (público en general o extranjero). "
            "Captura el RFC propio del médico o de su consultorio."
        )
    tipo = _TIPO_POR_LARGO.get(len(rfc))
    if tipo is None:
        raise DatoInvalido(
            f"El RFC debe tener 13 caracteres (persona física) o 12 (persona moral); tiene {len(rfc)}."
        )
    letras = _LETRAS_POR_TIPO[tipo]
    if not _PATRON_POR_TIPO[tipo].match(rfc):
        nombre = "física" if tipo == TIPO_FISICA else "moral"
        raise DatoInvalido(
            f"El RFC de persona {nombre} lleva {letras} letras, 6 dígitos de fecha (AAMMDD) "
            "y 3 caracteres de homoclave."
        )
    fecha = rfc[letras:letras + 6]
    if not _fecha_existe(fecha):
        raise DatoInvalido(f"La fecha del RFC ({fecha}) no existe: debe ser año, mes y día (AAMMDD).")
    return RevisionRfc(rfc=rfc, tipo=tipo, digito_correcto=rfc[-1] == digito_verificador(rfc))


def revisar_cedula(texto: str | None) -> str:
    """Regresa la cédula sin espacios, o lanza DatoInvalido."""
    cedula = re.sub(r"\s", "", texto or "")
    if not cedula:
        raise DatoInvalido("La cédula profesional es obligatoria.")
    if not _PATRON_CEDULA.match(cedula):
        raise DatoInvalido("La cédula profesional debe tener 7 u 8 dígitos, sin letras ni espacios.")
    return cedula


_PATRON_CORREO = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")


def revisar_telefono(texto: str | None) -> str:
    """10 dígitos (se aceptan espacios, guiones y paréntesis al escribirlo,
    pero se guarda solo el número)."""
    telefono = re.sub(r"[\s\-().]", "", texto or "")
    if not telefono:
        raise DatoInvalido("El teléfono es obligatorio.")
    if not re.fullmatch(r"\d{10}", telefono):
        raise DatoInvalido("El teléfono debe tener 10 dígitos, solo números.")
    return telefono


def revisar_codigo_postal(texto: str | None) -> str:
    cp = (texto or "").strip()
    if not cp:
        raise DatoInvalido("El código postal es obligatorio.")
    if not re.fullmatch(r"\d{5}", cp):
        raise DatoInvalido("El código postal debe tener 5 dígitos, solo números.")
    return cp


def revisar_correo(texto: str | None) -> str:
    correo = (texto or "").strip()
    if not correo:
        raise DatoInvalido("El correo electrónico es obligatorio.")
    if not _PATRON_CORREO.match(correo):
        raise DatoInvalido("El correo electrónico no tiene un formato válido.")
    return correo


DIAS_SEMANA = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
_DIA = "(?:" + "|".join(DIAS_SEMANA) + ")"
_HORA = r"(?:[01]\d|2[0-3]):[0-5]\d"
# "Lun-Vie 09:00-14:00" | "Lun, Mié, Vie 09:00-14:00" | "Sáb 09:00-13:00": los
# bloques se separan con "; ". Es el mismo texto que arma el selector de la
# pantalla y que ya usa el Excel del padrón.
_BLOQUE_HORARIO = re.compile(rf"^({_DIA}(?:-{_DIA}|(?:, {_DIA})*)) ({_HORA})-({_HORA})$")


def revisar_horario(texto: str | None) -> str:
    """El horario de atención como lo arma el selector: bloques de días con
    su hora de inicio y fin. Cada bloque debe tener inicio menor que fin y los
    rangos de días ("Lun-Vie") deben ir en orden."""
    horario = re.sub(r"\s+", " ", texto or "").strip()
    if not horario:
        raise DatoInvalido("El horario de atención es obligatorio.")
    for bloque in horario.split("; "):
        m = _BLOQUE_HORARIO.match(bloque)
        if not m:
            raise DatoInvalido("El horario de atención no tiene un formato válido: elige los días y la hora de inicio y fin.")
        dias, desde, hasta = m.groups()
        if desde >= hasta:
            raise DatoInvalido("En el horario de atención la hora de inicio debe ser anterior a la hora de fin.")
        if "-" in dias:
            primero, ultimo = dias.split("-")
            if DIAS_SEMANA.index(primero) >= DIAS_SEMANA.index(ultimo):
                raise DatoInvalido("En el horario de atención los días deben ir en orden (por ejemplo Lun-Vie).")
    return horario


# Costo aproximado de consulta: se elige un rango (el costo real varía). Los
# cortes son los mismos del filtro de precio del Directorio ("Hasta $600",
# "Hasta $900", "Hasta $1,200", "Sin límite"), para que el filtro funcione
# exacto con estos médicos.
RANGOS_COSTO = {
    "0-600": "Hasta $600",
    "600-900": "$600 a $900",
    "900-1200": "$900 a $1,200",
    "1200+": "Más de $1,200",
}


def revisar_costo(texto: str | None) -> str:
    costo = (texto or "").strip()
    if not costo:
        raise DatoInvalido("El costo aproximado de consulta es obligatorio.")
    if costo not in RANGOS_COSTO:
        raise DatoInvalido("Elige uno de los rangos de costo aproximado de consulta.")
    return costo


def exigir_texto(texto: str | None, nombre: str) -> str:
    limpio = re.sub(r"\s+", " ", texto or "").strip()
    if not limpio:
        raise DatoInvalido(f"{nombre} es obligatorio.")
    return limpio


def resumen_rfc(texto: str | None) -> dict:
    """Para mostrar en Solicitudes, también con las solicitudes viejas que
    se guardaron sin RFC o con uno mal formado (antes no se validaba)."""
    try:
        revision = revisar_rfc(texto)
    except DatoInvalido:
        return {"tipo": None, "formato_valido": False, "digito_correcto": False}
    return {"tipo": revision.tipo, "formato_valido": True, "digito_correcto": revision.digito_correcto}
