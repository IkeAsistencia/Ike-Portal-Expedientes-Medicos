"""
Lectura de secretos desde AWS Secrets Manager (en vez de tenerlos escritos en
el `.env` del servidor de producción).

¿Por qué un módulo aparte y no leerlos en app/config.py? Porque `Settings()`
se construye una sola vez (get_settings está cacheado con lru_cache) y, al
importar app.main, el módulo app.graphql.schema YA llama a
get_arranque_settings(). Si el fetch a AWS viviera dentro de `Settings()`,
tendría que dispararse en el import -- y entonces cualquier cosa que solo
importe la app (pytest recolectando, un script) se iría a la red o
necesitaría credenciales de AWS. Por eso el fetch es un paso EXPLÍCITO que se
llama al arrancar (ver `cargar_en_entorno()` en app/main.py:lifespan), ANTES
de construir `Settings`, y lo único que hace es dejar los valores en
`os.environ` como si los hubiera puesto el `.env`. Así el resto del código no
cambia: sigue leyendo `settings.google_maps_api_key`, etc.

Orden de precedencia (de menor a mayor):
  1. Default del código (app/config.py).
  2. `.env` del proyecto.
  3. Variables de entorno reales del proceso (systemd, ECS, docker...).
  4. Secretos de Secrets Manager -- GANAN sobre todo lo anterior.

El punto 4 a propósito: si alguien dejó una llave vieja en el `.env` del
servidor, no puede "ganarle" al secreto administrado centralmente.

Modos (SECRETOS_AWS_MODO):
  "off"        -> no toca la red (default; lo que usan desarrollo y pruebas).
  "obligatorio"-> si no se puede leer el secreto, la app NO arranca. Es el
                  modo que debe usarse en producción: arrancar con secretos a
                  medias es peor que no arrancar, porque el portal se vería
                  "funcionando" con Google Maps apagado.
  "opcional"   -> si falla, sigue con lo que haya en el entorno. Útil la
                  primera vez que se configura, para no tumbar el servicio
                  mientras se dan los permisos de IAM.

Alcance: SOLO las llaves de Google Maps. Es lo único que el equipo de
infraestructura administra en `encryption-portal-medicos`; el resto de la
configuración sensible (JWT_SECRET_KEY, DB_PASSWORD, SMTP_*) sigue en el
`.env` del servidor.
"""

import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

MODO_OFF = "off"
MODO_OPCIONAL = "opcional"
MODO_OBLIGATORIO = "obligatorio"
MODOS_VALIDOS = (MODO_OFF, MODO_OPCIONAL, MODO_OBLIGATORIO)

# Variables que este módulo puede tomar del secreto: el nombre de la clave en
# el JSON de Secrets Manager es el nombre de la variable en MAYÚSCULAS, tal
# cual la lee pydantic-settings (no distingue mayúsculas/minúsculas).
#
# Solo las llaves de Google Maps: es lo único que el equipo de infraestructura
# administra en `encryption-portal-medicos`. El resto de la configuración
# sensible (JWT_SECRET_KEY, DB_PASSWORD, SMTP_*) sigue en el `.env` del
# servidor.
#
# Se listan explícitamente a propósito (lista blanca, no "mete todo lo que
# venga"): el secreto lo administra otra área, y si algún día le agregan una
# clave llamada `PATH` o `PYTHONPATH`, no queremos que reescriba el entorno
# del proceso.
VARIABLES_PERMITIDAS = frozenset({
    # Llave de Google Cloud para Places API. Solo la usa el servidor.
    "GOOGLE_MAPS_API_KEY",
    # Llave del navegador (viaja al frontend, restringida por dominio).
    "GOOGLE_MAPS_BROWSER_API_KEY",
    "GOOGLE_MAPS_MAP_ID",
})


class ErrorSecretosAws(Exception):
    """El secreto no se pudo leer y el modo es "obligatorio"."""


def _parsear_secreto(texto: str) -> dict[str, Any]:
    """
    El secreto puede venir como JSON (`{"GOOGLE_MAPS_API_KEY": "..."}`, el
    formato recomendado de Secrets Manager) o como texto plano (una sola
    llave suelta). En texto plano no hay nombre de variable, así que se
    necesita SECRETOS_AWS_CLAVE para saber a cuál corresponde -- si no viene,
    se ignora con un aviso, en vez de adivinar y poner la llave en el lugar
    equivocado.
    """
    texto = (texto or "").strip()
    if not texto:
        return {}
    if texto.startswith("{"):
        datos = json.loads(texto)
        if not isinstance(datos, dict):
            raise ValueError("el secreto es un JSON que no es un objeto")
        return datos
    return {"__texto_plano__": texto}


