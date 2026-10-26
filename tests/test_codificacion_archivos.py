"""
Ningún archivo del proyecto debe tener acentos corrompidos ("Ã³" en vez de
"ó"). Pasa cuando una herramienta lee un archivo UTF-8 como si fuera de
Windows-1252 y lo vuelve a guardar: el archivo sigue siendo válido, las demás
pruebas pasan, pero los mensajes que ve el usuario salen con caracteres raros.
Ya ocurrió una vez (2026-10-26, app/routers/solicitudes_alta_medico.py).
"""
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
CARPETAS = ("app", "frontend", "jobs", "scripts", "sql", "tests")
EXTENSIONES = {".py", ".js", ".css", ".html", ".sql", ".md"}
# "Ã" seguido de un carácter de continuación, "Â " y "â€": las huellas típicas.
HUELLAS = ("Ã¡", "Ã©", "Ã­", "Ã³", "Ãº", "Ã±", "Ã‘", "Ã“", "Ã‰", "Â¿", "Â¡", "â€")


def _archivos():
    for carpeta in CARPETAS:
        base = RAIZ / carpeta
        if base.exists():
            yield from (p for p in base.rglob("*") if p.suffix in EXTENSIONES and p.is_file())
    yield from (p for p in RAIZ.glob("*.md") if p.is_file())


@pytest.mark.parametrize("ruta", sorted(_archivos()), ids=lambda p: str(p.relative_to(RAIZ)))
def test_sin_acentos_corrompidos_ni_bom(ruta):
    if ruta.name == Path(__file__).name:
        return  # este archivo menciona las huellas a propósito
    contenido = ruta.read_bytes()
    assert not contenido.startswith(b"\xef\xbb\xbf"), "el archivo trae BOM al inicio"
    texto = contenido.decode("utf-8")
    encontradas = [h for h in HUELLAS if h in texto]
    assert not encontradas, f"acentos corrompidos: {encontradas}"
