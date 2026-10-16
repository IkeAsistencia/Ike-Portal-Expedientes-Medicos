from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response

from app.core.security import usuario_actual
from app.repositories import accesos_repo, proveedores_catalogo_repo
from app.services.proveedores_catalogo_excel_service import (
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
    tags=["Directorio de Proveedores -- Catálogo Core"],
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
    return {
        "total": proveedores_catalogo_repo.contar_catalogo(),
        "ultima_carga": proveedores_catalogo_repo.obtener_ultima_carga(),
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

    rfc_usuario = usuario.get("rfc") or usuario.get("usuario") or "desconocido"
    total = proveedores_catalogo_repo.reemplazar_catalogo(registros, rfc_usuario)
    return {"ok": True, "total": total}
