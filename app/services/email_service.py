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
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from app.config import get_settings

logger = logging.getLogger("email_service")

# Mismo logo que usa el login (frontend/img/logo-ike-lema.png), incrustado
# en el correo por Content-ID -- una ruta local (file://) no se vería en un
# correo real, así que hay que mandar la imagen junto con el mensaje.
_LOGO_PATH = Path(__file__).resolve().parent.parent.parent / "frontend" / "img" / "logo-ike-lema.png"
_LOGO_CID = "logo_ike_portal"


@dataclass
class ResultadoEnvio:
    enviados: int
    destinatarios: list[str] = field(default_factory=list)
    simulado: bool = True


def _adjuntar_logo(msg: MIMEMultipart) -> None:
    try:
        with open(_LOGO_PATH, "rb") as f:
            imagen = MIMEImage(f.read())
    except OSError:
        logger.warning("No se encontró el logo en %s; el correo se manda sin logo.", _LOGO_PATH)
        return
    imagen.add_header("Content-ID", f"<{_LOGO_CID}>")
    imagen.add_header("Content-Disposition", "inline", filename="logo-ike-lema.png")
    msg.attach(imagen)


def _enviar_smtp(destinatario: str, asunto: str, html: str) -> None:
    settings = get_settings()
    msg = MIMEMultipart("related")
    msg["Subject"] = asunto
    msg["From"] = settings.smtp_remitente
    msg["To"] = destinatario

    alterno = MIMEMultipart("alternative")
    alterno.attach(MIMEText("Tu cliente de correo no muestra HTML. Entra al portal para ver el detalle.", "plain"))
    alterno.attach(MIMEText(html, "html"))
    msg.attach(alterno)
    _adjuntar_logo(msg)

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

    cuerpo = MIMEMultipart("related")
    alterno = MIMEMultipart("alternative")
    alterno.attach(MIMEText("Tu cliente de correo no muestra HTML. Entra al portal para ver el detalle.", "plain"))
    alterno.attach(MIMEText(html, "html"))
    cuerpo.attach(alterno)
    _adjuntar_logo(cuerpo)
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


# Mismos colores que usa la tabla de Expedientes para cada estado (ver
# badgeEstatus en frontend/js/componentes/tabla-expedientes.js) -- para que
# el correo se vea igual que el portal, no un diseño aparte.
_COLORES_ESTADO = {
    "Abierto": ("#CA5010", "#FDE7D9"),
    "En Espera de Respuesta": ("#005E54", "#DCF4F1"),
    "Seguimiento Proveedor": ("#005A9E", "#DEECF9"),
    "Seguimiento de Cita": ("#5C2D91", "#EDE7F6"),
    "Finalizado": ("#107C10", "#DFF6DD"),
}


def _estado_para_correo(estatus: str) -> str:
    # Mandar este correo es justo lo que pasa el expediente a "En Espera de
    # Respuesta" (ver app/routers/expedientes.py: el cambio de estatus ocurre
    # DESPUÉS de armar el correo, así que todavía llega como "Abierto" aquí).
    # Para cuando el proveedor lo lea, eso ya es verdad -- mostrar "Abierto"
    # sería mostrarle un dato que ya quedó desactualizado en el momento en
    # que le llega el correo.
    if estatus == "Abierto":
        return "En Espera de Respuesta"
    return estatus


def _chip_estado(estatus: str) -> str:
    estatus = _estado_para_correo(estatus)
    color, fondo = _COLORES_ESTADO.get(estatus, _COLORES_ESTADO["Abierto"])
    return (
        f'<span style="display:inline-block;background:{fondo};color:{color};'
        f'font-size:12px;font-weight:700;padding:4px 12px;border-radius:999px;">'
        f"{html.escape(estatus)}</span>"
    )


_ENCABEZADO_CORREO = f"""
    <div style="padding:26px 36px 22px;text-align:left;">
      <img src="cid:{_LOGO_CID}" alt="IKE" style="height:34px;width:auto;display:block;">
    </div>
    <div style="height:4px;background:linear-gradient(90deg,#0078D4 0%,#005E54 100%);"></div>
"""

_PIE_CORREO = """
    <div style="border-top:1px solid #E3E8ED;padding:18px 36px;text-align:center;">
      <p style="margin:0;font-size:11.5px;color:#9AA4AE;">
        Correo automático del Portal Promédico — no respondas a este mensaje.<br>
        ¿Dudas? Contacta a Cabina Médica.
      </p>
    </div>
"""


