"""
Envío de correo. Mientras no tengamos los datos reales de SMTP (ver
config.py: SMTP_HOST, SMTP_USER, SMTP_PASSWORD, SMTP_REMITENTE) y la
fuente del correo de cada proveedor, este módulo trabaja en "modo
simulado": registra en el log qué se habría enviado, en vez de mandarlo
de verdad. En cuanto se tengan esos datos, basta con llenar el .env —
no hay que tocar el código para activar el envío real.

⚠️ PENDIENTE DE CONFIRMAR: ¿de dónde sale el correo del proveedor al que
hay que escribirle? El query de Expedientes solo trae el correo del
USUARIO/paciente (E.Email), no el del proveedor asignado. Mientras se
confirma, ambas funciones de este módulo mandan el correo al remitente
configurado (SMTP_REMITENTE) como marcador de posición, para que el
flujo completo (validar selección -> armar plantilla -> "enviar") se
pueda probar de punta a punta.
"""

import html
import logging
import smtplib
from dataclasses import dataclass, field
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import get_settings

logger = logging.getLogger("email_service")


@dataclass
class ResultadoEnvio:
    enviados: int
    destinatarios: list[str] = field(default_factory=list)
    simulado: bool = True


def _enviar_smtp(destinatario: str, asunto: str, html: str) -> None:
    settings = get_settings()
    msg = MIMEMultipart("alternative")
    msg["Subject"] = asunto
    msg["From"] = settings.smtp_remitente
    msg["To"] = destinatario
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        if settings.smtp_usar_tls:
            server.starttls()
        if settings.smtp_user and settings.smtp_password:
            server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(settings.smtp_remitente, [destinatario], msg.as_string())


def _enviar_o_simular(destinatario: str, asunto: str, html: str) -> bool:
    settings = get_settings()
    if not settings.smtp_configurado:
        logger.info(
            "[MODO SIMULADO — falta configurar SMTP_HOST/SMTP_REMITENTE en .env] "
            "Para: %s | Asunto: %s\n%s",
            destinatario, asunto, html,
        )
        return False
    _enviar_smtp(destinatario, asunto, html)
    return True


