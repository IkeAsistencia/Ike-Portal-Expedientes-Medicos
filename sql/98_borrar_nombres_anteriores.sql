-- =====================================================================
-- OPCIONAL — Borra los SPs con el nombre anterior (sin el prefijo ST_CP_)
--
-- Solo para bases donde se crearon con el nombre viejo (por ejemplo la de
-- desarrollo). En una base nueva (QA, producción) no hace falta correrlo.
--
-- Correrlo SOLO después de crear los SPs nuevos (scripts 01 a 05 y 07) y
-- de confirmar que el portal funciona con ellos.
-- =====================================================================

IF OBJECT_ID('dbo.ObtenerExpedientesSinProveedorMedico', 'P') IS NOT NULL
    DROP PROCEDURE dbo.ObtenerExpedientesSinProveedorMedico;
IF OBJECT_ID('dbo.ObtenerCatalogoServicio', 'P') IS NOT NULL
    DROP PROCEDURE dbo.ObtenerCatalogoServicio;
IF OBJECT_ID('dbo.ObtenerCatalogoCuentas', 'P') IS NOT NULL
    DROP PROCEDURE dbo.ObtenerCatalogoCuentas;
IF OBJECT_ID('dbo.RegistrarSeguimiento', 'P') IS NOT NULL
    DROP PROCEDURE dbo.RegistrarSeguimiento;
IF OBJECT_ID('dbo.ObtenerExpedientesSinRespuestaProveedor', 'P') IS NOT NULL
    DROP PROCEDURE dbo.ObtenerExpedientesSinRespuestaProveedor;
IF OBJECT_ID('dbo.ObtenerServicioMedico', 'P') IS NOT NULL
    DROP PROCEDURE dbo.ObtenerServicioMedico;
IF OBJECT_ID('dbo.ObtenerCatalogoSubServicio', 'P') IS NOT NULL
    DROP PROCEDURE dbo.ObtenerCatalogoSubServicio;
GO
