"""
Carga del padrón de proveedores del Directorio de Proveedores (pantalla
"Carga catálogo proveedores", exclusiva de Administrador) desde un Excel --
la configuración y los datos de este padrón viven SOLO en este portal
(SQLite local), nunca en SQL Server. El archivo se solicita al área
correspondiente con el layout exacto que arma `generar_plantilla_excel()`.

Layout vigente (2026-10-19):
  - La CLAVE DEL PROVEEDOR dejó de ser obligatoria: ahora el portal genera
    su propia clave (PRV-000001, ver proveedores_repo) y es esa la que
    amarra las citas. La del sistema central se conserva como referencia.
  - El domicilio va DESGLOSADO y etiquetado como el lugar donde el médico
    DA LA CONSULTA: calle con números exterior/interior, colonia y CP.
"""

from io import BytesIO

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

COLOR_NAVY = "0B2942"
COLOR_WHITE = "FFFFFF"

# (encabezado en el Excel, llave interna, ancho de columna, obligatorio).
# Obligatorio solo el nombre: sin él no hay a quién registrar. La cédula no
# se exige, pero conviene mandarla -- es con lo que se reconoce al mismo
# médico entre una carga y otra (ver proveedores_repo.llaves_candidatas);
# sin ella, el reconocimiento se hace por nombre + especialidad.
COLUMNAS = [
    ("Nombre completo", "nombre", 30, True),
    ("Especialidad", "especialidad", 22, False),
    ("Cédula profesional", "cedula", 18, False),
    ("RFC", "rfc", 16, False),
    ("Estado", "estado", 18, False),
    ("Municipio", "municipio", 20, False),
    ("Domicilio de consulta: Calle, No. Ext., No. Int.", "calle_num_ext_int", 38, False),
    ("Domicilio de consulta: Colonia", "colonia", 24, False),
    ("Domicilio de consulta: Código Postal", "codigo_postal", 20, False),
    ("Nombre del consultorio/clínica", "consultorio", 26, False),
    ("Teléfono", "telefono", 16, False),
    ("Correo electrónico", "email", 28, False),
    ("Horario de atención", "horario", 24, False),
    ("Costo de consulta", "costo_consulta", 18, False),
    ("Convenio (aseguradora)", "convenio", 22, False),
    ("Teleconsulta (Sí/No)", "teleconsulta", 18, False),
    ("Latitud", "latitud", 14, False),
    ("Longitud", "longitud", 14, False),
    ("Clave del proveedor (referencia, opcional)", "cl_proveedor", 34, False),
]

FILA_ENCABEZADO = 1

_FILA_EJEMPLO = {
    "nombre": "Dra. Laura Méndez Ruiz", "especialidad": "Cardiología",
    "cedula": "8453219", "rfc": "MERL850214H23", "estado": "Jalisco", "municipio": "Guadalajara",
    "calle_num_ext_int": "Av. Vallarta 1450, Int. 302", "colonia": "Americana",
    "codigo_postal": "44100", "consultorio": "Consultorio 302",
    "telefono": "33 1234 5678", "email": "consultorio@correo.mx", "horario": "Lun-Vie 09:00-14:00",
    "costo_consulta": "800", "convenio": "GNP", "teleconsulta": "No",
    "latitud": 20.6736, "longitud": -103.344, "cl_proveedor": 10234,
}


