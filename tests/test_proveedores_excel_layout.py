"""
Pruebas del layout del Excel del padrón (el que validó el área, 2026-10-20) y
de la llave con la que se reconoce a un proveedor entre cargas.

Son pruebas del servicio y del repositorio, sin HTTP: aquí lo que importa es
que un archivo con ESOS encabezados se lea completo y que las 662 filas del
padrón real no se fusionen entre ellas.
"""
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from app.repositories.proveedores_repo import ORIGEN_APOYO, ORIGEN_CATALOGO, llaves_candidatas
from app.services.proveedores_excel_service import (
    COLUMNA_CLAVE_CENTRAL,
    COLUMNAS,
    ErrorCatalogoExcel,
    generar_plantilla_excel,
    leer_catalogo_excel,
)

# Encabezado EXACTO del archivo validado, en su orden. Si alguien le cambia
# una palabra a COLUMNAS, esta prueba lo caza antes de que el área suba un
# archivo que ya no se lee.
ENCABEZADO_VALIDADO = [
    "Nombre completo *",
    "Especialidad *",
    "Cédula profesional",
    "RFC *",
    "Estado *",
    "Municipio *",
    "Calle, No. Ext., No. Int. *",
    "Colonia *",
    "Código Postal *",
    "Nombre del consultorio/clínica",
    "Teléfono Consultorio",
    "Correo electrónico*",
    "Horario de atención",
    "Costo de consulta",
    "Convenio (aseguradora)",
    "Teleconsulta (Sí/No)",
    "Latitud Consultorio*",
    "Longitud Consultorio*",
]


def _excel(encabezados: list[str], filas: list[list], hoja: str = "Padrón de proveedores") -> bytes:
    """Un Excel de una sola hoja, nombrada como la hoja del padrón por
    default -- para que las pruebas de encabezado/columnas no se vean
    afectadas por el reconocimiento de hoja (ver tests de más abajo, que sí
    prueban eso)."""
    wb = Workbook()
    ws = wb.active
    ws.title = hoja
    for col, texto in enumerate(encabezados, start=1):
        ws.cell(row=1, column=col, value=texto)
    for i, fila in enumerate(filas, start=2):
        for col, valor in enumerate(fila, start=1):
            ws.cell(row=i, column=col, value=valor)
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _excel_hojas(hojas: dict[str, tuple[list[str], list[list]]]) -> bytes:
    """Un Excel con varias hojas: {nombre_hoja: (encabezados, filas)}."""
    wb = Workbook()
    wb.remove(wb.active)
    for nombre, (encabezados, filas) in hojas.items():
        ws = wb.create_sheet(nombre)
        for col, texto in enumerate(encabezados, start=1):
            ws.cell(row=1, column=col, value=texto)
        for i, fila in enumerate(filas, start=2):
            for col, valor in enumerate(fila, start=1):
                ws.cell(row=i, column=col, value=valor)
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


# ---------- El encabezado ----------

def test_las_columnas_son_las_del_archivo_validado():
    assert [c[0] for c in COLUMNAS] == ENCABEZADO_VALIDADO


def test_la_plantilla_descargable_trae_ese_mismo_encabezado():
    """Lo que el portal entrega tiene que ser lo que el portal acepta."""
    ws = load_workbook(BytesIO(generar_plantilla_excel())).active
    encabezados = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    assert encabezados == ENCABEZADO_VALIDADO


def test_la_plantilla_descargable_se_lee_de_vuelta():
    registros = leer_catalogo_excel(generar_plantilla_excel())
    assert len(registros) == 1
    assert registros[0]["nombre"] == "Dra. Laura Méndez Ruiz"
    assert registros[0]["codigo_postal"] == "44100"
    assert registros[0]["telefono"] == "33 1234 5678"
    assert registros[0]["email"] == "consultorio@correo.mx"


def test_se_lee_el_archivo_validado_completo():
    """Las 18 columnas del archivo del área se reconocen todas."""
    datos = leer_catalogo_excel(_excel(ENCABEZADO_VALIDADO, [[
        "DIAGNOSTICOS POR IMAGEN DE MAZATLAN S.C.", "GABINETE", 2345876512,
        "DIM-001129-HCA      ", "SINALOA", "MAZATLAN", "AV. DE LOS ANDES",
        "ALAMEDA", 82123, "DIAGNOSTICOS POR IMAGEN", 6699902650, None,
        "Lunes a Viernes de 7:00 a 20:00", 0, "CON-323243", "NO", None, None,
    ]]))
    assert len(datos) == 1
    r = datos[0]
    assert r["nombre"] == "DIAGNOSTICOS POR IMAGEN DE MAZATLAN S.C."
    assert r["especialidad"] == "GABINETE"
    assert r["rfc"] == "DIM-001129-HCA", "se le quitan los espacios de relleno"
    assert r["estado"] == "SINALOA"
    assert r["codigo_postal"] == "82123"
    assert r["telefono"] == "6699902650"
    assert r["email"] is None
    assert r["latitud"] is None and r["longitud"] is None
    assert r["teleconsulta"] == 0


