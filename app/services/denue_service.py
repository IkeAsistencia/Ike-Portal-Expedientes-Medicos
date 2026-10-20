"""
Búsqueda FUERA DE LA RED contra el DENUE del INEGI (Directorio Estadístico
Nacional de Unidades Económicas).

Para qué: cuando el Directorio de Proveedores no encuentra a nadie de la red
para un tipo de consulta y una zona, esto ofrece consultorios de esa misma
zona como CANDIDATOS a contratar -- no como proveedores del portal.

Por qué el DENUE y no un scraping de un portal de médicos:
  - Es dato público de gobierno, con API oficial y gratuita; los portales
    comerciales del ramo lo prohíben expresamente en sus términos de uso.
  - Lista UNIDADES ECONÓMICAS (consultorios y clínicas), no personas con
    nombre, cédula y reseñas -- mucho menor exposición de datos personales.

Y justo por eso un resultado de aquí NO entra al padrón automáticamente: el
DENUE dice "aquí hay un consultorio de medicina especializada", no "este
médico está certificado y acepta nuestras tarifas". Un candidato se vuelve
proveedor pasando por "Alta de médico", con su validación de cédula y la
aprobación de un Administrador.

Nada de lo que regresa se guarda: cada búsqueda consulta en vivo (decisión
del usuario, 2026-10-20).

⚠️ LIMITACIÓN IMPORTANTE, verificada contra la API real el 2026-10-20: el
DENUE clasifica por TIPO DE CONSULTORIO, no por especialidad médica. Todas
las especialidades (cardiología, pediatría, dermatología, ginecología...)
caen en la misma clase 621113 "Consultorios de medicina especializada". No
existe forma de pedirle "solo cardiología": lo más fino que da es "los
consultorios de medicina especializada de este municipio". Por eso la
pantalla avisa que hay que confirmar la especialidad real al contactarlos.

Documentación: https://www.inegi.org.mx/servicios/api_denue.html
"""

import logging
import unicodedata
from urllib.parse import quote

import httpx

from app.config import get_settings
from app.core.log_seguro import sanear_para_log

logger = logging.getLogger("denue_service")

_BASE = "https://www.inegi.org.mx/app/api/denue/v1/consulta/BuscarAreaAct"

# Orden REAL de los parámetros de BuscarAreaAct, confirmado probando contra la
# API el 2026-10-20 (la documentación solo muestra un ejemplo con ceros, que
# se presta a interpretarlo mal):
#
#   entidad / municipio / localidad / ageb / manzana /
#   sector / subsector / rama / subrama / nombre /
#   registro_inicial / registro_final / estrato / token
#
# Dos detalles que costaron encontrar:
#   - entidad y municipio van SEPARADOS (no "14039" en un solo campo).
#   - la clave de actividad va en la posición de su nivel: una rama de 4
#     dígitos va en "rama", no en la primera posición de actividad.
_PLANTILLA_RUTA = (
    "{entidad}/{municipio}/0/0/0/{sector}/{subsector}/{rama}/{subrama}/{nombre}/"
    "1/{maximo}/0"
)

# Clases del SCIAN que el DENUE reporta de verdad para consultorios --
# enumeradas consultando la API (Guadalajara, 2026-10-20), no tomadas de un
# catálogo que pudiera estar desfasado. Se incluyen las del sector público:
# existen pocas, pero el usuario decide si le sirven.
CLASES_POR_TIPO = {
    "medicina_general": ("621111", "621112"),
    "medicina_especializada": ("621113", "621114"),
    "clinicas_consultorios": ("621115", "621116"),
    "dental": ("621211", "621212"),
    "quiropractica": ("621311",),
    "optometria": ("621320",),
    "psicologia": ("621331", "621332"),
    "audiologia_terapia": ("621341", "621342"),
    "nutricion": ("621391",),
    "otros_cuidado_salud": ("621398", "621399"),
}

# Especialidades que hay que resolver por nombre COMPLETO, porque como
# pedazo de texto chocan con otra regla de la tabla de abajo:
#   - "CLINICA" a secas sí es una clínica de consultorios, pero "ALERGOLOGIA
#     E INMUNOLOGIA CLINICA" es medicina especializada y también contiene
#     "clinica".
#   - "OPTICA" es una óptica; buscarla como pedazo de texto no sirve porque
#     ninguna de las reglas de abajo la cubre.
# (Salieron al conectar el catálogo de especialidades del portal, que trae
# estos nombres -- ver app/repositories/especialidades_repo.py.)
_TIPO_EXACTO = {
    "clinica": "clinicas_consultorios",
    "optica": "optometria",
}

