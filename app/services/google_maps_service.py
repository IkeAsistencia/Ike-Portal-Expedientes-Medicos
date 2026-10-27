"""
Búsqueda FUERA DE LA RED contra Google Maps (Places API) dentro de la
pantalla del Directorio de Proveedores.

Para qué: cuando el padrón no tiene nadie de la red para una especialidad y
una zona, esto ofrece establecimientos de esa zona como CANDIDATOS a
contratar -- no como proveedores del portal.

Google Maps indexa el giro real del negocio (buscar "cardiólogo" regresa
cardiólogos) y trae señales útiles para decidir a quién contactar primero
(calificación, si está abierto). A cambio: cada consulta tiene costo
(requiere una llave de Google Cloud con facturación activa) y los
resultados pueden traer el nombre del médico y reseñas de pacientes.

⚠️ Se usa **Places API (New)** (`places:searchText`), NO la versión legacy
(`maps/api/place/textsearch`). Comprobado contra la llave real del proyecto
el 2026-10-27: la legacy responde `REQUEST_DENIED` con
"LegacyApiNotActivatedMapError" porque Google ya no la habilita en proyectos
nuevos -- solo la (New). Si algún día se migra de vuelta, hay que habilitar
"Places API" (legacy) en Google Cloud Console.

Por qué Text Search y no Nearby Search: Nearby Search exige coordenadas
(lat/lng) del centro de búsqueda, que este portal no tiene por municipio;
Text Search acepta un texto libre ("cardiólogo en Mérida, Yucatán, México")
y es Google quien resuelve la zona, sin necesitar geocodificación aparte.

Por qué NO se trae el teléfono real de cada resultado: Google Places solo
regresa teléfono/sitio web con una llamada de "Place Details" POR CADA
lugar (una consulta adicional, con su propio costo, por cada candidato). Para
no multiplicar el gasto por el número de resultados, aquí se usa únicamente
lo que ya trae la búsqueda de texto (nombre, dirección, calificación, si
está abierto) y se entrega un enlace directo a la ficha de Google Maps del
lugar, desde donde el usuario puede ver el teléfono si lo necesita.

El `X-Goog-FieldMask` es obligatorio en la API nueva y además define el
costo: solo se piden los campos que la pantalla muestra (nada de fotos,
reseñas ni teléfonos), que es la SKU más barata de Text Search.

Nada de lo que regresa se guarda: cada búsqueda consulta en vivo. Un
resultado de aquí tampoco entra al padrón automáticamente: un candidato se
vuelve proveedor pasando por "Alta de médico", con su validación de cédula
y la aprobación de un Administrador -- Google solo dice que ahí hay un
lugar con ese giro, no que esté certificado ni que acepte las tarifas.

Documentación: https://developers.google.com/maps/documentation/places/web-service/text-search
"""

import logging

import httpx

from app.config import get_settings
from app.core.log_seguro import sanear_para_log

logger = logging.getLogger("google_maps_service")

_BASE = "https://places.googleapis.com/v1/places:searchText"

# Campos que se piden a la API nueva. Es obligatorio mandar el FieldMask y,
# además, define el precio: pedir menos campos = SKU más barata. Aquí solo
# van los que la pantalla pinta (ver _a_candidato y la tabla de
# frontend/js/directorio/vistas.js).
_FIELD_MASK = ",".join((
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.rating",
    "places.userRatingCount",
    "places.currentOpeningHours.openNow",
    "places.location",
))