@pytest.mark.parametrize("encabezado", [
    "Correo electrónico*",   # como viene en el archivo validado (pegado)
    "Correo electrónico *",  # con espacio
    "Correo electrónico",    # sin asterisco
    "CORREO ELECTRONICO",    # sin acentos y en mayúsculas
])
def test_el_asterisco_y_los_acentos_no_rompen_el_encabezado(encabezado):
    """El "*" cambia de significado y de posición según la versión del
    archivo, así que no puede decidir si una columna se reconoce o no."""
    encabezados = list(ENCABEZADO_VALIDADO)
    encabezados[11] = encabezado
    datos = leer_catalogo_excel(_excel(encabezados, [
        ["Dr. Prueba"] + [None] * 10 + ["correo@dominio.mx"] + [None] * 6
    ]))
    assert datos[0]["email"] == "correo@dominio.mx"


def test_se_siguen_aceptando_los_encabezados_de_la_plantilla_anterior():
    """Alguien puede traer todavía un archivo descargado antes del cambio."""
    viejos = [
        "Nombre completo *", "Especialidad", "Cédula profesional", "RFC",
        "Estado", "Municipio",
        "Domicilio de consulta: Calle, No. Ext., No. Int.",
        "Domicilio de consulta: Colonia", "Domicilio de consulta: Código Postal",
        "Nombre del consultorio/clínica", "Teléfono", "Correo electrónico",
        "Horario de atención", "Costo de consulta", "Convenio (aseguradora)",
        "Teleconsulta (Sí/No)", "Latitud", "Longitud",
        "Clave del proveedor (referencia, opcional)",
    ]
    datos = leer_catalogo_excel(_excel(viejos, [[
        "Dra. Laura", "CARDIOLOGIA", "8453219", "MERL850214H23", "Jalisco",
        "Guadalajara", "Av. Vallarta 1450", "Americana", "44100",
        "Consultorio 302", "33 1234 5678", "laura@correo.mx", "L-V 9-14",
        "800", "GNP", "Sí", 20.6736, -103.344, 10234,
    ]]))
    r = datos[0]
    assert r["calle_num_ext_int"] == "Av. Vallarta 1450"
    assert r["colonia"] == "Americana"
    assert r["codigo_postal"] == "44100"
    assert r["telefono"] == "33 1234 5678"
    assert r["cl_proveedor"] == 10234
    assert r["teleconsulta"] == 1


def test_las_columnas_pueden_venir_en_otro_orden():
    datos = leer_catalogo_excel(_excel(
        ["Especialidad *", "Nombre completo *"],
        [["CARDIOLOGIA", "Dra. Laura"]],
    ))
    assert datos[0]["nombre"] == "Dra. Laura"
    assert datos[0]["especialidad"] == "CARDIOLOGIA"


def test_un_encabezado_irreconocible_si_se_rechaza():
    with pytest.raises(ErrorCatalogoExcel, match="No se reconoció"):
        leer_catalogo_excel(_excel(["Una", "Otra"], [["x", "y"]]))


# ---------- Las dos hojas ----------
# El archivo real (2026-10-28) trae "Padrón de proveedores" (origen
# 'catalogo') y "Proveedores red de apoyo" (origen 'apoyo', con menos
# columnas: sin cédula, RFC ni consultorio, y sin correo/horario/costo/
# convenio/teleconsulta/coordenadas).

ENCABEZADO_APOYO = ENCABEZADO_VALIDADO[:11]  # hasta "Teléfono Consultorio" inclusive


def test_se_leen_las_dos_hojas_con_su_origen():
    datos = leer_catalogo_excel(_excel_hojas({
        "Padrón de proveedores": (ENCABEZADO_VALIDADO, [
            ["Dr. Padrón", "CARDIOLOGIA"] + [None] * 16,
        ]),
        "Proveedores red de apoyo": (ENCABEZADO_APOYO, [
            ["Dr. Apoyo", "CARDIOLOGIA"] + [None] * 9,
        ]),
    }))
    por_nombre = {r["nombre"]: r["origen"] for r in datos}
    assert por_nombre == {"Dr. Padrón": ORIGEN_CATALOGO, "Dr. Apoyo": ORIGEN_APOYO}