# Qué tipo de consultorio buscar según la especialidad que pidió el usuario.
# Lo que no esté aquí cae en "medicina especializada", que es donde el DENUE
# mete a todas las especialidades médicas.
#
# El orden IMPORTA: gana la primera regla que aparezca como pedazo del
# nombre. Por eso "cirugia" va antes que "general": "CIRUGIA GENERAL" es un
# cirujano (medicina especializada), no un médico general.
_TIPO_POR_ESPECIALIDAD = {
    "cirugia": "medicina_especializada",
    "medicina general": "medicina_general",
    "general": "medicina_general",
    "odontologia": "dental",
    "dental": "dental",
    "dentista": "dental",
    "psicologia": "psicologia",
    "psicolog": "psicologia",
    "nutricion": "nutricion",
    "nutriolog": "nutricion",
    "optometria": "optometria",
    "oftalmologia": "optometria",
    "quiropractica": "quiropractica",
    "audiologia": "audiologia_terapia",
    "terapia": "audiologia_terapia",
    "fisioterapia": "audiologia_terapia",
}

TIPO_DEFAULT = "medicina_especializada"

# Descripción legible de cada tipo, para que la pantalla diga qué se buscó.
ETIQUETA_TIPO = {
    "medicina_general": "consultorios de medicina general",
    "medicina_especializada": "consultorios de medicina especializada",
    "clinicas_consultorios": "clínicas de consultorios médicos",
    "dental": "consultorios dentales",
    "quiropractica": "consultorios de quiropráctica",
    "optometria": "consultorios de optometría",
    "psicologia": "consultorios de psicología",
    "audiologia_terapia": "consultorios de audiología y terapia",
    "nutricion": "consultorios de nutriólogos y dietistas",
    "otros_cuidado_salud": "otros consultorios para el cuidado de la salud",
}


class DenueNoConfigurado(Exception):
    """Falta DENUE_TOKEN en el .env -- la búsqueda fuera de la red está apagada."""


class ErrorDenue(Exception):
    """El DENUE no respondió, tardó demasiado o devolvió algo inesperado.
    El mensaje ya viene listo para mostrarse al usuario."""


def _normalizar(texto: str) -> str:
    """Minúsculas y sin acentos, para comparar especialidades."""
    base = (texto or "").strip().lower()
    return "".join(c for c in unicodedata.normalize("NFD", base) if unicodedata.category(c) != "Mn")


def tipo_para(especialidad: str) -> str:
    """Qué tipo de consultorio del DENUE corresponde a esa especialidad."""
    normalizada = _normalizar(especialidad)
    # Primero por nombre completo, luego por pedazo de texto: si no, un
    # nombre como "CLINICA" lo acabaría resolviendo una regla más general.
    if normalizada in _TIPO_EXACTO:
        return _TIPO_EXACTO[normalizada]
    for llave, tipo in _TIPO_POR_ESPECIALIDAD.items():
        if llave in normalizada:
            return tipo
    return TIPO_DEFAULT


def partir_area(clave_inegi_entidad: str, cod_mun: str | None) -> tuple[str, str]:
    """
    (entidad, municipio) como los pide el DENUE, en parámetros separados.

    El portal guarda el municipio como CodMD del sistema central, con ceros a
    la izquierda ("00039"); el DENUE quiere 3 dígitos ("039"). Municipio "0"
    = toda la entidad.
    """
    entidad = str(clave_inegi_entidad).strip().zfill(2)
    solo_digitos = "".join(c for c in (cod_mun or "") if c.isdigit())
    if not solo_digitos:
        return entidad, "0"
    return entidad, solo_digitos[-3:].zfill(3)


def construir_area(clave_inegi_entidad: str, cod_mun: str | None) -> str:
    """Clave de área legible para mostrar y diagnosticar ("14039" o "14")."""
    entidad, municipio = partir_area(clave_inegi_entidad, cod_mun)
    return entidad if municipio == "0" else entidad + municipio


def _a_float(valor) -> float | None:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _a_candidato(fila: dict) -> dict:
    """
    Una fila del DENUE con la misma forma que usa el padrón, para que la
    pantalla la pinte con el mismo componente.

    Lo que NO se inventa: no hay cédula, costo de consulta, convenio ni
    horario -- el DENUE no los tiene. Se dejan fuera a propósito, en vez de
    rellenarlos con algo verosímil que después nadie pueda distinguir de un
    dato real.
    """
    calle = " ".join(
        parte for parte in (
            (fila.get("Tipo_vialidad") or "").strip().title(),
            (fila.get("Calle") or "").strip(),
            (fila.get("Num_Exterior") or "").strip(),
        ) if parte
    )
    interior = (fila.get("Num_Interior") or "").strip()
    if interior:
        calle = f"{calle}, Int. {interior}" if calle else f"Int. {interior}"

    return {
        # Identificador del DENUE, NO una clave del portal: así es imposible
        # confundir un candidato con un proveedor ya dado de alta.
        "id_denue": str(fila.get("Id") or "").strip(),
        "nombre": (fila.get("Nombre") or "").strip(),
        "razon_social": (fila.get("Razon_social") or "").strip(),
        "especialidad": (fila.get("Clase_actividad") or "").strip(),
        "clase_actividad_id": str(fila.get("CLASE_ACTIVIDAD_ID") or "").strip(),
        "calle_num_ext_int": calle,
        "colonia": (fila.get("Colonia") or "").strip(),
        "codigo_postal": (fila.get("CP") or "").strip(),
        "ubicacion": (fila.get("Ubicacion") or "").strip(),
        "telefono": (fila.get("Telefono") or "").strip(),
        "email": (fila.get("Correo_e") or "").strip(),
        "sitio_internet": (fila.get("Sitio_internet") or "").strip(),
        "latitud": _a_float(fila.get("Latitud")),
        "longitud": _a_float(fila.get("Longitud")),
        "origen": "fuera_de_red",
    }


