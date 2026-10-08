from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.repositories import openrouter_repo
from app.routers.admin_accesos import requerir_administrador
from app.schemas.openrouter import IteracionOpenRouter, OpenRouterPromptInput, OpenRouterRespuesta, ReporteOpenRouter
from app.services import openrouter_service

# Exclusivo de Administrador: expone costo real (tarjeta/saldo de OpenRouter)
# y dispara llamadas que consumen ese saldo -- mismo criterio que
# app/routers/admin_accesos.py (reutiliza su dependencia, sin excepción para
# sesiones SISE legadas).
router = APIRouter(prefix="/openrouter", tags=["OpenRouter"], dependencies=[Depends(requerir_administrador)])


@router.post("", response_model=OpenRouterRespuesta)
def ejecutar_prompt(data: OpenRouterPromptInput, usuario: dict = Depends(requerir_administrador)):
    """
    Manda `mensaje` a OpenRouter y registra el consumo real (tokens/costo)
    en la bitácora local. Cada llamada es una "iteración" para el reporte
    de abajo.
    """
    identificador = usuario.get("rfc") or usuario.get("usuario") or "desconocido"
    try:
        resultado = openrouter_service.ejecutar_prompt(
            data.mensaje, modelo=data.modelo, descripcion=data.descripcion, identificador=identificador
        )
    except openrouter_service.OpenRouterNoConfigurado as e:
        raise HTTPException(400, str(e))
    except openrouter_service.OpenRouterError as e:
        raise HTTPException(502, str(e))
    return OpenRouterRespuesta(**resultado)


@router.get("/iteraciones", response_model=list[IteracionOpenRouter])
def listar_iteraciones(desde: Optional[date] = None, hasta: Optional[date] = None):
    """Bitácora cruda, para auditar petición por petición."""
    filas = openrouter_repo.listar_iteraciones(
        desde.isoformat() if desde else None, hasta.isoformat() if hasta else None
    )
    return [IteracionOpenRouter(**f) for f in filas]


@router.get("/reporte", response_model=ReporteOpenRouter)
def reporte(desde: Optional[date] = None, hasta: Optional[date] = None):
    """
    Resumen de consumo/costo en el rango dado: totales, promedio, desglose
    por modelo y por día, y las peticiones de mayor consumo/costo.
    """
    datos = openrouter_repo.reporte(
        desde.isoformat() if desde else None, hasta.isoformat() if hasta else None
    )
    return ReporteOpenRouter(**datos)
