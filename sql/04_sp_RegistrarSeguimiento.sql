-- =====================================================================
-- SP: dbo.RegistrarSeguimiento
-- Pantalla: Seguimiento Expediente -> botón "Actualizar en SISE"
-- Compatible con SQL Server 2012.
--
-- Inserta un registro en la tabla YA EXISTENTE dbo.Seguimiento (según lo
-- especificado por el usuario):
--   clExpediente  = expediente al que pertenece el seguimiento
--   clEstatus     = 9  (constante fija de esta tabla de bitácora; NO debe
--                        confundirse con el "estatus de negocio" del
--                        expediente en la app -Abierto/Seguimiento
--                        Proveedor/etc-, que vive solo en la aplicación
--                        y nunca toca SQL Server)
--   Observaciones = texto capturado en el textarea de la plantilla
--                    Seguimiento Expediente (máx. 1500 caracteres)
--   clUsrApp      = usuario autenticado (obtenido vía
--                    dbo.sp_EncriptDesEncriptPassword en el login)
--   Fecha         = fecha/hora del servidor en el momento del registro
--
-- CONFIRMAR: nombres exactos de columnas de dbo.Seguimiento si difieren
-- de los aquí usados (clExpediente, clEstatus, Observaciones, clUsrApp,
-- Fecha), y si hay alguna otra columna NOT NULL no mencionada que
-- también deba poblarse.
-- =====================================================================
IF OBJECT_ID('dbo.RegistrarSeguimiento', 'P') IS NOT NULL
    DROP PROCEDURE dbo.RegistrarSeguimiento;
GO

CREATE PROCEDURE dbo.RegistrarSeguimiento
    @clExpediente  INT,
    @Observaciones NVARCHAR(1500),
    @clUsrApp      INT
AS
BEGIN
    SET NOCOUNT ON;

    IF @Observaciones IS NULL OR LTRIM(RTRIM(@Observaciones)) = ''
    BEGIN
        RAISERROR('El campo de seguimiento no puede estar vacío.', 16, 1);
        RETURN;
    END

    INSERT INTO dbo.Seguimiento (clExpediente, clEstatus, Observaciones, clUsrApp, Fecha)
    VALUES (@clExpediente, 9, @Observaciones, @clUsrApp, GETDATE());

    SELECT SCOPE_IDENTITY() AS clSeguimiento, GETDATE() AS FechaRegistro;
END
GO