def _fila_tarjeta(etiqueta: str, valor: str) -> str:
    return (
        f'<tr><td style="padding:8px 20px;font-size:12px;color:#6B7785;">{etiqueta}</td>'
        f'<td style="padding:8px 20px;font-size:14px;color:#0B2942;font-weight:600;text-align:right;">{valor}</td></tr>'
    )


def _html_un_expediente(e: dict, usuario_nombre: str, es_recordatorio: bool = False) -> str:
    filas = "".join([
        _fila_tarjeta("Expediente", f"<strong>{e['expediente']}</strong>"),
        _fila_tarjeta("Cuenta", html.escape(str(e.get("cuenta") or ""))),
        _fila_tarjeta("Paciente", html.escape(str(e.get("nombre_paciente") or "N/A"))),
        _fila_tarjeta("Servicio", html.escape(str(e.get("tipo_servicio") or ""))),
        _fila_tarjeta("Subservicio", html.escape(str(e.get("tipo_subservicio") or ""))),
        _fila_tarjeta("Fecha Apertura", html.escape(str(e.get("fecha_apertura_servicio") or ""))),
    ])
    titulo = "Recordatorio: sigues teniendo un expediente pendiente de respuesta" if es_recordatorio else "Tienes un expediente pendiente de atención"
    intro = (
        "Sigues teniendo un expediente pendiente de respuesta"
        if es_recordatorio
        else "Se te asignó un expediente para su seguimiento"
    )
    return f"""
    <div style="width:100%;background:#EEF1F4;padding:40px 16px;box-sizing:border-box;font-family:'Segoe UI',Arial,sans-serif;">
      <div style="max-width:580px;margin:0 auto;background:#FFFFFF;border-radius:10px;overflow:hidden;box-shadow:0 2px 10px rgba(11,41,66,0.12);">
        {_ENCABEZADO_CORREO}
        <div style="padding:32px 36px 28px;">
          <div style="font-size:11px;font-weight:700;letter-spacing:1.2px;color:#0078D4;text-transform:uppercase;margin-bottom:10px;">
            Portal Promédico
          </div>
          <h1 style="margin:0 0 14px;font-size:21px;line-height:1.3;color:#0B2942;">
            {titulo}
          </h1>
          <p style="margin:0 0 22px;font-size:14px;line-height:1.6;color:#3C4A58;">
            {intro} (enviado por {html.escape(usuario_nombre)}). Este es el resumen:
          </p>
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F6F8FA;border:1px solid #E3E8ED;border-radius:8px;">
            {filas}
            <tr><td style="padding:8px 20px 18px;font-size:12px;color:#6B7785;">Estado</td>
                <td style="padding:8px 20px 18px;text-align:right;">{_chip_estado(e.get("estatus") or "Abierto")}</td></tr>
          </table>
        </div>
        {_PIE_CORREO}
      </div>
    </div>
    """


def _html_varios_expedientes(expedientes: list[dict], usuario_nombre: str, es_recordatorio: bool = False) -> str:
    filas = "".join(
        f'<tr style="background:{"#DEECF9" if i % 2 else "transparent"};">'
        f'<td style="padding:9px 10px;color:#0B2942;font-weight:600;">{e["expediente"]}</td>'
        f'<td style="padding:9px 10px;color:#3C4A58;">{html.escape(str(e.get("cuenta") or ""))}</td>'
        f'<td style="padding:9px 10px;color:#3C4A58;">{html.escape(str(e.get("nombre_paciente") or "N/A"))}</td>'
        f'<td style="padding:9px 10px;color:#3C4A58;">{html.escape(str(e.get("tipo_servicio") or ""))}</td>'
        f'<td style="padding:9px 10px;color:#3C4A58;">{html.escape(str(e.get("tipo_subservicio") or ""))}</td>'
        f'<td style="padding:9px 10px;color:#3C4A58;">{html.escape(str(e.get("fecha_apertura_servicio") or ""))}</td>'
        f'<td style="padding:9px 10px;">{_chip_estado(e.get("estatus") or "Abierto")}</td>'
        f"</tr>"
        for i, e in enumerate(expedientes)
    )
    encabezados = "".join(
        f'<th style="text-align:left;padding:10px 10px;color:#0B2942;font-weight:700;border-bottom:2px solid #E3E8ED;">{col}</th>'
        for col in ("Expediente", "Cuenta", "Paciente", "Servicio", "Subservicio", "Fecha Apertura", "Estado")
    )
    cantidad = len(expedientes)
    titulo = (
        f"Recordatorio: sigues teniendo {cantidad} expedientes pendientes de respuesta"
        if es_recordatorio
        else f"Tienes {cantidad} expedientes pendientes de atención"
    )
    intro = "Sigues teniendo" if es_recordatorio else "Se te asignaron"
    return f"""
    <div style="width:100%;background:#EEF1F4;padding:40px 16px;box-sizing:border-box;font-family:'Segoe UI',Arial,sans-serif;">
      <div style="max-width:680px;margin:0 auto;background:#FFFFFF;border-radius:10px;overflow:hidden;box-shadow:0 2px 10px rgba(11,41,66,0.12);">
        {_ENCABEZADO_CORREO}
        <div style="padding:32px 36px 10px;">
          <div style="font-size:11px;font-weight:700;letter-spacing:1.2px;color:#0078D4;text-transform:uppercase;margin-bottom:10px;">
            Portal Promédico
          </div>
          <h1 style="margin:0 0 14px;font-size:21px;line-height:1.3;color:#0B2942;">
            {titulo}
          </h1>
          <p style="margin:0 0 20px;font-size:14px;line-height:1.6;color:#3C4A58;">
            {intro} los siguientes expedientes para su seguimiento (enviado por {html.escape(usuario_nombre)}):
          </p>
        </div>
        <div style="padding:0 36px 8px;overflow-x:auto;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:12.5px;min-width:620px;">
            <thead><tr style="background:#F3F2F1;">{encabezados}</tr></thead>
            <tbody>{filas}</tbody>
          </table>
        </div>
        <div style="padding:16px 36px 0;"></div>
        {_PIE_CORREO}
      </div>
    </div>
    """


