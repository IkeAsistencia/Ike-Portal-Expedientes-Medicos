-- =====================================================================
-- SP: dbo.ObtenerCatalogoCuentas
-- Pantalla: Expedientes (combo Cuenta / Cuenta Específica en Filtros)
-- Compatible con SQL Server 2012. Requiere 00_create_types.sql.
--
-- La lista de cuentas permitidas (antes 2819,2868,1366,2806,2654,1519)
-- ahora se manda como Table-Valued Parameter, poblado desde la
-- configuración de la app (.env). Tabla vacía = sin restricción.
-- CONFIRMAR si esta restricción debe depender del usuario en vez de
-- ser una lista fija.
-- =====================================================================
IF OBJECT_ID('dbo.ObtenerCatalogoCuentas', 'P') IS NOT NULL
    DROP PROCEDURE dbo.ObtenerCatalogoCuentas;
GO

CREATE PROCEDURE dbo.ObtenerCatalogoCuentas
    @CuentasPermitidas dbo.IntList READONLY
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        clCuenta,
        Nombre
    FROM dbo.cCuenta
    WHERE (
            NOT EXISTS (SELECT 1 FROM @CuentasPermitidas)
            OR clCuenta IN (SELECT Value FROM @CuentasPermitidas)
          );
END
GO
