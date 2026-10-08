"""
Pruebas de la integración con OpenRouter (app/services/openrouter_service.py,
app/repositories/openrouter_repo.py, app/routers/openrouter.py).

No se llama a OpenRouter real: se sustituye
openrouter_service._llamar_chat_completions por un doble de prueba, igual
que el resto de la suite sustituye call_procedure para SQL Server.

Ejecutar con:
    pytest tests/test_openrouter.py -v
"""
import pytest
from fastapi.testclient import TestClient

import app.repositories.accesos_repo as accesos_repo_module
import app.services.openrouter_service as openrouter_service_module
from app.main import app


def _respuesta_openrouter(modelo="openai/gpt-4o-mini", prompt_tokens=120, completion_tokens=30, cost=0.0042):
    """Forma de la respuesta real de /chat/completions (ver
    https://openrouter.ai/docs/use-cases/usage-accounting)."""
    return {
        "id": "gen-fake-123",
        "model": modelo,
        "choices": [{"message": {"role": "assistant", "content": "Respuesta simulada de OpenRouter."}}],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "cost": cost,
        },
    }


@pytest.fixture(autouse=True)
def _patch_arranque(monkeypatch):
    # calentar_pool() del lifespan intenta una conexión real a SQL Server --
    # esta suite no la necesita (OpenRouter y la bitácora local no tocan
    # SQL Server para nada).
    import app.main as main_module

    monkeypatch.setattr(main_module, "calentar_pool", lambda: None)

    from app.core.rate_limit import limpiar_todo

    limpiar_todo()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_AUTH_MODE", "sql")
    monkeypatch.setenv("DB_SERVER", "servidor-fake")
    monkeypatch.setenv("DB_NAME", "bd-fake")
    monkeypatch.setenv("DB_USER", "usuario-fake")
    monkeypatch.setenv("DB_PASSWORD", "password-fake")
    monkeypatch.setenv("LOCAL_DB_PATH", str(tmp_path / "test_local.db"))
    monkeypatch.setenv("JWT_SECRET_KEY", "clave-de-prueba")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-fake-key")

    from app.config import get_settings

    get_settings.cache_clear()

    with TestClient(app) as c:
        yield c


def _headers_admin(client):
    accesos_repo_module.alta_acceso("RFCADMOR", "Admin OpenRouter", accesos_repo_module.PERFIL_ADMINISTRADOR)
    accesos_repo_module.crear_password("RFCADMOR", "Admin2024xx")
    r = client.post("/auth/rfc/login", json={"rfc": "RFCADMOR", "password": "Admin2024xx"})
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _headers_proveedor(client):
    accesos_repo_module.alta_acceso("RFCPROVOR", "Proveedor OpenRouter", accesos_repo_module.PERFIL_PROVEEDOR, "Ciudad de México")
    accesos_repo_module.crear_password("RFCPROVOR", "Proveedor2024")
    r = client.post("/auth/rfc/login", json={"rfc": "RFCPROVOR", "password": "Proveedor2024"})
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_sin_sesion_rechaza(client):
    r = client.post("/openrouter", json={"mensaje": "hola"})
    assert r.status_code == 401


def test_perfil_proveedor_no_puede_usar_openrouter(client):
    headers = _headers_proveedor(client)
    r = client.post("/openrouter", json={"mensaje": "hola"}, headers=headers)
    assert r.status_code == 403