def buscar_candidatos(
    clave_inegi_entidad: str, cod_mun: str | None, especialidad: str
) -> tuple[list[dict], str]:
    """
    Consultorios del DENUE en esa zona, como candidatos a contratar.
    Devuelve (candidatos, tipo_consultado). Lista vacía si no hay ninguno
    (no es un error).

    La especialidad se usa para elegir QUÉ TIPO de consultorio pedirle al
    DENUE (ver la limitación en el encabezado del módulo); además, si el
    nombre del establecimiento la menciona, esos resultados se muestran
    primero.

    Lanza DenueNoConfigurado si falta el token y ErrorDenue si el servicio no
    respondió -- los dos con mensaje listo para el usuario.
    """
    settings = get_settings()
    if not settings.denue_configurado:
        raise DenueNoConfigurado(
            "La búsqueda fuera de la red no está configurada todavía: falta el token del DENUE "
            "(INEGI) en el archivo .env del servidor."
        )

    entidad, municipio = partir_area(clave_inegi_entidad, cod_mun)
    tipo = tipo_para(especialidad)

    candidatos: list[dict] = []
    vistos: set[str] = set()
    for clase in CLASES_POR_TIPO[tipo]:
        # La clase del SCIAN es de 6 dígitos, así que va en la posición de
        # "subrama" (el DENUE acepta ahí hasta el nivel de clase); rama y
        # subrama superiores quedan en 0 para no contradecirla.
        ruta = _PLANTILLA_RUTA.format(
            entidad=entidad, municipio=municipio,
            sector="0", subsector="0", rama="0", subrama=clase,
            nombre="0", maximo=settings.denue_maximo_resultados,
        )
        for fila in _consultar(f"{_BASE}/{ruta}/{quote(settings.denue_token.strip(), safe='')}"):
            candidato = _a_candidato(fila)
            if candidato["id_denue"] and candidato["id_denue"] in vistos:
                continue
            vistos.add(candidato["id_denue"])
            candidatos.append(candidato)

    # Los que mencionan la especialidad en su nombre van primero: son los que
    # con más probabilidad la atienden de verdad.
    termino = _normalizar(especialidad)
    if termino:
        candidatos.sort(key=lambda c: termino not in _normalizar(c["nombre"]))

    return candidatos[: settings.denue_maximo_resultados], tipo


def _consultar(url: str) -> list[dict]:
    settings = get_settings()
    try:
        respuesta = httpx.get(url, timeout=settings.denue_timeout_segundos)
    except httpx.TimeoutException as e:
        raise ErrorDenue(
            "El servicio del INEGI tardó demasiado en responder. Vuelve a intentarlo en un momento."
        ) from e
    except httpx.HTTPError as e:
        raise ErrorDenue("No fue posible conectar con el servicio del INEGI.") from e

    if respuesta.status_code == 404:
        # El DENUE responde 404 cuando la consulta es válida pero no hay
        # coincidencias -- no es un fallo, es "no encontré nada".
        return []
    if respuesta.status_code in (401, 403):
        raise ErrorDenue("El token del DENUE (INEGI) no es válido o ya expiró.")
    if respuesta.status_code != 200:
        # El token viaja en la URL: nunca se registra completa en el log.
        logger.warning(
            "El DENUE respondió %s en la consulta de candidatos (área: %s)",
            respuesta.status_code,
            sanear_para_log(url.split("/BuscarAreaAct/")[-1].split("/0/0/0/")[0]),
        )
        raise ErrorDenue("El servicio del INEGI respondió con un error. Intenta más tarde.")

    try:
        datos = respuesta.json()
    except ValueError as e:
        raise ErrorDenue("El servicio del INEGI devolvió una respuesta que no se pudo interpretar.") from e

    # Sin coincidencias el DENUE NO devuelve una lista vacía: responde 404, o
    # bien HTTP 200 con una cadena JSON ("" o "No hay resultados. ").
    # Comprobado contra la API real, por eso se trata como "no encontré nada"
    # y no como un fallo.
    if datos is None or isinstance(datos, str):
        return []
    if not isinstance(datos, list):
        raise ErrorDenue("El servicio del INEGI devolvió una respuesta inesperada.")
    return [f for f in datos if isinstance(f, dict)]