def enviar_correo_proveedores(
    expedientes: list[dict], usuario_nombre: str, es_recordatorio: bool = False
) -> ResultadoEnvio:
    """
    Botón "Enviar correo a proveedores" (pantallas Expedientes y Expedientes
    PA). `expedientes` son los registros seleccionados (dicts con las mismas
    llaves que el schema Expediente). Un solo expediente usa la plantilla de
    tarjeta; varios, la de tabla -- mismo encabezado/pie en ambas.

    `es_recordatorio=True` cuando la selección ya estaba en "En Espera de
    Respuesta" (Cabina le está recordando al proveedor, no asignándole un
    caso nuevo) -- ver ESTATUS_PERMITIDOS_ENVIO_CORREO en estatus_service.py.
    Solo cambia el texto, nunca se mezcla con expedientes recién abiertos.
    """
    settings = get_settings()
    destinatario = settings.smtp_destinatario_prueba or settings.smtp_remitente or "proveedor@pendiente-confirmar.com"

    if len(expedientes) == 1:
        prefijo = "Recordatorio: expediente" if es_recordatorio else "Expediente"
        asunto = f"{prefijo} {expedientes[0]['expediente']} pendiente de atención"
        cuerpo_html = _html_un_expediente(expedientes[0], usuario_nombre, es_recordatorio=es_recordatorio)
    else:
        prefijo = "Recordatorio:" if es_recordatorio else ""
        asunto = f"{prefijo} {len(expedientes)} expedientes pendientes de atención".strip()
        cuerpo_html = _html_varios_expedientes(expedientes, usuario_nombre, es_recordatorio=es_recordatorio)

    enviado = _enviar_o_simular(destinatario, asunto, cuerpo_html)
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
    cl_expediente: int, cuenta: str, nombre_paciente: Optional[str], comentario: str, usuario_nombre: str,
    nuevo_estatus: str = "En Espera de Respuesta",
) -> ResultadoEnvio:
    """
    Aviso a Proveedor cuando Cabina regresa un expediente desde "Estado del
    Caso" -- ya sea para que lo corrija ("En Espera de Respuesta") o porque
    la cita fue aceptada y debe subir el comprobante de pago ("Seguimiento
    de Cita").
    """
    settings = get_settings()
    destinatario = settings.smtp_destinatario_prueba or settings.smtp_remitente or "proveedor@pendiente-confirmar.com"
    etiqueta_asunto, frase = MENSAJES_REGRESO_POR_ESTATUS.get(
        nuevo_estatus, MENSAJES_REGRESO_POR_ESTATUS["En Espera de Respuesta"]
    )
    # nombre_paciente puede venir None -- ver nota en app/schemas/expediente.py
    # (LEFT JOIN en dbo.ST_CP_ObtenerExpedientesSinProveedorMedico); html.escape(None)
    # truena, así que se cubre aquí también (no solo en quien llama a esta función).
    cuerpo_html = f"""
    <p>El expediente <b>{cl_expediente}</b> (cuenta: {html.escape(cuenta)}, paciente: {html.escape(nombre_paciente or "N/A")})
    {html.escape(frase.format(usuario=usuario_nombre))}.</p>
    <p><b>Comentario:</b></p>
    <p>{html.escape(comentario)}</p>
    """
    enviado = _enviar_o_simular(destinatario, f"Expediente {cl_expediente} {etiqueta_asunto}", cuerpo_html)
    return ResultadoEnvio(enviados=1, destinatarios=[destinatario], simulado=not enviado)


