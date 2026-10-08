"""
Job de validación de estatus del proveedor.

Reglas de negocio (según lo solicitado):
    Para expedientes con proveedor asignado que no han tenido
    respuesta / cambio de estatus:
      1. Si han pasado 8 horas  -> correo con los expedientes, fecha de
         apertura en color NARANJA.
      2. Si han pasado más de 24 horas -> correo con los expedientes,
         fecha de apertura en color ROJO.

    Interpretación aplicada (CONFIRMAR): "8 horas" se toma como el piso
    de la primera alerta (>=8h y <24h = naranja), y "más de 24 horas"
    como la segunda, más urgente (>=24h = rojo) — igual que el patrón de
    semáforo ya usado para las citas. Si la intención era otra (por
    ejemplo, alertar en naranja TODOS los que llevan 8h o más, sin
    importar si ya pasaron a rojo), avisar para ajustar el corte.

Este script NO corre solo ni se queda "vivo": está pensado para
ejecutarse periódicamente vía un programador externo (ver jobs/README.md
para configurarlo con el Programador de tareas de Windows). Cada
corrida:
  1. Consulta dbo.ST_CP_ObtenerExpedientesSinRespuestaProveedor.
  2. Separa los resultados en nivel "naranja" (8-24h) y "rojo" (24h+).
  3. Evita reenviar una alerta ya mandada para el mismo expediente y
     nivel (tabla local alertas_proveedor_enviadas) — si un expediente
     escala de naranja a rojo, sí se manda la alerta roja aunque ya se
     haya mandado la naranja antes.

Uso manual:
    python -m jobs.validar_estatus_proveedor
"""

import logging

from app.db.local_store import init_local_db
from app.repositories import alertas_proveedor_repo, expedientes_repo
from app.services import email_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("validar_estatus_proveedor")

UMBRAL_NARANJA_HORAS = 8
UMBRAL_ROJO_HORAS = 24


def _nivel_para(horas_sin_respuesta: int) -> str:
    if horas_sin_respuesta >= UMBRAL_ROJO_HORAS:
        return "rojo"
    return "naranja"  # ya viene filtrado desde >=8h por el SP


def ejecutar() -> None:
    init_local_db()
    logger.info("Consultando expedientes sin respuesta del proveedor (>= %sh)...", UMBRAL_NARANJA_HORAS)

    registros = expedientes_repo.listar_sin_respuesta_proveedor(UMBRAL_NARANJA_HORAS)
    logger.info("Encontrados %s expediente(s) con %sh o más sin respuesta.", len(registros), UMBRAL_NARANJA_HORAS)

    pendientes_por_nivel: dict[str, list[dict]] = {"naranja": [], "rojo": []}

    for row in registros:
        cl_expediente = row["Expediente"]
        horas = row["HorasSinRespuesta"]
        nivel = _nivel_para(horas)

        if alertas_proveedor_repo.ya_se_envio(cl_expediente, nivel):
            continue

        pendientes_por_nivel[nivel].append(
            {
                "expediente": cl_expediente,
                "cuenta": row.get("Cuenta"),
                "nombre_paciente": row.get("NombrePaciente"),
                "fecha_apertura": row.get("FechaApertura"),
                "horas_sin_respuesta": horas,
            }
        )

    for nivel, umbral in (("naranja", UMBRAL_NARANJA_HORAS), ("rojo", UMBRAL_ROJO_HORAS)):
        pendientes = pendientes_por_nivel[nivel]
        if not pendientes:
            logger.info("Nivel %s: nada nuevo que alertar.", nivel)
            continue

        logger.info("Nivel %s: enviando alerta para %s expediente(s).", nivel, len(pendientes))
        resultado = email_service.enviar_alerta_sin_respuesta(pendientes, color=nivel, umbral_horas=umbral)
        if resultado.simulado:
            logger.warning(
                "SMTP no configurado (.env): la alerta de nivel %s quedó solo registrada en el log, "
                "no se mandó un correo real.", nivel
            )

        for item in pendientes:
            alertas_proveedor_repo.marcar_enviada(item["expediente"], nivel)


if __name__ == "__main__":
    ejecutar()