def test_el_nombre_de_hoja_acepta_texto_despues_del_prefijo():
    """"Padrón de proveedores 2026" cuenta igual que "Padrón de proveedores"."""
    datos = leer_catalogo_excel(_excel(
        ENCABEZADO_VALIDADO, [["Dr. Prueba", "CARDIOLOGIA"] + [None] * 16],
        hoja="Padrón de proveedores 2026",
    ))
    assert datos[0]["origen"] == ORIGEN_CATALOGO


def test_el_archivo_puede_traer_solo_una_de_las_dos_hojas():
    datos = leer_catalogo_excel(_excel(
        ENCABEZADO_APOYO, [["Dr. Apoyo", "CARDIOLOGIA"] + [None] * 9],
        hoja="Proveedores red de apoyo",
    ))
    assert len(datos) == 1
    assert datos[0]["origen"] == ORIGEN_APOYO


def test_la_hoja_de_apoyo_no_exige_las_columnas_que_no_trae():
    """cédula, RFC, consultorio, correo, horario, costo, convenio,
    teleconsulta y coordenadas no están en esta hoja -- entran vacíos, no
    tumban la carga (instrucción del usuario, 2026-10-28)."""
    datos = leer_catalogo_excel(_excel(
        ENCABEZADO_APOYO, [["Dr. Apoyo", "CARDIOLOGIA", None, None, "Jalisco",
                             "Guadalajara", "Av. Vallarta 1", "Americana", "44100",
                             None, "33 1234 5678"]],
        hoja="Proveedores red de apoyo",
    ))
    r = datos[0]
    assert r["cedula"] is None
    assert r["rfc"] is None
    assert r["consultorio"] is None
    assert r["email"] is None
    assert r["horario"] is None
    assert r["telefono"] == "33 1234 5678"


def test_ninguna_hoja_reconocida_se_rechaza():
    with pytest.raises(ErrorCatalogoExcel, match="ninguna hoja reconocida"):
        leer_catalogo_excel(_excel_hojas({
            "Hoja1": (["Una", "Otra"], [["x", "y"]]),
        }))


# ---------- Nada se exige ----------

def test_ninguna_columna_es_obligatoria():
    """Instrucción del usuario: lo que no traiga información entra vacío."""
    datos = leer_catalogo_excel(_excel(ENCABEZADO_VALIDADO, [
        [None, None, None, None, None, None, None, None, None,
         None, None, None, None, None, None, None, None, "algo"],
    ]))
    assert len(datos) == 1
    assert datos[0]["nombre"] == "", "lo unico NOT NULL de la tabla"
    assert datos[0]["especialidad"] is None


def test_el_codigo_postal_se_rellena_a_cinco_digitos():
    """Excel guarda el CP como número y le come el cero: el archivo real
    trae 166 filas así."""
    datos = leer_catalogo_excel(_excel(ENCABEZADO_VALIDADO, [
        ["A"] + [None] * 7 + [6700] + [None] * 9,
        ["B"] + [None] * 7 + [82123] + [None] * 9,
        ["C"] + [None] * 7 + ["01000"] + [None] * 9,
    ]))
    assert [d["codigo_postal"] for d in datos] == ["06700", "82123", "01000"]


@pytest.mark.parametrize("relleno", ["NULL", "null", "-", "N/A", "sin dato"])
def test_el_texto_de_relleno_entra_como_vacio(relleno):
    datos = leer_catalogo_excel(_excel(ENCABEZADO_VALIDADO, [
        ["Dr. Prueba", "CARDIOLOGIA", None, relleno, relleno, relleno,
         relleno, relleno, relleno, None, relleno, None, relleno, relleno,
         None, None, None, None],
    ]))
    r = datos[0]
    for campo in ("rfc", "estado", "municipio", "calle_num_ext_int", "colonia",
                  "codigo_postal", "telefono", "horario", "costo_consulta"):
        assert r[campo] is None, campo


def test_una_latitud_invalida_no_tumba_la_carga():
    datos = leer_catalogo_excel(_excel(ENCABEZADO_VALIDADO, [
        ["Dr. Prueba"] + [None] * 15 + ["no es un numero", "tampoco"],
    ]))
    assert datos[0]["latitud"] is None
    assert datos[0]["longitud"] is None


def test_una_latitud_con_coma_decimal_se_entiende():
    datos = leer_catalogo_excel(_excel(ENCABEZADO_VALIDADO, [
        ["Dr. Prueba"] + [None] * 15 + ["20,6736", "-103,344"],
    ]))
    assert datos[0]["latitud"] == pytest.approx(20.6736)
    assert datos[0]["longitud"] == pytest.approx(-103.344)


# ---------- La llave de identidad ----------