def _a_entorno(datos: dict[str, Any], clave_texto_plano: Optional[str]) -> dict[str, str]:
    """Filtra a la lista blanca y normaliza todo a str (Secrets Manager
    admite números y booleanos dentro del JSON)."""
    salida: dict[str, str] = {}
    for nombre, valor in datos.items():
        if nombre == "__texto_plano__":
            continue
        if nombre.upper() not in VARIABLES_PERMITIDAS:
            # No se imprime el valor, solo el nombre: el valor es el secreto.
            logger.warning(
                "Secreto de AWS: se ignora la clave '%s' (no está en la lista de "
                "variables que este portal acepta)", nombre,
            )
            continue
        if valor is None:
            continue
        salida[nombre.upper()] = str(valor)

    texto_plano = datos.get("__texto_plano__")
    if texto_plano:
        if clave_texto_plano:
            destino = clave_texto_plano.upper()
            if destino in VARIABLES_PERMITIDAS:
                salida[destino] = texto_plano
            else:
                logger.warning(
                    "Secreto de AWS: SECRETOS_AWS_CLAVE='%s' no está en la lista de "
                    "variables que este portal acepta; se ignora el secreto en texto plano.",
                    clave_texto_plano,
                )
        else:
            logger.warning(
                "Secreto de AWS: el secreto es texto plano y no hay SECRETOS_AWS_CLAVE "
                "que diga a qué variable corresponde; se ignora."
            )
    return salida


def _leer_de_aws(nombre: str, region: str) -> str:
    """
    Aísla la llamada a boto3 para que se pueda sustituir en las pruebas sin
    tener AWS ni credenciales. Import perezoso: boto3 solo se necesita en
    producción (o si alguien enciende los secretos a mano).

    Es el snippet que mandó el equipo de infraestructura, tal cual: misma
    sesión, mismo cliente, mismo `get_secret_value` y mismo `SecretString`.
    Lo único que se agrega es envolver el ClientError en ErrorSecretosAws
    para que el modo "obligatorio" pueda abortar el arranque.
    """
    import boto3
    from botocore.exceptions import ClientError

    session = boto3.session.Session()
    client = session.client(
        service_name="secretsmanager",
        region_name=region,
    )
    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=nombre,
        )
    except ClientError as e:
        # El mensaje de boto3 puede traer el nombre del recurso y el ARN, pero
        # nunca el valor del secreto -- es seguro registrarlo tal cual.
        raise ErrorSecretosAws(f"No se pudo leer el secreto '{nombre}' en {region}: {e}") from e

    return get_secret_value_response["SecretString"]


def cargar_en_entorno(modo: str, nombre: str, region: str, clave_texto_plano: Optional[str] = None) -> list[str]:
    """
    Trae el secreto y deja sus valores en `os.environ`.

    Devuelve la lista de nombres de variable que aplicó (sin valores). Se
    llama al arrancar la app, antes de construir Settings.

    Lanza ErrorSecretosAws si el modo es "obligatorio" y algo falla: en ese
    caso la app debe abortar el arranque.
    """
    modo = (modo or MODO_OFF).strip().lower()
    if modo == MODO_OFF:
        return []
    if modo not in MODOS_VALIDOS:
        raise ErrorSecretosAws(
            f"SECRETOS_AWS_MODO='{modo}' no es válido. Usa uno de: {', '.join(MODOS_VALIDOS)}."
        )

    obligatorio = modo == MODO_OBLIGATORIO
    try:
        contenido = _leer_de_aws(nombre, region)
        aplicadas = _a_entorno(_parsear_secreto(contenido), clave_texto_plano)
    except ErrorSecretosAws:
        if obligatorio:
            raise
        logger.warning("Secretos de AWS: no se pudo leer el secreto; se sigue con el entorno.")
        return []
    except Exception as e:  # noqa: BLE001 -- JSON inválido, binario corrupto, etc.
        mensaje = f"Secreto de AWS '{nombre}': no se pudo interpretar ({type(e).__name__})."
        if obligatorio:
            raise ErrorSecretosAws(mensaje) from e
        logger.warning(mensaje)
        return []

    if not aplicadas:
        mensaje = (
            f"Secreto de AWS '{nombre}': no trajo ninguna variable que este portal use. "
            f"Se esperaba alguna de: {', '.join(sorted(VARIABLES_PERMITIDAS))}."
        )
        if obligatorio:
            raise ErrorSecretosAws(mensaje)
        logger.warning(mensaje)
        return []

    for variable, valor in aplicadas.items():
        os.environ[variable] = valor

    # Solo los NOMBRES: el valor es el secreto.
    logger.info("Secretos de AWS: aplicadas %d variable(s): %s", len(aplicadas), ", ".join(sorted(aplicadas)))
    return sorted(aplicadas)