def generar_plantilla_excel() -> bytes:
    """Layout a solicitar al área que entrega la data -- un encabezado por
    columna (los obligatorios marcados con "*") y un renglón de ejemplo
    para que quede claro el formato esperado de cada campo."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Padrón de Proveedores"

    for col_idx, (encabezado, _clave, ancho, obligatorio) in enumerate(COLUMNAS, start=1):
        texto = encabezado + (" *" if obligatorio else "")
        celda = ws.cell(row=FILA_ENCABEZADO, column=col_idx, value=texto)
        celda.font = Font(bold=True, color=COLOR_WHITE)
        celda.fill = PatternFill("solid", fgColor=COLOR_NAVY)
        celda.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(col_idx)].width = ancho
    ws.row_dimensions[FILA_ENCABEZADO].height = 44
    ws.freeze_panes = f"A{FILA_ENCABEZADO + 1}"

    for col_idx, (_encabezado, clave, _ancho, _obligatorio) in enumerate(COLUMNAS, start=1):
        ws.cell(row=FILA_ENCABEZADO + 1, column=col_idx, value=_FILA_EJEMPLO.get(clave))

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


class ErrorCatalogoExcel(Exception):
    """El archivo subido no tiene el formato esperado -- encabezado
    faltante/renombrado, dato obligatorio vacío o de tipo inválido. El
    mensaje ya viene listo para mostrarse tal cual al usuario."""


def _encabezados_de_la_fila(fila: tuple) -> list[str]:
    encabezados = [str(c).strip() if c is not None else "" for c in fila]
    # La plantilla marca los obligatorios con " *" -- se compara sin ese
    # sufijo, por si alguien lo deja o lo borra al llenar el archivo.
    return [e[:-2].strip() if e.endswith(" *") else e for e in encabezados]


def leer_catalogo_excel(contenido: bytes) -> list[dict]:
    """Valida y convierte el Excel subido en una lista de dicts (una por
    proveedor), listos para `proveedores_repo.cargar_padron`. Lanza
    ErrorCatalogoExcel con un mensaje accionable ante cualquier problema --
    nunca intenta "adivinar" un dato faltante u obligatorio."""
    try:
        wb = load_workbook(BytesIO(contenido), data_only=True, read_only=True)
    except Exception as e:
        raise ErrorCatalogoExcel("El archivo no es un Excel (.xlsx) válido.") from e

    ws = wb.active
    filas = list(ws.iter_rows(values_only=True))
    if not filas:
        raise ErrorCatalogoExcel("El archivo está vacío.")

    encabezados = _encabezados_de_la_fila(filas[0])
    indice_por_clave: dict[str, int | None] = {}
    for encabezado_esperado, clave, _ancho, obligatorio in COLUMNAS:
        try:
            indice_por_clave[clave] = encabezados.index(encabezado_esperado)
        except ValueError:
            if obligatorio:
                raise ErrorCatalogoExcel(
                    f'Falta la columna obligatoria "{encabezado_esperado}" -- usa la plantilla '
                    "sin cambiarle los encabezados."
                )
            indice_por_clave[clave] = None

    registros = []
    for num_fila, fila in enumerate(filas[1:], start=2):
        if all(c is None or str(c).strip() == "" for c in fila):
            continue  # renglón vacío (común al final de la plantilla) -- se ignora

        registro = {}
        for _encabezado, clave, _ancho, _obligatorio in COLUMNAS:
            idx = indice_por_clave[clave]
            valor = fila[idx] if idx is not None and idx < len(fila) else None
            if isinstance(valor, str):
                valor = valor.strip() or None
            registro[clave] = valor

        faltantes = [
            encabezado for encabezado, clave, _ancho, obligatorio in COLUMNAS
            if obligatorio and registro.get(clave) in (None, "")
        ]
        if faltantes:
            plural = "n" if len(faltantes) > 1 else ""
            raise ErrorCatalogoExcel(
                f"Fila {num_fila}: falta{plural} " + ", ".join(f'"{c}"' for c in faltantes) + "."
            )

        # Clave del sistema central: ya es opcional (el portal genera la
        # suya), pero si viene tiene que ser un número -- un "N/A" o un
        # texto ahí casi siempre significa que el archivo trae otra cosa.
        if registro.get("cl_proveedor") in (None, ""):
            registro["cl_proveedor"] = None
        else:
            try:
                registro["cl_proveedor"] = int(registro["cl_proveedor"])
            except (TypeError, ValueError):
                raise ErrorCatalogoExcel(
                    f'Fila {num_fila}: "Clave del proveedor (referencia, opcional)" debe ser un '
                    "número entero, o quedarse vacía."
                )

        # El CP llega como número en muchos Excel (44100) -- se guarda como
        # texto para no perder los ceros a la izquierda (ej. "01000").
        if isinstance(registro.get("codigo_postal"), (int, float)):
            registro["codigo_postal"] = str(int(registro["codigo_postal"]))

        valor_tele = str(registro.get("teleconsulta") or "").strip().lower()
        registro["teleconsulta"] = 1 if valor_tele in ("si", "sí", "1", "true", "x") else 0

        # Opcionales -- si no hay geolocalización todavía, se deja en NULL
        # (no bloquea la carga, a diferencia del nombre).
        for campo, etiqueta in (("latitud", "Latitud"), ("longitud", "Longitud")):
            if registro.get(campo) in (None, ""):
                registro[campo] = None
                continue
            try:
                registro[campo] = float(registro[campo])
            except (TypeError, ValueError):
                raise ErrorCatalogoExcel(f'Fila {num_fila}: "{etiqueta}" debe ser un número (ej. 20.6736).')

        registros.append(registro)

    if not registros:
        raise ErrorCatalogoExcel("El archivo no trae ningún renglón con datos.")

    return registros