def test_sin_api_key_configurada_da_400(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    get_settings.cache_clear()
    headers = _headers_admin(client)
    r = client.post("/openrouter", json={"mensaje": "hola"}, headers=headers)
    assert r.status_code == 400
    assert "OPENROUTER_API_KEY" in r.json()["detail"]
    get_settings.cache_clear()


def test_ejecutar_prompt_registra_consumo_real(client, monkeypatch):
    monkeypatch.setattr(
        openrouter_service_module,
        "_llamar_chat_completions",
        lambda payload: _respuesta_openrouter(),
    )
    headers = _headers_admin(client)
    r = client.post(
        "/openrouter",
        json={"mensaje": "Resume este expediente", "descripcion": "prueba unitaria"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["modelo"] == "openai/gpt-4o-mini"
    assert data["tokens_entrada"] == 120
    assert data["tokens_salida"] == 30
    assert data["tokens_totales"] == 150
    assert data["costo_usd"] == pytest.approx(0.0042)

    r = client.get("/openrouter/iteraciones", headers=headers)
    assert r.status_code == 200
    iteraciones = r.json()
    assert len(iteraciones) == 1
    assert iteraciones[0]["descripcion"] == "prueba unitaria"
    assert iteraciones[0]["identificador"] == "RFCADMOR"


def test_modelo_gratuito_sin_cost_registra_cero(client, monkeypatch):
    respuesta = _respuesta_openrouter(modelo="meta-llama/llama-3.1-8b-instruct:free", cost=None)
    del respuesta["usage"]["cost"]
    monkeypatch.setattr(openrouter_service_module, "_llamar_chat_completions", lambda payload: respuesta)
    headers = _headers_admin(client)
    r = client.post("/openrouter", json={"mensaje": "hola"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["costo_usd"] == 0.0


def test_error_openrouter_se_traduce_a_502(client, monkeypatch):
    def _lanzar(payload):
        raise openrouter_service_module.OpenRouterError("OpenRouter respondió 402: saldo insuficiente")

    monkeypatch.setattr(openrouter_service_module, "_llamar_chat_completions", _lanzar)
    headers = _headers_admin(client)
    r = client.post("/openrouter", json={"mensaje": "hola"}, headers=headers)
    assert r.status_code == 502


def test_reporte_agrega_por_modelo_y_dia(client, monkeypatch):
    llamadas = [
        _respuesta_openrouter(modelo="openai/gpt-4o-mini", prompt_tokens=100, completion_tokens=20, cost=0.01),
        _respuesta_openrouter(modelo="openai/gpt-4o-mini", prompt_tokens=200, completion_tokens=40, cost=0.02),
        _respuesta_openrouter(modelo="anthropic/claude-3.5-haiku", prompt_tokens=50, completion_tokens=10, cost=0.05),
    ]
    respuestas = iter(llamadas)
    monkeypatch.setattr(openrouter_service_module, "_llamar_chat_completions", lambda payload: next(respuestas))

    headers = _headers_admin(client)
    for _ in llamadas:
        r = client.post("/openrouter", json={"mensaje": "hola"}, headers=headers)
        assert r.status_code == 200

    r = client.get("/openrouter/reporte", headers=headers)
    assert r.status_code == 200
    reporte = r.json()

    assert reporte["total_peticiones"] == 3
    assert reporte["tokens_entrada"] == 350
    assert reporte["tokens_salida"] == 70
    assert reporte["tokens_totales"] == 420
    assert reporte["costo_total_usd"] == pytest.approx(0.08)
    assert reporte["costo_promedio_usd"] == pytest.approx(0.08 / 3)

    por_modelo = {m["modelo"]: m for m in reporte["por_modelo"]}
    assert por_modelo["openai/gpt-4o-mini"]["peticiones"] == 2
    assert por_modelo["openai/gpt-4o-mini"]["tokens_totales"] == 360
    assert por_modelo["openai/gpt-4o-mini"]["costo_usd"] == pytest.approx(0.03)
    assert por_modelo["anthropic/claude-3.5-haiku"]["peticiones"] == 1
    assert por_modelo["anthropic/claude-3.5-haiku"]["costo_usd"] == pytest.approx(0.05)

    # La más costosa es la de claude (0.05), aunque no sea la de más tokens.
    assert reporte["mayor_costo"][0]["modelo"] == "anthropic/claude-3.5-haiku"
    # La de mayor consumo de tokens es la segunda llamada de gpt-4o-mini (240 tokens).
    assert reporte["mayor_consumo_tokens"][0]["tokens_totales"] == 240

    assert len(reporte["por_dia"]) == 1
    assert reporte["por_dia"][0]["peticiones"] == 3


def test_reporte_filtra_por_rango_de_fechas(client, monkeypatch):
    import app.repositories.openrouter_repo as openrouter_repo_module

    # Una iteración "vieja" insertada directo en la bitácora, fuera del
    # rango que se va a consultar.
    with openrouter_repo_module.get_local_connection() as conn:
        conn.execute(
            "INSERT INTO openrouter_iteraciones (modelo, tokens_entrada, tokens_salida, tokens_totales, costo_usd, fecha) "
            "VALUES ('openai/gpt-4o-mini', 10, 5, 15, 0.001, '2020-01-01 10:00:00')"
        )
        conn.commit()

    monkeypatch.setattr(
        openrouter_service_module, "_llamar_chat_completions", lambda payload: _respuesta_openrouter()
    )
    headers = _headers_admin(client)
    r = client.post("/openrouter", json={"mensaje": "hola"}, headers=headers)
    assert r.status_code == 200

    r = client.get("/openrouter/reporte", params={"desde": "2024-01-01"}, headers=headers)
    assert r.status_code == 200
    reporte = r.json()
    assert reporte["total_peticiones"] == 1  # la de 2020 queda fuera

    r = client.get("/openrouter/reporte", headers=headers)
    assert r.json()["total_peticiones"] == 2  # sin filtro, incluye ambas
