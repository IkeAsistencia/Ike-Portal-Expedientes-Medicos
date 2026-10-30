"""
Pruebas de la lectura de secretos desde AWS Secrets Manager
(app/core/secretos_aws.py).

No se llama a AWS: `_leer_de_aws` se sustituye por una función que devuelve
el contenido que se quiera probar, así que las pruebas corren sin
credenciales ni red.

Lo que se cuida aquí:
- Que el secreto GANE sobre lo que ya hubiera en el entorno (una llave vieja
  en el .env del servidor no puede tener prioridad).
- Que la lista blanca se respete: el secreto lo administra otra área y no
  debe poder reescribir variables arbitrarias del proceso.
- Que en modo "obligatorio" un fallo impida arrancar (no arrancar a medias).
- Que nunca se registre en el log el VALOR de un secreto, solo su nombre.
"""

import json
import logging

import pytest

from app.core import secretos_aws as mod


@pytest.fixture(autouse=True)
def _sin_entorno_previo(monkeypatch):
    """Cada prueba arranca sin las variables que este módulo aplica, para que
    no se filtren entre pruebas."""
    for variable in mod.VARIABLES_PERMITIDAS:
        monkeypatch.delenv(variable, raising=False)
    yield


def _simular_secreto(monkeypatch, contenido):
    """Sustituye la llamada real a boto3 por el contenido dado."""
    monkeypatch.setattr(mod, "_leer_de_aws", lambda nombre, region: contenido)


def test_modo_off_no_toca_nada(monkeypatch):
    """Default: desarrollo y pruebas no deben intentar hablar con AWS."""
    def _explota(*_a, **_k):
        raise AssertionError("con modo off no debe llamarse a AWS")

    monkeypatch.setattr(mod, "_leer_de_aws", _explota)
    assert mod.cargar_en_entorno(mod.MODO_OFF, "secreto", "mx-central-1") == []


def test_aplica_las_llaves_del_json(monkeypatch):
    _simular_secreto(monkeypatch, json.dumps({
        "GOOGLE_MAPS_API_KEY": "llave-google",
        "JWT_SECRET_KEY": "llave-jwt",
    }))
    aplicadas = mod.cargar_en_entorno(mod.MODO_OBLIGATORIO, "encryption-portal-medicos", "mx-central-1")
    assert aplicadas == ["GOOGLE_MAPS_API_KEY", "JWT_SECRET_KEY"]
    import os
    assert os.environ["GOOGLE_MAPS_API_KEY"] == "llave-google"
    assert os.environ["JWT_SECRET_KEY"] == "llave-jwt"


def test_el_secreto_gana_sobre_el_entorno_existente(monkeypatch):
    """El punto del cambio: si alguien dejó una llave vieja en el .env del
    servidor, el secreto administrado centralmente debe tener prioridad."""
    import os
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "llave-vieja-del-env")
    _simular_secreto(monkeypatch, json.dumps({"GOOGLE_MAPS_API_KEY": "llave-del-secreto"}))
    mod.cargar_en_entorno(mod.MODO_OBLIGATORIO, "s", "mx-central-1")
    assert os.environ["GOOGLE_MAPS_API_KEY"] == "llave-del-secreto"


def test_ignora_claves_fuera_de_la_lista_blanca(monkeypatch, caplog):
    """El secreto lo administra otra área: no debe poder reescribir PATH ni
    nada que no esté permitido explícitamente."""
    import os
    monkeypatch.setenv("PATH", "/usr/bin")
    _simular_secreto(monkeypatch, json.dumps({"PATH": "/tmp/malicioso", "GOOGLE_MAPS_API_KEY": "ok"}))
    with caplog.at_level(logging.WARNING):
        aplicadas = mod.cargar_en_entorno(mod.MODO_OBLIGATORIO, "s", "mx-central-1")
    assert aplicadas == ["GOOGLE_MAPS_API_KEY"]
    assert os.environ["PATH"] == "/usr/bin"
    assert "PATH" in caplog.text


def test_normaliza_nombres_en_minusculas(monkeypatch):
    _simular_secreto(monkeypatch, json.dumps({"google_maps_browser_api_key": "llave-nav"}))
    aplicadas = mod.cargar_en_entorno(mod.MODO_OBLIGATORIO, "s", "mx-central-1")
    import os
    assert aplicadas == ["GOOGLE_MAPS_BROWSER_API_KEY"]
    assert os.environ["GOOGLE_MAPS_BROWSER_API_KEY"] == "llave-nav"