def _enviar_smtp_con_adjunto(
    destinatario: str, asunto: str, html: str, adjunto_nombre: str, adjunto_bytes: bytes
) -> None:
    settings = get_settings()
    msg = MIMEMultipart("mixed")
    msg["Subject"] = asunto
    msg["From"] = settings.smtp_remitente
    msg["To"] = destinatario

    cuerpo = MIMEMultipart("alternative")
    cuerpo.attach(MIMEText(html, "html"))
    msg.attach(cuerpo)

    adjunto = MIMEApplication(
        adjunto_bytes, _subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    adjunto.add_header("Content-Disposition", "attachment", filename=adjunto_nombre)
    msg.attach(adjunto)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        if settings.smtp_usar_tls:
            server.starttls()
        if settings.smtp_user and settings.smtp_password:
            server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(settings.smtp_remitente, [destinatario], msg.as_string())


def _enviar_o_simular_con_adjunto(
    destinatario: str, asunto: str, html: str, adjunto_nombre: str, adjunto_bytes: bytes
) -> bool:
    settings = get_settings()
    if not settings.smtp_configurado:
        logger.info(
            "[MODO SIMULADO — falta configurar SMTP_HOST/SMTP_REMITENTE en .env] "
            "Para: %s | Asunto: %s | Adjunto: %s (%d bytes)\n%s",
            destinatario, asunto, adjunto_nombre, len(adjunto_bytes), html,
        )
        return False
    _enviar_smtp_con_adjunto(destinatario, asunto, html, adjunto_nombre, adjunto_bytes)
    return True


def enviar_correo_proveedores(expedientes: list[dict], usuario_nombre: str) -> ResultadoEnvio:
    """
    Botón "Enviar correo a proveedores" (pantalla Expedientes).
    `expedientes` es la lista de registros seleccionados (dicts con al
    menos: expediente, cuenta, nombre_paciente).
    """
    settings = get_settings()
    destinatario = settings.smtp_remitente or "proveedor@pendiente-confirmar.com"

    filas = "".join(
        f"<tr><td>{e['expediente']}</td><td>{html.escape(str(e.get('cuenta','')))}</td>"
        f"<td>{html.escape(str(e.get('nombre_paciente','')))}</td></tr>"
        for e in expedientes
    )
    cuerpo_html = f"""
    <p>Se solicita atención a los siguientes expedientes (enviado por {html.escape(usuario_nombre)}):</p>
    <table border="1" cellpadding="6" cellspacing="0">
      <tr><th>Expediente</th><th>Cuenta</th><th>Paciente</th></tr>
      {filas}
    </table>
    """
    enviado = _enviar_o_simular(destinatario, "Expedientes pendientes de atención", cuerpo_html)
    return ResultadoEnvio(enviados=len(expedientes), destinatarios=[destinatario], simulado=not enviado)


MENSAJES_REGRESO_POR_ESTATUS = {
    # (asunto, frase de qué pasó) según a qué estatus Cabina regresó el expediente.
    "En Espera de Respuesta": (
        "regresado para corrección",
        "fue regresado por {usuario} y requiere que lo corrijas",
    ),
    "Seguimiento de Cita": (
        "cita aceptada — sube tu comprobante de pago",
        "fue regresado por {usuario}: la cita fue aceptada, ya puedes subir el comprobante de pago",
    ),
}


def enviar_notificacion_regreso(
    cl_expediente: int, cuenta: str, nombre_paciente: str, comentario: str, usuario_nombre: str,
    nuevo_estatus: str = "En Espera de Respuesta",
) -> ResultadoEnvio:
    """
    Aviso a Proveedor cuando Cabina regresa un expediente desde "Estado del
    Caso" -- ya sea para que lo corrija ("En Espera de Respuesta") o porque
    la cita fue aceptada y debe subir el comprobante de pago ("Seguimiento
    de Cita").
    """
    settings = get_settings()
    destinatario = settings.smtp_remitente or "proveedor@pendiente-confirmar.com"
    etiqueta_asunto, frase = MENSAJES_REGRESO_POR_ESTATUS.get(
        nuevo_estatus, MENSAJES_REGRESO_POR_ESTATUS["En Espera de Respuesta"]
    )
    cuerpo_html = f"""
    <p>El expediente <b>{cl_expediente}</b> (cuenta: {html.escape(cuenta)}, paciente: {html.escape(nombre_paciente)})
    {html.escape(frase.format(usuario=usuario_nombre))}.</p>
    <p><b>Comentario:</b></p>
    <p>{html.escape(comentario)}</p>
    """
    enviado = _enviar_o_simular(destinatario, f"Expediente {cl_expediente} {etiqueta_asunto}", cuerpo_html)
    return ResultadoEnvio(enviados=1, destinatarios=[destinatario], simulado=not enviado)


def enviar_corte_proveedores(
    cantidad: int, tipo_expediente: str, archivo_nombre: str, archivo_bytes: bytes, usuario_nombre: str
) -> ResultadoEnvio:
    """
    Botón "Generar corte" (pantallas Expedientes/Expedientes PA). A diferencia
    de enviar_correo_proveedores(), este correo NO cambia el estatus de nada --
    es un corte/evidencia de los expedientes ya enviados, con el Excel adjunto.
    """
    settings = get_settings()
    destinatario = settings.smtp_remitente or "proveedor@pendiente-confirmar.com"
    etiqueta = "Pago Anticipado" if tipo_expediente == "anticipado" else "Expedientes"
    asunto = f"Corte de {etiqueta} — {cantidad} expediente(s)"
    cuerpo_html = f"""
    <p>Corte de {cantidad} expediente(s) de {etiqueta}, generado por {html.escape(usuario_nombre)}.</p>
    <p>Se adjunta el detalle en Excel.</p>
    """
    enviado = _enviar_o_simular_con_adjunto(destinatario, asunto, cuerpo_html, archivo_nombre, archivo_bytes)
    return ResultadoEnvio(enviados=cantidad, destinatarios=[destinatario], simulado=not enviado)


def enviar_alerta_sin_respuesta(expedientes: list[dict], color: str, umbral_horas: int) -> ResultadoEnvio:
    """
    Usado por el cron (jobs/validar_estatus_proveedor.py).
    `color`: "naranja" (>=8h) o "rojo" (>24h). Resalta la fecha de
    apertura de cada expediente con ese color, según lo solicitado.
    """
    settings = get_settings()
    destinatario = settings.smtp_remitente or "proveedor@pendiente-confirmar.com"
    color_css = "#CA5010" if color == "naranja" else "#D13438"

    filas = "".join(
        f"<tr><td>{e['expediente']}</td><td>{html.escape(str(e.get('cuenta','')))}</td>"
        f"<td>{html.escape(str(e.get('nombre_paciente','')))}</td>"
        f"<td style='color:{color_css};font-weight:bold;'>{e['fecha_apertura']}</td>"
        f"<td>{e['horas_sin_respuesta']}</td></tr>"
        for e in expedientes
    )
    cuerpo_html = f"""
    <p>Los siguientes expedientes llevan más de {umbral_horas} horas sin respuesta del proveedor:</p>
    <table border="1" cellpadding="6" cellspacing="0">
      <tr><th>Expediente</th><th>Cuenta</th><th>Paciente</th>
          <th>Fecha de apertura</th><th>Horas sin respuesta</th></tr>
      {filas}
    </table>
    """
    asunto = f"[{'URGENTE' if color == 'rojo' else 'Alerta'}] Expedientes sin respuesta del proveedor"
    enviado = _enviar_o_simular(destinatario, asunto, cuerpo_html)
    return ResultadoEnvio(enviados=len(expedientes), destinatarios=[destinatario], simulado=not enviado)
