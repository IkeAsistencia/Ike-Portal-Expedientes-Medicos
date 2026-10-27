"""
Genera frontend/js/directorio/geo-estados.js: el centro y los límites
(bbox) de cada entidad federativa, para que el mapa de "Buscar fuera de la
red" se encuadre en el estado que se está buscando en vez de ajustarse solo
a los pines (que con 20 consultorios en una ciudad deja el resto del estado
fuera de vista).

Se corre A MANO y el resultado se versiona:

    python scripts/generar_limites_estados.py

No se ejecuta en tiempo de arranque ni de despliegue: el portal no debe
depender de GitHub para dibujar un mapa.

Fuente: https://github.com/angelnmara/geojson (mexicoHigh.json, derivado de
los marcos geoestadísticos del INEGI). Solo se guardan los límites, no el
polígono completo: el mapa necesita encuadrar, no pintar fronteras.

Las claves son las del INEGI (dos dígitos), las mismas de
scripts/catalogo_inegi_demo.json, para no depender del CodEnt de SISE.
"""
from __future__ import annotations

import json
import unicodedata
import urllib.request
from pathlib import Path

URL = "https://raw.githubusercontent.com/angelnmara/geojson/master/mexicoHigh.json"
RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "frontend" / "js" / "directorio" / "geo-estados.js"
CATALOGO = RAIZ / "scripts" / "catalogo_inegi_demo.json"

# El GeoJSON usa el nombre corto y el catálogo del INEGI el nombre oficial.
# Se comparan sin acentos ni mayúsculas, y estas cuatro no coinciden ni así.
ALIAS = {
    "MEXICO": "15",            # catálogo: "México" (Estado de México)
    "COAHUILA": "05",          # catálogo: "Coahuila De Zaragoza"
    "MICHOACAN": "16",         # catálogo: "Michoacán De Ocampo"
    "VERACRUZ": "30",          # catálogo: "Veracruz De Ignacio De La Llave"
}


def normalizar(texto: str) -> str:
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return " ".join(sin_acentos.upper().split())


def recorrer(coordenadas, visitar):
    """Recorre un anillo/multi-anillo de coordenadas sin suponer su forma."""
    if isinstance(coordenadas, (int, float)):
        return
    if coordenadas and isinstance(coordenadas[0], (int, float)):
        visitar(coordenadas[0], coordenadas[1])
        return
    for parte in coordenadas:
        recorrer(parte, visitar)


def limites_de(geometria: dict) -> dict | None:
    lngs: list[float] = []
    lats: list[float] = []
    tipo = geometria.get("type")
    if tipo == "Polygon":
        recorrer(geometria["coordinates"], lambda lng, lat: (lngs.append(lng), lats.append(lat)))
    elif tipo == "MultiPolygon":
        for poligono in geometria["coordinates"]:
            recorrer(poligono, lambda lng, lat: (lngs.append(lng), lats.append(lat)))
    else:
        return None
    if not lngs or not lats:
        return None
    sur, norte = min(lats), max(lats)
    oeste, este = min(lngs), max(lngs)
    return {
        "sur": round(sur, 4),
        "oeste": round(oeste, 4),
        "norte": round(norte, 4),
        "este": round(este, 4),
        "centro": {"lat": round((sur + norte) / 2, 4), "lng": round((oeste + este) / 2, 4)},
    }


def main() -> None:
    catalogo = json.loads(CATALOGO.read_text(encoding="utf-8"))
    por_nombre = {normalizar(datos["nombre"]): clave for clave, datos in catalogo.items()}

    with urllib.request.urlopen(URL, timeout=60) as respuesta:
        geojson = json.loads(respuesta.read().decode("utf-8"))

    resultado: dict[str, dict] = {}
    sin_match: list[str] = []
    for rasgo in geojson["features"]:
        nombre = rasgo["properties"]["name"]
        clave = ALIAS.get(normalizar(nombre)) or por_nombre.get(normalizar(nombre))
        if clave is None:
            sin_match.append(nombre)
            continue
        limites = limites_de(rasgo["geometry"])
        if limites:
            resultado[clave] = limites

    if sin_match:
        raise SystemExit(f"No se pudo emparejar con el catálogo: {sin_match}")
    faltantes = sorted(set(catalogo) - set(resultado))
    if faltantes:
        raise SystemExit(f"El GeoJSON no trae estas entidades: {faltantes}")

    lineas = [
        "/* GENERADO por scripts/generar_limites_estados.py -- no editar a mano.",
        "   ",
        "   Centro y límites (bbox) de cada entidad federativa, por clave del",
        "   INEGI. Lo usa el mapa de \"Buscar fuera de la red\" para encuadrarse en",
        "   el estado que se está buscando: ajustarse solo a los pines deja fuera",
        "   el resto del estado cuando los resultados se concentran en una ciudad.",
        "   ",
        "   Fuente: https://github.com/angelnmara/geojson (mexicoHigh.json). */",
        "",
        "export const LIMITES_ESTADOS = {",
    ]
    for clave in sorted(resultado):
        d = resultado[clave]
        c = d["centro"]
        lineas.append(
            f'  "{clave}": {{ sur: {d["sur"]}, oeste: {d["oeste"]}, '
            f'norte: {d["norte"]}, este: {d["este"]}, '
            f'centro: {{ lat: {c["lat"]}, lng: {c["lng"]} }} }},'
        )
    lineas += ["};", ""]

    DESTINO.write_text("\n".join(lineas), encoding="utf-8")
    print(f"{DESTINO.relative_to(RAIZ)}: {len(resultado)} entidades")


if __name__ == "__main__":
    main()
