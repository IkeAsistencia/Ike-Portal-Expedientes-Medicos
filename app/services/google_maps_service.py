"""
Búsqueda FUERA DE LA RED contra Google Maps (Places API), como alternativa
al DENUE del INEGI (ver app/services/denue_service.py) dentro de la misma
pantalla del Directorio de Proveedores.

Para qué: igual que con el DENUE, cuando el padrón no tiene nadie de la red
para una especialidad y una zona, esto ofrece establecimientos de esa zona
como CANDIDATOS a contratar -- no como proveedores del portal.

Por qué una alternativa y no un reemplazo del DENUE:
  - El DENUE es gratis y clasifica por ESTABLECIMIENTO (no por persona): es
    la opción por default, sin costo y con menor exposición de datos
    personales (ver el porqué detallado en denue_service.py).
  - Google Maps sí indexa el giro real del negocio (buscar "cardiólogo"
    regresa cardiólogos, no "consultorios de medicina especializada" en
    general como el DENUE) y trae señales útiles para decidir a quién
    contactar primero (calificación, si está abierto). A cambio: cada
    consulta tiene costo (requiere una llave de Google Cloud con
    facturación activa) y los resultados sí pueden traer el nombre del
    médico y reseñas de pacientes -- más exposición de datos personales
    que el DENUE.
  - Por eso la pantalla deja elegir la fuente en cada búsqueda, en vez de
    sustituir una por la otra.

Por qué Text Search y no Nearby Search: Nearby Search exige coordenadas
(lat/lng) del centro de búsqueda, que este portal no tiene por municipio;
Text Search acepta un texto libre ("cardiólogo en Mérida, Yucatán, México")
y es Google quien resuelve la zona -- mismo nivel de información que ya
maneja el DENUE con entidad/municipio, sin necesitar geocodificación aparte.

Por qué NO se trae el teléfono real de cada resultado: Google Places solo
regresa teléfono/sitio web con una llamada de "Place Details" POR CADA
lugar (una consulta adicional, con su propio costo, por cada candidato). Para
no multiplicar el gasto por el número de resultados, aquí se usa únicamente
lo que ya trae la búsqueda de texto (nombre, dirección, calificación, si
está abierto) y se entrega un enlace directo a la ficha de Google Maps del
lugar, desde donde el usuario puede ver el teléfono si lo necesita.

Nada de lo que regresa se guarda: cada búsqueda consulta en vivo (misma
decisión que con el DENUE, 2026-10-20). Un resultado de aquí tampoco entra
al padrón automáticamente: un candidato se vuelve proveedor pasando por
"Alta de médico", con su validación de cédula y la aprobación de un
Administrador -- Google solo dice que ahí hay un lugar con ese giro, no que
esté certificado ni que acepte las tarifas.

Documentación: https://developers.google.com/maps/documentation/places/web-service/text-search
"""

import logging

import httpx

from app.config import get_settings
from app.core.log_seguro import sanear_para_log

logger = logging.getLogger("google_maps_service")

_BASE = "https://maps.googleapis.com/maps/api/place/textsearch/json"

# Mensaje legible por cada "status" que puede regresar la Places API (no son
# códigos HTTP: la API casi siempre responde 200 y el resultado real viene
# en este campo). Lo que no esté aquí cae en el genérico de abajo.
_MENSAJES_ESTADO = {
    "OVER_QUERY_LIMIT": (
        "Se alcanzó el límite de consultas de Google Maps (cuota o presupuesto diario). "
        "Intenta más tarde o revisa el presupuesto del proyecto en Google Cloud."
    ),
    "REQUEST_DENIED": (
        "Google Maps rechazó la consulta: revisa que la llave (GOOGLE_MAPS_API_KEY) sea "
        "válida, que la \"Places API\" esté habilitada y que la facturación del proyecto esté activa."
    ),
    "INVALID_REQUEST": "La búsqueda no se pudo completar: faltó información para construirla.",
}
_MENSAJE_GENERICO = "Google Maps devolvió una respuesta inesperada. Intenta más tarde."


class GoogleMapsNoConfigurado(Exception):
    """Falta GOOGLE_MAPS_API_KEY en el .env -- esta alternativa está apagada."""


class ErrorGoogleMaps(Exception):
    """Google Maps no respondió, tardó demasiado o devolvió algo inesperado.
    El mensaje ya viene listo para mostrarse al usuario."""


def construir_consulta(especialidad: str, nombre_entidad: str, nombre_municipio: str | None) -> str:
    """Texto libre que se le manda a Google ("cardiología en Mérida,
    Yucatán, México"); sin municipio, busca en toda la entidad."""
    zona = f"{nombre_municipio.strip()}, {nombre_entidad.strip()}" if nombre_municipio else nombre_entidad.strip()
    return f"{especialidad.strip()} en {zona}, México"


