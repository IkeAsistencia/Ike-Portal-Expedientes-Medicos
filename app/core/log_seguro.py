"""
Saneado de valores antes de escribirlos en el log (CWE-117, Log Forging).

Un valor que viene de afuera (nombre de archivo, asunto, destinatario...)
puede traer saltos de línea. Si se interpola tal cual en un `logger.info`,
quien lo manda puede cerrar el renglón e inyectar renglones falsos que
parecen entradas legítimas del log -- con eso se puede tapar una huella o
inventar actividad que nunca pasó. Aquí los saltos y demás caracteres de
control se vuelven texto visible ("\\n", "\\r", "\\x07"), así el valor sigue
siendo legible pero nunca puede generar un renglón nuevo.
"""

_REEMPLAZOS = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}


def sanear_para_log(valor: object) -> str:
    texto = str(valor)
    salida = []
    for ch in texto:
        if ch in _REEMPLAZOS:
            salida.append(_REEMPLAZOS[ch])
        elif ch.isprintable():
            salida.append(ch)
        else:
            # Resto de caracteres de control (NUL, BEL, ESC y las secuencias
            # ANSI que algunas consolas interpretan) -- también a texto.
            salida.append(f"\\x{ord(ch):02x}")
    return "".join(salida)
