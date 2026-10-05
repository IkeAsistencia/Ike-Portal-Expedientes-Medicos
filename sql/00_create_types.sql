-- =====================================================================
-- Tipo de tabla (Table-Valued Parameter) para pasar listas de IDs
-- enteros a los Stored Procedures, en vez de STRING_SPLIT (que no
-- existe en SQL Server 2012; llegó hasta la versión 2016).
--
-- Usado para: @Cuenta (multi-selección de cuentas en Expedientes),
-- @SubServiciosPermitidos, @CuentasPermitidas (catálogos).
--
-- IMPORTANTE: los tipos de tabla NO se pueden "ALTER". Si en el futuro
-- necesitas cambiar su estructura, hay que hacer DROP TYPE (y de los
-- SPs que lo usan) y volver a crear todo.
-- =====================================================================
IF NOT EXISTS (
    SELECT 1 FROM sys.types
    WHERE name = 'IntList' AND is_table_type = 1 AND schema_id = SCHEMA_ID('dbo')
)
BEGIN
    CREATE TYPE dbo.IntList AS TABLE (
        Value INT NOT NULL PRIMARY KEY
    );
END
GO
