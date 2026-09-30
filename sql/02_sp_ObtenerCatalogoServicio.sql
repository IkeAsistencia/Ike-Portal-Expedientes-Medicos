-- =====================================================================
-- SP: dbo.ObtenerCatalogoServicio
-- Pantalla: Expedientes (combo Servicio en Filtros)
--
-- Basado en:
--   select clServicio, dsServicio from dbo.cServicio where clServicio = 4
--
-- Tal como te lo compartieron, este catálogo siempre regresa un solo
-- registro (clServicio = 4) porque el filtro va sobre un valor fijo.
-- Se dejó como parámetro (@clServicio = 4 por default) por si en el
-- futuro se necesita traer más de un servicio; con el valor por
-- default, el combo Servicio en pantalla mostrará una sola opción.
-- =====================================================================
IF OBJECT_ID('dbo.ObtenerCatalogoServicio', 'P') IS NOT NULL
    DROP PROCEDURE dbo.ObtenerCatalogoServicio;
GO

CREATE PROCEDURE dbo.ObtenerCatalogoServicio
    @clServicio INT = 4
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        clServicio,
        dsServicio
    FROM dbo.cServicio
    WHERE clServicio = @clServicio;
END
GO
