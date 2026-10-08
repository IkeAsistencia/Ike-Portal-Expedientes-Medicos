-- =====================================================================
-- ⚠️ DEPRECADO — YA NO SE USA, NO EJECUTAR
-- =====================================================================
-- Este SP se creó cuando aún no sabíamos que el catálogo real de
-- subservicios se obtenía con el SP legado dbo.sp_GetSubServicios2
-- (recibe @clServicio). Se conserva este archivo solo como referencia
-- histórica. El combo Subservicio de la pantalla Expedientes ya no usa
-- ninguno de los dos -- ahora usa dbo.ST_CP_ObtenerServicioMedico (ver
-- 07_ST_CP_ObtenerServicioMedico.sql), que tampoco depende de la cuenta.
-- =====================================================================

-- =====================================================================
-- SP: dbo.ST_CP_ObtenerCatalogoSubServicio
-- Pantalla: Expedientes (combo Subservicio en Filtros)
-- Compatible con SQL Server 2012. Requiere 00_create_types.sql.
--
-- La lista de subservicios permitidos (antes 377,420,383,433) ahora se
-- manda como Table-Valued Parameter, poblado desde la configuración de
-- la app (.env). Si la tabla llega vacía, NO se restringe (se listan
-- todos los del @clServicio indicado). CONFIRMAR si esta restricción
-- debe depender del usuario/cuenta en vez de ser una lista fija.
-- =====================================================================
IF OBJECT_ID('dbo.ST_CP_ObtenerCatalogoSubServicio', 'P') IS NOT NULL
    DROP PROCEDURE dbo.ST_CP_ObtenerCatalogoSubServicio;
GO

CREATE PROCEDURE dbo.ST_CP_ObtenerCatalogoSubServicio
    @clServicio             INT         = 4,
    @SubServiciosPermitidos dbo.IntList READONLY
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        clSubServicio,
        dsSubServicio
    FROM dbo.cSubServicio
    WHERE clServicio = @clServicio
      AND (
            NOT EXISTS (SELECT 1 FROM @SubServiciosPermitidos)
            OR clSubServicio IN (SELECT Value FROM @SubServiciosPermitidos)
          );
END
GO