def _html_corte(
    cantidad: int, etiqueta: str, archivo_nombre: str, usuario_nombre: str, fecha_generado: Optional[str] = None
) -> str:
    filas = [
        _fila_tarjeta("Tipo", html.escape(etiqueta)),
        _fila_tarjeta("Cantidad de expedientes", f"<strong>{cantidad}</strong>"),
        _fila_tarjeta("Generado por", html.escape(usuario_nombre)),
    ]
    if fecha_generado:
        filas.append(_fila_tarjeta("Fecha", html.escape(fecha_generado)))
    filas.append(_fila_tarjeta("Archivo adjunto", html.escape(archivo_nombre)))
    return f"""
    <div style="width:100%;background:#EEF1F4;padding:40px 16px;box-sizing:border-box;font-family:'Segoe UI',Arial,sans-serif;">
      <div style="max-width:580px;margin:0 auto;background:#FFFFFF;border-radius:10px;overflow:hidden;box-shadow:0 2px 10px rgba(11,41,66,0.12);">
        {_ENCABEZADO_CORREO}
        <div style="padding:32px 36px 28px;">
          <div style="font-size:11px;font-weight:700;letter-spacing:1.2px;color:#0078D4;text-transform:uppercase;margin-bottom:10px;">
            Portal Promédico
          </div>
          <h1 style="margin:0 0 14px;font-size:21px;line-height:1.3;color:#0B2942;">
            Corte de {html.escape(etiqueta)}
          </h1>
          <p style="margin:0 0 22px;font-size:14px;line-height:1.6;color:#3C4A58;">
            Se generó un corte de <strong>{cantidad}</strong> expediente(s) de {html.escape(etiqueta)}.
            Se adjunta el detalle completo en Excel.
          </p>
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F6F8FA;border:1px solid #E3E8ED;border-radius:8px;">
            {"".join(filas)}
          </table>
          <p style="margin:18px 0 0;font-size:12.5px;line-height:1.6;color:#8A96A3;">
            Este correo es solo evidencia del corte ya enviado — no cambia el estado de ningún expediente.
          </p>
        </div>
        {_PIE_CORREO}
      </div>
    </div>
    """


def enviar_corte_proveedores(
    cantidad: int,
    tipo_expediente: str,
    archivo_nombre: str,
    archivo_bytes: bytes,
    usuario_nombre: str,
    fecha_generado: Optional[str] = None,
) -> ResultadoEnvio:
    """
    Botón "Generar corte" (pantallas Expedientes/Expedientes PA). A diferencia
    de enviar_correo_proveedores(), este correo NO cambia el estatus de nada --
    es un corte/evidencia de los expedientes ya enviados, con el Excel adjunto.
    """
    settings = get_settings()
    destinatario = settings.smtp_destinatario_prueba or settings.smtp_remitente or "proveedor@pendiente-confirmar.com"
    etiqueta = "Pago Anticipado" if tipo_expediente == "anticipado" else "Expedientes"
    asunto = f"Corte de {etiqueta} — {cantidad} expediente(s)"
    cuerpo_html = _html_corte(cantidad, etiqueta, archivo_nombre, usuario_nombre, fecha_generado)
    enviado = _enviar_o_simular_con_adjunto(destinatario, asunto, cuerpo_html, archivo_nombre, archivo_bytes)
    return ResultadoEnvio(enviados=cantidad, destinatarios=[destinatario], simulado=not enviado)


def enviar_alerta_sin_respuesta(expedientes: list[dict], color: str, umbral_horas: int) -> ResultadoEnvio:
    """
    Usado por el cron (jobs/validar_estatus_proveedor.py).
    `color`: "naranja" (>=8h) o "rojo" (>24h). Resalta la fecha de
    apertura de cada expediente con ese color, según lo solicitado.
    """
    settings = get_settings()
    destinatario = settings.smtp_destinatario_prueba or settings.smtp_remitente or "proveedor@pendiente-confirmar.com"
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