def _a_candidato(lugar: dict) -> dict:
    """
    Un resultado de Google con una forma parecida a la del DENUE (ver
    denue_service._a_candidato), para reusar el mismo tipo de tarjeta en la
    pantalla, con sus propios campos donde la fuente es distinta.

    Lo que NO se inventa: no hay cédula, costo de consulta, convenio ni
    teléfono -- igual que con el DENUE, se deja fuera en vez de rellenarlo
    con algo que después nadie podría distinguir de un dato real.
    """
    ubicacion = ((lugar.get("geometry") or {}).get("location")) or {}
    apertura = lugar.get("opening_hours") or {}
    place_id = (lugar.get("place_id") or "").strip()
    return {
        # Identificador de Google, NO una clave del portal -- igual que
        # id_denue, para que sea imposible confundirlo con un proveedor ya
        # dado de alta.
        "place_id": place_id,
        "nombre": (lugar.get("name") or "").strip(),
        "direccion": (lugar.get("formatted_address") or "").strip(),
        "calificacion": lugar.get("rating"),
        "total_calificaciones": lugar.get("user_ratings_total"),
        "abierto_ahora": apertura.get("open_now"),
        "latitud": ubicacion.get("lat"),
        "longitud": ubicacion.get("lng"),
        # Ficha pública del lugar en Google Maps -- de ahí el usuario puede
        # ver teléfono, sitio web y horario sin que el portal tenga que
        # pagar una consulta de "Place Details" por cada candidato.
        "enlace_maps": f"https://www.google.com/maps/place/?q=place_id:{place_id}" if place_id else "",
        "origen": "fuera_de_red_google",
    }


def buscar_candidatos(
    especialidad: str, nombre_entidad: str, nombre_municipio: str | None
) -> tuple[list[dict], str]:
    """
    Establecimientos de Google Maps en esa zona, como candidatos a
    contratar. Devuelve (candidatos, consulta_usada). Lista vacía si no hay
    ninguno (no es un error).

    Lanza GoogleMapsNoConfigurado si falta la llave y ErrorGoogleMaps si el
    servicio no respondió -- los dos con mensaje listo para el usuario.
    """
    settings = get_settings()
    if not settings.google_maps_configurado:
        raise GoogleMapsNoConfigurado(
            "La búsqueda con Google Maps no está configurada todavía: falta la llave "
            "(GOOGLE_MAPS_API_KEY) en el archivo .env del servidor."
        )

    consulta = construir_consulta(especialidad, nombre_entidad, nombre_municipio)
    datos = _consultar(consulta, settings.google_maps_api_key.strip(), settings.google_maps_timeout_segundos)

    estado_resp = datos.get("status")
    if estado_resp == "ZERO_RESULTS":
        return [], consulta
    if estado_resp != "OK":
        # La llave viaja en la petición (nunca en lo que se registra aquí).
        logger.warning(
            "Google Maps devolvió status=%s en la consulta de candidatos (consulta: %s)",
            sanear_para_log(estado_resp), sanear_para_log(consulta),
        )
        raise ErrorGoogleMaps(_MENSAJES_ESTADO.get(estado_resp, _MENSAJE_GENERICO))

    resultados = datos.get("results") or []
    candidatos = [_a_candidato(r) for r in resultados if isinstance(r, dict)]
    return candidatos[: settings.google_maps_maximo_resultados], consulta


def _consultar(consulta: str, api_key: str, timeout: float) -> dict:
    params = {"query": consulta, "language": "es-419", "region": "mx", "key": api_key}
    try:
        respuesta = httpx.get(_BASE, params=params, timeout=timeout)
    except httpx.TimeoutException as e:
        raise ErrorGoogleMaps(
            "Google Maps tardó demasiado en responder. Vuelve a intentarlo en un momento."
        ) from e
    except httpx.HTTPError as e:
        raise ErrorGoogleMaps("No fue posible conectar con Google Maps.") from e

    if respuesta.status_code != 200:
        # La llave va en los parámetros de la petición, no en esta cadena.
        logger.warning(
            "Google Maps respondió HTTP %s en la consulta de candidatos (consulta: %s)",
            respuesta.status_code, sanear_para_log(consulta),
        )
        raise ErrorGoogleMaps("Google Maps respondió con un error. Intenta más tarde.")

    try:
        return respuesta.json()
    except ValueError as e:
        raise ErrorGoogleMaps("Google Maps devolvió una respuesta que no se pudo interpretar.") from e
