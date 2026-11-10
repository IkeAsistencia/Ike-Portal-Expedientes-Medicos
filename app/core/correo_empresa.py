"""
Candado de dominio: los correos a los que el portal manda -- el correo de
cada Proveedor (Usuarios y Accesos / carga por Excel) y el destinatario del
corte -- solo pueden ser de la empresa.

Se revisa al capturar (con el aviso de MENSAJE_DOMINIO_NO_PERMITIDO) y otra
vez al enviar a proveedores, para que un correo guardado antes de esta regla
tampoco reciba nada.
"""

DOMINIO_EMPRESA = "ikeasistencia.com"
MENSAJE_DOMINIO_NO_PERMITIDO = f"El correo que acabas de ingresar no pertenece al dominio de @{DOMINIO_EMPRESA}."


def es_correo_de_empresa(correo: str | None) -> bool:
    # Dominio exacto: "x@ikeasistencia.com.mx" o "x@otroikeasistencia.com" no pasan.
    partes = (correo or "").strip().lower().split("@")
    return len(partes) == 2 and bool(partes[0]) and partes[1] == DOMINIO_EMPRESA
