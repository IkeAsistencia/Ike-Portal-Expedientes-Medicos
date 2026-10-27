"""
Pruebas de frontend/js/directorio/geo-estados.js, el archivo GENERADO con el
centro y los límites de cada entidad federativa.

Lo usa el mapa de "Buscar fuera de la red" para encuadrarse en el estado que
se está buscando en vez de ajustarse solo a los pines: con los resultados
concentrados en una ciudad, ajustar a los pines deja el resto del estado
fuera de vista.

Se revisa que:
  - estén las 32 entidades, con la misma clave del INEGI que el catálogo;
  - los límites sean coherentes (sur < norte, oeste < este) y caigan dentro
    de México (un error de signo en una coordenada pondría un estado en el
    océano y nadie lo notaría hasta verlo en pantalla);
  - el centro esté dentro de sus propios límites.

No se vuelve a generar el archivo aquí: eso requiere red (ver
scripts/generar_limites_estados.py).
"""
import json
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
GEO = RAIZ / "frontend" / "js" / "directorio" / "geo-estados.js"
CATALOGO = RAIZ / "scripts" / "catalogo_inegi_demo.json"

# Caja que engloba a todo México (incluye islas y el sur de Baja California).
MEXICO = {"sur": 14.0, "oeste": -118.5, "norte": 32.8, "este": -86.6}

PATRON = re.compile(
    r'"(?P<clave>\d{2})":\s*\{\s*'
    r"sur:\s*(?P<sur>-?\d+\.?\d*),\s*oeste:\s*(?P<oeste>-?\d+\.?\d*),\s*"
    r"norte:\s*(?P<norte>-?\d+\.?\d*),\s*este:\s*(?P<este>-?\d+\.?\d*),\s*"
    r"centro:\s*\{\s*lat:\s*(?P<lat>-?\d+\.?\d*),\s*lng:\s*(?P<lng>-?\d+\.?\d*)\s*\}"
)


def _limites() -> dict[str, dict[str, float]]:
    texto = GEO.read_text(encoding="utf-8")
    crudos = [m.groupdict() for m in PATRON.finditer(texto)]
    return {
        c["clave"]: {k: float(v) for k, v in c.items() if k != "clave"}
        for c in crudos
    }


def test_el_archivo_existe_y_trae_las_32_entidades():
    limites = _limites()
    assert len(limites) == 32, f"se esperaban 32 entidades, hay {len(limites)}"


def test_las_claves_son_las_del_catalogo_del_inegi():
    """Si las claves no empatan con catalogo_inegi_demo.json, el mapa no
    encuentra los límites y se queda encuadrado en los pines."""
    catalogo = json.loads(CATALOGO.read_text(encoding="utf-8"))
    assert set(_limites()) == set(catalogo)


def test_los_limites_son_coherentes():
    for clave, d in _limites().items():
        assert d["sur"] < d["norte"], f"{clave}: sur ({d['sur']}) no es menor que norte ({d['norte']})"
        assert d["oeste"] < d["este"], f"{clave}: oeste ({d['oeste']}) no es menor que este ({d['este']})"


def test_todo_cae_dentro_de_mexico():
    """Un signo cambiado en una coordenada pondría un estado en el Pacífico y
    el mapa se vería "raro" sin que ninguna prueba fallara."""
    for clave, d in _limites().items():
        for lado in ("sur", "norte"):
            assert MEXICO["sur"] <= d[lado] <= MEXICO["norte"], f"{clave}: {lado}={d[lado]}"
        for lado in ("oeste", "este"):
            assert MEXICO["oeste"] <= d[lado] <= MEXICO["este"], f"{clave}: {lado}={d[lado]}"


def test_el_centro_cae_dentro_de_sus_limites():
    for clave, d in _limites().items():
        assert d["sur"] <= d["lat"] <= d["norte"], f"{clave}: el centro se sale en latitud"
        assert d["oeste"] <= d["lng"] <= d["este"], f"{clave}: el centro se sale en longitud"


def test_los_estados_no_son_del_tamano_de_un_punto():
    """Un bbox de área casi cero sería una coordenada suelta, no un estado:
    el mapa se acercaría al máximo y se vería igual que antes del cambio."""
    for clave, d in _limites().items():
        assert (d["norte"] - d["sur"]) > 0.05, f"{clave}: el alto es sospechosamente chico"
        assert (d["este"] - d["oeste"]) > 0.05, f"{clave}: el ancho es sospechosamente chico"