def _registro(**extra):
    base = {
        "nombre": "OPTICAS DEVLYN", "especialidad": "OPTICA",
        "calle_num_ext_int": "AV. COYOACAN 1000", "colonia": "XOCO",
        "codigo_postal": "03330", "municipio": "BENITO JUAREZ",
        "estado": "CIUDAD DE MEXICO", "telefono": "5555555555",
    }
    base.update(extra)
    return base


def test_la_cedula_ya_no_identifica_al_proveedor():
    """El padrón real trae la MISMA cédula de relleno en las 662 filas: si
    identificara, todo lo que comparte especialidad se fusionaría (quedaban
    38 de 662)."""
    con_cedula = llaves_candidatas(_registro(cedula="2345876512"))
    sin_cedula = llaves_candidatas(_registro())
    otra_cedula = llaves_candidatas(_registro(cedula="9999999"))
    assert con_cedula == sin_cedula == otra_cedula


def test_dos_sucursales_de_la_misma_cadena_son_proveedores_distintos():
    """Mismo nombre y especialidad, distinto domicilio: son dos consultorios
    con su propia agenda."""
    sucursal_a = llaves_candidatas(_registro(calle_num_ext_int="AV. COYOACAN 1000"))
    sucursal_b = llaves_candidatas(_registro(calle_num_ext_int="AV. UNIVERSIDAD 500"))
    assert sucursal_a != sucursal_b


def test_el_telefono_desempata_dos_sucursales_en_el_mismo_domicilio():
    a = llaves_candidatas(_registro(telefono="5555555555"))
    b = llaves_candidatas(_registro(telefono="5544443333"))
    assert a != b


def test_la_misma_sucursal_se_reconoce_entre_cargas():
    """Aunque cambien los datos que NO son de identidad (costo, horario), la
    llave debe ser la misma para que conserve su clave y sus citas."""
    antes = llaves_candidatas(_registro(costo_consulta="500", horario="L-V 9-14"))
    despues = llaves_candidatas(_registro(costo_consulta="900", horario="L-S 8-20"))
    assert antes == despues


def test_las_mayusculas_y_los_acentos_no_cambian_la_llave():
    assert llaves_candidatas(_registro(municipio="BENITO JUAREZ")) == \
           llaves_candidatas(_registro(municipio="Benito Juárez"))


def test_un_renglon_sin_nada_identificable_no_se_fusiona_con_otro():
    assert llaves_candidatas({}) == []
    assert llaves_candidatas({"costo_consulta": "500"}) == []


def test_una_especialidad_distinta_es_otro_renglon():
    """Un mismo consultorio que da dos especialidades lleva una agenda por
    cada una."""
    assert llaves_candidatas(_registro(especialidad="OPTICA")) != \
           llaves_candidatas(_registro(especialidad="OFTALMOLOGIA"))


# ---------- El archivo real ----------
# Solo corre si el .xlsx está en la carpeta del proyecto. Está en .gitignore
# (lleva datos de proveedores reales), así que en otra máquina se salta.

RUTA_ARCHIVO_REAL = Path(__file__).resolve().parents[1] / "plantilla_catalogo_proveedores.xlsx"

sin_archivo_real = pytest.mark.skipif(
    not RUTA_ARCHIVO_REAL.exists(),
    reason="plantilla_catalogo_proveedores.xlsx no está en el proyecto (va en .gitignore)",
)


@sin_archivo_real
def test_el_archivo_real_se_lee_entero_y_sin_fusionar_proveedores():
    """
    La prueba que de verdad importa: con la llave anterior (que usaba la
    cédula) este archivo entraba como 38 proveedores en vez de 662, porque
    todas sus filas traen la misma cédula de relleno.
    """
    registros = leer_catalogo_excel(RUTA_ARCHIVO_REAL.read_bytes())
    assert len(registros) > 600, "debe leer todas las filas con datos"

    llaves = [llaves_candidatas(r) for r in registros]
    assert all(k for k in llaves), "ningún renglón debe quedarse sin llave"

    distintas = {k[0] for k in llaves}
    assert len(distintas) == len(registros), (
        f"se fusionarían {len(registros) - len(distintas)} renglones: "
        "cada sucursal tiene que ser un proveedor aparte"
    )


@sin_archivo_real
def test_el_archivo_real_no_deja_codigos_postales_a_medias():
    registros = leer_catalogo_excel(RUTA_ARCHIVO_REAL.read_bytes())
    cps = [r["codigo_postal"] for r in registros if r["codigo_postal"]]
    assert cps, "el archivo sí trae códigos postales"
    assert all(len(c) >= 5 for c in cps), "los de 4 dígitos se rellenan a 5"
    assert any(c.startswith("0") for c in cps), "y hay varios que empiezan en 0"
