from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response

from app.core.security import usuario_actual
from app.repositories import accesos_repo, especialidades_repo, proveedores_repo
from app.services.proveedores_excel_service import (
    ErrorCatalogoExcel,
    generar_plantilla_excel,
    leer_catalogo_excel,
)

TAMANO_MAXIMO_BYTES = 5 * 1024 * 1024  # 5 MB
TIPO_MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
# Firma real de un .xlsx (es un ZIP) -- el Content-Type lo manda el cliente
# (header HTTP), no es confiable por sí solo (mismo criterio que
# app/repositories/comprobantes_repo.py).
FIRMA_XLSX = b"PK\x03\x04"


def _requerir_administrador(usuario: dict = Depends(usuario_actual)) -> dict:
    """Ver app.repositories.accesos_repo.verificar_rol_administrador: la
    carga del catálogo de proveedores es exclusiva de Administrador."""
    try:
        accesos_repo.verificar_rol_administrador(usuario)
    except ValueError as e:
        raise HTTPException(403, str(e))
    return usuario


router = APIRouter(
    prefix="/proveedores-catalogo",
    tags=["Directorio de Proveedores -- Catálogo"],
    dependencies=[Depends(_requerir_administrador)],
)


@router.get("/plantilla")
def descargar_plantilla():
    archivo = generar_plantilla_excel()
    return Response(
        content=archivo,
        media_type=TIPO_MIME_XLSX,
        headers={"Content-Disposition": 'attachment; filename="plantilla_catalogo_proveedores.xlsx"'},
    )


@router.get("")
def resumen():
    por_origen = proveedores_repo.contar_por_origen()
    return {
        "total": proveedores_repo.contar_padron(),
        "dentro_de_la_red": por_origen.get(proveedores_repo.ORIGEN_CATALOGO, 0),
        "fuera_de_la_red": por_origen.get(proveedores_repo.ORIGEN_PORTAL, 0),
        "ultima_carga": proveedores_repo.obtener_ultima_carga(),
    }


@router.post("/cargar")
async def cargar(archivo: UploadFile = File(...), usuario: dict = Depends(usuario_actual)):
    if archivo.content_type != TIPO_MIME_XLSX:
        raise HTTPException(400, "El archivo debe ser un Excel (.xlsx).")

    contenido = await archivo.read()
    if len(contenido) > TAMANO_MAXIMO_BYTES:
        raise HTTPException(400, "El archivo supera el máximo permitido de 5 MB.")
    if not contenido.startswith(FIRMA_XLSX):
        raise HTTPException(400, "El archivo no es un Excel (.xlsx) válido.")

    try:
        registros = leer_catalogo_excel(contenido)
    except ErrorCatalogoExcel as e:
        raise HTTPException(400, str(e))

    # Especialidades que no empatan con el catálogo: el renglón se carga
    # igual (decisión del usuario, 2026-10-20), pero hay que avisarlo -- un
    # proveedor sin especialidad del catálogo no suma a ninguna tarjeta de
    # KPI, y eso se vería como "falta gente" en vez de "está mal escrito".
    no_reconocidas = especialidades_repo.especialidades_no_reconocidas(
        r.get("especialidad") for r in registros
    )

    rfc_usuario = usuario.get("rfc") or usuario.get("usuario") or "desconocido"
    # Carga INCREMENTAL: agrega los que no existan y actualiza los que ya
    # estaban conservándoles su clave (ver proveedores_repo.cargar_padron),
    # así las citas ya agendadas no quedan huérfanas.
    resultado = proveedores_repo.cargar_padron(registros, rfc_usuario)
    return {"ok": True, **resultado, "especialidades_no_reconocidas": no_reconocidas}
