"""
Cliente de OpenRouter (https://openrouter.ai) -- normaliza el acceso a
modelos de IA de varios proveedores bajo un solo API, con el mismo
contrato que el Chat Completions de OpenAI.

Cada llamada a `ejecutar_prompt` queda registrada en la bitácora local
(app/repositories/openrouter_repo.py) con los tokens y el costo que
OpenRouter regresa en el propio `usage` de la respuesta (ver
https://openrouter.ai/docs/use-cases/usage-accounting) -- no se calcula ni
se estima nada aquí, así el reporte de consumo (GET /openrouter/reporte)
queda respaldado por datos reales.

A propósito, NO hay "modo simulado" como en email_service.py: si no hay
OPENROUTER_API_KEY configurada, se rechaza la llamada de entrada (ver
OpenRouterNoConfigurado) en vez de inventar números de tokens/costo que
ensuciarían el reporte.
"""

import httpx

from app.config import get_settings
from app.repositories import openrouter_repo

TIMEOUT_SEGUNDOS = 60


class OpenRouterNoConfigurado(Exception):
    pass


class OpenRouterError(Exception):
    """La llamada a OpenRouter falló (HTTP de error, respuesta sin 'choices', etc.)."""


def _encabezados() -> dict:
    settings = get_settings()
    encabezados = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        # Recomendados por OpenRouter para su ranking -- opcionales, no
        # afectan el funcionamiento si se dejan vacíos.
        "X-Title": settings.openrouter_app_name,
    }
    if settings.openrouter_site_url:
        encabezados["HTTP-Referer"] = settings.openrouter_site_url
    return encabezados


def _llamar_chat_completions(payload: dict) -> dict:
    """
    Aislado en su propia función (sin lógica adicional) para poder
    sustituirla por un doble de prueba en los tests, sin tener que
    simular HTTP de verdad.
    """
    settings = get_settings()
    respuesta = httpx.post(
        f"{settings.openrouter_base_url}/chat/completions",
        headers=_encabezados(),
        json=payload,
        timeout=TIMEOUT_SEGUNDOS,
    )
    try:
        respuesta.raise_for_status()
    except httpx.HTTPStatusError as e:
        # El body de error de OpenRouter trae el motivo real (ej. modelo
        # inválido, saldo insuficiente) -- se incluye, pero nunca la API key
        # (va en el header de la petición, no en la respuesta).
        raise OpenRouterError(f"OpenRouter respondió {e.response.status_code}: {e.response.text[:500]}") from e
    return respuesta.json()


def ejecutar_prompt(
    mensaje: str,
    modelo: str | None = None,
    descripcion: str | None = None,
    identificador: str | None = None,
) -> dict:
    """
    Manda `mensaje` como un solo turno de usuario al modelo indicado (o al
    default de .env si no se especifica), registra el consumo real en la
    bitácora local y regresa el contenido generado junto con sus tokens/costo.
    """
    settings = get_settings()
    if not settings.openrouter_configurado:
        raise OpenRouterNoConfigurado(
            "OPENROUTER_API_KEY no está configurada en el .env -- ver .env.example."
        )

    modelo_usado = modelo or settings.openrouter_modelo_default
    payload = {
        "model": modelo_usado,
        "messages": [{"role": "user", "content": mensaje}],
    }

    datos = _llamar_chat_completions(payload)

    choices = datos.get("choices") or []
    if not choices:
        raise OpenRouterError(f"OpenRouter no regresó ninguna respuesta (choices vacío): {datos}")
    contenido = choices[0].get("message", {}).get("content", "")

    uso = datos.get("usage") or {}
    tokens_entrada = int(uso.get("prompt_tokens") or 0)
    tokens_salida = int(uso.get("completion_tokens") or 0)
    tokens_totales = int(uso.get("total_tokens") or (tokens_entrada + tokens_salida))
    # Modelos gratuitos ("...:free") no traen 'cost' -- 0 es el valor correcto, no un error.
    costo_usd = float(uso.get("cost") or 0.0)

    # El modelo real puede diferir del pedido (ej. si se usó "route":
    # "fallback" o el server regresa un alias) -- se guarda el que OpenRouter
    # confirmó, no el que se pidió, para que el reporte por modelo sea exacto.
    modelo_confirmado = datos.get("model") or modelo_usado

    openrouter_repo.registrar_iteracion(
        modelo=modelo_confirmado,
        tokens_entrada=tokens_entrada,
        tokens_salida=tokens_salida,
        tokens_totales=tokens_totales,
        costo_usd=costo_usd,
        descripcion=descripcion,
        identificador=identificador,
    )

    return {
        "contenido": contenido,
        "modelo": modelo_confirmado,
        "tokens_entrada": tokens_entrada,
        "tokens_salida": tokens_salida,
        "tokens_totales": tokens_totales,
        "costo_usd": costo_usd,
    }
