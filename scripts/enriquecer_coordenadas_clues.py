"""
Llena la latitud y longitud que le faltan al padrón de proveedores, cruzándolo
contra el Catálogo CLUES de la Secretaría de Salud.

PARA QUÉ: el Excel que entrega el área trae las columnas de coordenadas
vacías, así que el mapa del Directorio no puede ubicar a nadie. CLUES publica
el domicilio Y las coordenadas de los establecimientos de salud del país, y
--a diferencia de Google Maps-- no restringe guardarlas (ver
WEB-SCRAPING-DOCTORALIA.md, secciones 10 y 11).

DE DÓNDE SACAR EL ARCHIVO (descarga directa, sin token ni registro):
    http://www.dgis.salud.gob.mx/contenidos/intercambio/clues_gobmx.html
    -> "Establecimientos de Salud (Formato XLSX)"   (~25 MB)

USO:
    # 1) Ver qué haría, SIN tocar la base (así arranca por defecto):
    python -m scripts.enriquecer_coordenadas_clues ESTABLECIMIENTO_SALUD.xlsx

    # 2) Aplicarlo:
    python -m scripts.enriquecer_coordenadas_clues ESTABLECIMIENTO_SALUD.xlsx --aplicar

    # Ver el detalle de cada proveedor que se enriquecería:
    python -m scripts.enriquecer_coordenadas_clues ESTABLECIMIENTO_SALUD.xlsx --detalle

Corre en seco a propósito: toca cientos de renglones del padrón real, así que
conviene revisar el plan antes de escribirlo.

QUÉ NO HACE:
  - No da de alta proveedores. CLUES no trae especialidad médica (el 100% de
    sus consultorios la tiene en "NO ESPECIFICADO"), así que solo sirve para
    ubicar a los que YA están en el padrón.
  - No pisa coordenadas existentes. Las que vinieron en el Excel del área son
    la fuente autorizada; aquí solo se llenan las que están vacías.
  - No adivina: si el cruce es ambiguo (misma razón social en varias
    sucursales) se deja al proveedor sin coordenadas. Ver el encabezado de
    app/services/clues_service.py.
"""

import argparse

from app.db.local_store import init_local_db
from app.repositories import proveedores_repo
from app.services import clues_service
from app.services.clues_service import ErrorCatalogoClues


def _porcentaje(parte: int, total: int) -> str:
    return f"{(parte / total * 100):.1f}%" if total else "0.0%"


def ejecutar(ruta_archivo: str, aplicar: bool = False, detalle: bool = False) -> dict:
    init_local_db()

    print(f"Leyendo el catálogo CLUES: {ruta_archivo}")
    print("(son ~64 mil establecimientos, puede tardar un minuto)")
    establecimientos = clues_service.leer_establecimientos(ruta_archivo)
    print(f"  establecimientos privados en operación: {len(establecimientos)}")

    padron = proveedores_repo.listar_padron()
    if not padron:
        print("\nEl padrón está vacío: no hay nada que enriquecer.")
        return {"asignaciones": 0, "aplicados": 0}

    plan = clues_service.emparejar(padron, establecimientos)
    asignaciones = plan["asignaciones"]
    sin_coordenadas = len(asignaciones) + len(plan["sin_coincidencia"])

    print(f"  de esos, con coordenadas: {plan['establecimientos_con_coordenadas']}")
    print(f"\nPadrón del portal: {plan['total_padron']} proveedor(es)")
    print(f"  ya tenían coordenadas:  {plan['ya_tenian_coordenadas']}")
    print(f"  sin coordenadas:        {sin_coordenadas}")

    por_cruce = {}
    for a in asignaciones:
        por_cruce[a["cruce"]] = por_cruce.get(a["cruce"], 0) + 1

    print(f"\nSe les puede poner coordenadas a {len(asignaciones)} "
          f"({_porcentaje(len(asignaciones), plan['total_padron'])} del padrón, "
          f"{_porcentaje(len(asignaciones), sin_coordenadas)} de los que no tienen):")
    for cruce, n in sorted(por_cruce.items(), key=lambda x: -x[1]):
        print(f"  {n:>5}  por {cruce}")
    print(f"  {len(plan['sin_coincidencia']):>5}  sin coincidencia confiable en CLUES")

    if detalle and asignaciones:
        print("\nDetalle:")
        for a in asignaciones:
            print(f"  {a['clave']}  {str(a['nombre'])[:38]:<38} {str(a['municipio'])[:18]:<18} "
                  f"{a['latitud']:.6f}, {a['longitud']:.6f}  [{a['cruce']}]")
            print(f"              CLUES {a['clues']}: {str(a['nombre_clues'])[:52]}")

    if not aplicar:
        print("\nNo se escribió nada (corrida en seco).")
        print("Para aplicarlo, vuelve a correrlo agregando --aplicar")
        return {"asignaciones": len(asignaciones), "aplicados": 0}

    aplicados = proveedores_repo.asignar_coordenadas(asignaciones)
    print(f"\nListo: {aplicados} proveedor(es) quedaron con coordenadas de CLUES.")

    resumen = proveedores_repo.contar_coordenadas()
    print(f"\nPadrón ahora: {resumen['con_coordenadas']} de {resumen['total']} "
          f"ubicables en el mapa ({_porcentaje(resumen['con_coordenadas'], resumen['total'])})")
    for origen, n in sorted(resumen["por_origen"].items()):
        print(f"  {n:>5}  origen '{origen}'")
    return {"asignaciones": len(asignaciones), "aplicados": aplicados}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Llena las coordenadas faltantes del padrón con el Catálogo CLUES.",
    )
    parser.add_argument("archivo", help="Ruta del .xlsx de Establecimientos de Salud (CLUES)")
    parser.add_argument(
        "--aplicar", action="store_true",
        help="Escribe los cambios. Sin esta bandera solo muestra qué haría.",
    )
    parser.add_argument(
        "--detalle", action="store_true",
        help="Lista proveedor por proveedor qué coordenadas se le pondrían.",
    )
    args = parser.parse_args()

    try:
        ejecutar(args.archivo, aplicar=args.aplicar, detalle=args.detalle)
    except ErrorCatalogoClues as e:
        raise SystemExit(f"No se pudo leer el catálogo: {e}")
    except FileNotFoundError:
        raise SystemExit(f"No se encontró el archivo: {args.archivo}")


if __name__ == "__main__":
    main()
