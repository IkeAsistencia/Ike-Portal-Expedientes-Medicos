"""
Pruebas del cálculo de semáforo (app/services/semaforo_service.py) --
puras, sin base de datos: se fija "ahora" con monkeypatch para que los
cálculos de horas/minutos sean deterministas.
"""
import datetime

from app.schemas.expediente import EstatusExpediente
from app.services import semaforo_service


AHORA = "2026-08-01 12:00:00"


def _fijar_ahora(monkeypatch):
    monkeypatch.setattr(semaforo_service, "ahora_local", lambda: AHORA)


def _apertura(horas_atras: float) -> datetime.datetime:
    ahora = datetime.datetime.strptime(AHORA, semaforo_service.FORMATO_FECHA_LOCAL)
    return ahora - datetime.timedelta(hours=horas_atras)


def test_grupo_primer_contacto_verde_amarillo_naranja_rojo(monkeypatch):
    _fijar_ahora(monkeypatch)
    # 377 Check Up es de primer contacto: amarillo=6h, naranja=12h, rojo=24h
    assert semaforo_service.calcular_color(377, EstatusExpediente.ABIERTO, _apertura(1), None) == semaforo_service.ColorSemaforo.VERDE
    assert semaforo_service.calcular_color(377, EstatusExpediente.ABIERTO, _apertura(7), None) == semaforo_service.ColorSemaforo.AMARILLO
    assert semaforo_service.calcular_color(377, EstatusExpediente.ABIERTO, _apertura(13), None) == semaforo_service.ColorSemaforo.NARANJA
    assert semaforo_service.calcular_color(377, EstatusExpediente.ABIERTO, _apertura(25), None) == semaforo_service.ColorSemaforo.ROJO


def test_grupo_segundo_contacto_usa_umbrales_mas_laxos(monkeypatch):
    _fijar_ahora(monkeypatch)
    # 383 Consulta Médica en Consultorio es de segundo contacto: amarillo=12h, naranja=48h, rojo=72h
    assert semaforo_service.calcular_color(383, EstatusExpediente.ABIERTO, _apertura(11), None) == semaforo_service.ColorSemaforo.VERDE
    assert semaforo_service.calcular_color(383, EstatusExpediente.ABIERTO, _apertura(13), None) == semaforo_service.ColorSemaforo.AMARILLO
    assert semaforo_service.calcular_color(383, EstatusExpediente.ABIERTO, _apertura(49), None) == semaforo_service.ColorSemaforo.NARANJA
    assert semaforo_service.calcular_color(383, EstatusExpediente.ABIERTO, _apertura(73), None) == semaforo_service.ColorSemaforo.ROJO


def test_despues_de_escalar_usa_minutos_desde_el_cambio_de_estatus(monkeypatch):
    _fijar_ahora(monkeypatch)
    hace_60_min = "2026-08-01 11:00:00"
    hace_150_min = "2026-08-01 09:30:00"
    hace_200_min = "2026-08-01 08:40:00"
    # El subservicio ya no importa en esta fase -- es el mismo umbral para todos.
    assert semaforo_service.calcular_color(377, EstatusExpediente.EN_ESPERA_RESPUESTA, _apertura(30), hace_60_min) == semaforo_service.ColorSemaforo.VERDE
    assert semaforo_service.calcular_color(383, EstatusExpediente.EN_ESPERA_RESPUESTA, _apertura(30), hace_150_min) == semaforo_service.ColorSemaforo.NARANJA
    assert semaforo_service.calcular_color(420, EstatusExpediente.EN_ESPERA_RESPUESTA, _apertura(30), hace_200_min) == semaforo_service.ColorSemaforo.ROJO


def test_una_vez_que_hay_respuesta_o_el_caso_avanzo_no_aplica_semaforo(monkeypatch):
    _fijar_ahora(monkeypatch)
    for estatus in (
        EstatusExpediente.SEGUIMIENTO_PROVEEDOR,
        EstatusExpediente.SEGUIMIENTO_CITA,
        EstatusExpediente.SEGUIMIENTO_COORDINADOR,
    ):
        assert semaforo_service.calcular_color(377, estatus, _apertura(100), "2026-08-01 08:00:00") is None


def test_subservicio_sin_grupo_clasificado_no_inventa_color(monkeypatch):
    _fijar_ahora(monkeypatch)
    assert semaforo_service.calcular_color(999, EstatusExpediente.ABIERTO, _apertura(100), None) is None


def test_formato_del_tiempo_transcurrido():
    f = semaforo_service._formato_duracion
    assert f(0) == "0 min"
    assert f(45) == "45 min"
    assert f(60) == "1 h"
    assert f(80) == "1 h 20 min"
    assert f(23 * 60 + 59) == "23 h 59 min"
    assert f(24 * 60) == "1 d"
    assert f(2 * 24 * 60 + 3 * 60 + 10) == "2 d 3 h"
    assert f(-5) == "0 min"


def test_tiempo_transcurrido_abierto_cuenta_desde_la_apertura(monkeypatch):
    _fijar_ahora(monkeypatch)
    texto = semaforo_service.tiempo_transcurrido(EstatusExpediente.ABIERTO, _apertura(13.5), None)
    assert texto == "13 h 30 min"


def test_tiempo_transcurrido_en_espera_cuenta_desde_el_cambio_de_estatus(monkeypatch):
    _fijar_ahora(monkeypatch)
    # Se mandó al proveedor hace 135 minutos (11:00 → 09:45 del mismo día)
    assert semaforo_service.tiempo_transcurrido(
        EstatusExpediente.EN_ESPERA_RESPUESTA, _apertura(100), "2026-08-01 09:45:00"
    ) == "2 h 15 min"
    # Sin fecha de cambio no se inventa un tiempo
    assert semaforo_service.tiempo_transcurrido(EstatusExpediente.EN_ESPERA_RESPUESTA, _apertura(100), None) is None


def test_tiempo_transcurrido_none_donde_no_aplica_semaforo(monkeypatch):
    _fijar_ahora(monkeypatch)
    for estatus in (EstatusExpediente.SEGUIMIENTO_PROVEEDOR, EstatusExpediente.SEGUIMIENTO_CITA):
        assert semaforo_service.tiempo_transcurrido(estatus, _apertura(30), None) is None