def test_texto_plano_con_clave_explicita(monkeypatch):
    """Un secreto guardado como una llave suelta, sin JSON."""
    _simular_secreto(monkeypatch, "AIzaSy-llave-suelta")
    aplicadas = mod.cargar_en_entorno(
        mod.MODO_OBLIGATORIO, "s", "mx-central-1", clave_texto_plano="GOOGLE_MAPS_API_KEY"
    )
    import os
    assert aplicadas == ["GOOGLE_MAPS_API_KEY"]
    assert os.environ["GOOGLE_MAPS_API_KEY"] == "AIzaSy-llave-suelta"


def test_texto_plano_sin_clave_no_adivina(monkeypatch, caplog):
    """Sin SECRETOS_AWS_CLAVE no se puede saber a qué variable corresponde:
    mejor ignorarlo que poner la llave en el lugar equivocado.

    Se usa "opcional" a propósito: en "obligatorio" un secreto que no aporta
    ninguna variable ya es un error por su cuenta (ver el caso siguiente), y
    aquí lo que se quiere comprobar es que NO se adivine el destino."""
    _simular_secreto(monkeypatch, "AIzaSy-llave-suelta")
    with caplog.at_level(logging.WARNING):
        aplicadas = mod.cargar_en_entorno(mod.MODO_OPCIONAL, "s", "mx-central-1")
    assert aplicadas == []
    assert "SECRETOS_AWS_CLAVE" in caplog.text
    import os
    assert "GOOGLE_MAPS_API_KEY" not in os.environ


def test_obligatorio_falla_si_no_hay_secreto(monkeypatch):
    def _falla(nombre, region):
        raise mod.ErrorSecretosAws("no autorizado")

    monkeypatch.setattr(mod, "_leer_de_aws", _falla)
    with pytest.raises(mod.ErrorSecretosAws):
        mod.cargar_en_entorno(mod.MODO_OBLIGATORIO, "s", "mx-central-1")


def test_opcional_sigue_adelante_si_falla(monkeypatch, caplog):
    def _falla(nombre, region):
        raise mod.ErrorSecretosAws("no autorizado")

    monkeypatch.setattr(mod, "_leer_de_aws", _falla)
    with caplog.at_level(logging.WARNING):
        assert mod.cargar_en_entorno(mod.MODO_OPCIONAL, "s", "mx-central-1") == []
    assert "no se pudo leer el secreto" in caplog.text


def test_obligatorio_falla_si_el_json_es_invalido(monkeypatch):
    _simular_secreto(monkeypatch, "{esto no es json")
    with pytest.raises(mod.ErrorSecretosAws):
        mod.cargar_en_entorno(mod.MODO_OBLIGATORIO, "s", "mx-central-1")


def test_obligatorio_falla_si_no_trae_variables_utiles(monkeypatch):
    """Un secreto vacío o con puras claves desconocidas dejaría la app
    arrancando sin lo que necesita: en obligatorio eso es un error."""
    _simular_secreto(monkeypatch, json.dumps({"OTRA_COSA": "x"}))
    with pytest.raises(mod.ErrorSecretosAws):
        mod.cargar_en_entorno(mod.MODO_OBLIGATORIO, "s", "mx-central-1")


def test_modo_invalido_es_error(monkeypatch):
    with pytest.raises(mod.ErrorSecretosAws, match="no es válido"):
        mod.cargar_en_entorno("activado", "s", "mx-central-1")


def test_nunca_registra_el_valor_del_secreto(monkeypatch, caplog):
    """El log es lo primero que se comparte al depurar: no puede llevar la llave."""
    secreto = "AIzaSyMUY-SECRETO-NO-DEBE-SALIR"
    _simular_secreto(monkeypatch, json.dumps({"GOOGLE_MAPS_API_KEY": secreto}))
    with caplog.at_level(logging.DEBUG):
        mod.cargar_en_entorno(mod.MODO_OBLIGATORIO, "s", "mx-central-1")
    assert secreto not in caplog.text
    assert "GOOGLE_MAPS_API_KEY" in caplog.text


def test_la_lista_blanca_no_incluye_variables_peligrosas():
    """Regresión: si alguien agrega PATH/PYTHONPATH a la lista, un secreto
    mal administrado podría secuestrar el proceso."""
    for peligrosa in ("PATH", "PYTHONPATH", "LD_PRELOAD", "HOME"):
        assert peligrosa not in mod.VARIABLES_PERMITIDAS