# Mensaje legible por cada código de error de la API nueva. A diferencia de
# la legacy (que respondía 200 con un campo "status"), la nueva usa códigos
# HTTP + un cuerpo con "error.status" y "error.message".
_MENSAJES_ERROR = {
    "PERMISSION_DENIED": (
        "Google Maps rechazó la consulta: revisa que la llave (GOOGLE_MAPS_API_KEY) sea "
        "válida, que la \"Places API (New)\" esté habilitada y que la facturación del "
        "proyecto esté activa."
    ),
    "RESOURCE_EXHAUSTED": (
        "Se alcanzó el límite de consultas de Google Maps (cuota o presupuesto diario). "
        "Intenta más tarde o revisa el presupuesto del proyecto en Google Cloud."
    ),
    "INVALID_ARGUMENT": "La búsqueda no se pudo completar: faltó información para construirla.",
    "UNAUTHENTICATED": (
        "Google Maps no reconoció la llave (GOOGLE_MAPS_API_KEY). Revisa que esté bien "
        "copiada en el .env del servidor."
    ),
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
    Traduce los nombres de campo de la API NUEVA (displayName.text,
    formattedAddress, userRatingCount, currentOpeningHours.openNow,
    location.latitude/longitude) a los que ya usa la pantalla.

    Lo que NO se inventa: no hay cédula, costo de consulta, convenio ni
    teléfono -- se deja fuera en vez de rellenarlo con algo que después
    nadie podría distinguir de un dato real.
    """
    ubicacion = lugar.get("location") or {}
    apertura = lugar.get("currentOpeningHours") or {}
    place_id = (lugar.get("id") or "").strip()
    return {
        # Identificador de Google, NO una clave del portal, para que sea
        # imposible confundirlo con un proveedor ya dado de alta.
        "place_id": place_id,
        "nombre": ((lugar.get("displayName") or {}).get("text") or "").strip(),
        "direccion": (lugar.get("formattedAddress") or "").strip(),
        "calificacion": lugar.get("rating"),
        "total_calificaciones": lugar.get("userRatingCount"),
        "abierto_ahora": apertura.get("openNow"),
        "latitud": ubicacion.get("latitude"),
        "longitud": ubicacion.get("longitude"),
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

    # La API nueva NO devuelve "status": si no hay resultados responde 200
    # con el objeto vacío (sin la clave "places").
    resultados = datos.get("places") or []
    candidatos = [_a_candidato(r) for r in resultados if isinstance(r, dict)]
    return candidatos[: settings.google_maps_maximo_resultados], consulta


def _consultar(consulta: str, api_key: str, timeout: float) -> dict:
    cuerpo = {
        "textQuery": consulta,
        "languageCode": "es-419",
        "regionCode": "MX",
    }
    encabezados = {
        "Content-Type": "application/json",
        # La llave va en el encabezado (no en la URL): así no puede quedar
        # en un log de proxy ni en el historial de nadie.
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": _FIELD_MASK,
    }
    try:
        respuesta = httpx.post(_BASE, json=cuerpo, headers=encabezados, timeout=timeout)
    except httpx.TimeoutException as e:
        raise ErrorGoogleMaps(
            "Google Maps tardó demasiado en responder. Vuelve a intentarlo en un momento."
        ) from e
    except httpx.HTTPError as e:
        raise ErrorGoogleMaps("No fue posible conectar con Google Maps.") from e

    if respuesta.status_code != 200:
        # El cuerpo del error trae {"error": {"status": "...", "message": "..."}}.
        # Se registra el status (nunca la llave, que va en el encabezado).
        try:
            cuerpo_error = respuesta.json()
        except ValueError:
            cuerpo_error = None
        detalle = (cuerpo_error or {}).get("error") if isinstance(cuerpo_error, dict) else None
        detalle = detalle if isinstance(detalle, dict) else {}
        estado = detalle.get("status") or f"HTTP_{respuesta.status_code}"
        logger.warning(
            "Google Maps respondió %s (%s) en la consulta de candidatos (consulta: %s)",
            respuesta.status_code, sanear_para_log(estado), sanear_para_log(consulta),
        )
        raise ErrorGoogleMaps(_MENSAJES_ERROR.get(estado, _MENSAJE_GENERICO))

    try:
        return respuesta.json()
    except ValueError as e:
        raise ErrorGoogleMaps("Google Maps devolvió una respuesta que no se pudo interpretar.") from e
