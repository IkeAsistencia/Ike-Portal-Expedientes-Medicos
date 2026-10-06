-- =====================================================================
-- SP: dbo.ObtenerExpedientesSinRespuestaProveedor
-- Uso: cron/timer (jobs/validar_estatus_proveedor.py)
--
-- Regresa los expedientes cuyo proveedor sigue "asignado, sin
-- respuesta" (dbo.ProveedorxExpediente.clEstatus = 3) desde hace al
-- menos @horasMinimas horas.
--
-- CONFIRMADO: clEstatus = 3 en dbo.ProveedorxExpediente corresponde a
-- "Asignación de Proveedor" — es el estatus que el sistema core le da
-- al expediente cuando se le asigna un proveedor. Por eso este mismo
-- valor se usa para obtener FechaAsignacion (fecha en que se asignó el
-- proveedor), tanto aquí como en dbo.ObtenerExpedientesSinProveedorMedico.
-- =====================================================================
IF OBJECT_ID('dbo.ObtenerExpedientesSinRespuestaProveedor', 'P') IS NOT NULL
    DROP PROCEDURE dbo.ObtenerExpedientesSinRespuestaProveedor;
GO

CREATE PROCEDURE dbo.ObtenerExpedientesSinRespuestaProveedor
    @horasMinimas INT
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        E.clExpediente                     AS Expediente,
        C.Nombre                           AS Cuenta,
        RM.NombrePaciente                  AS NombrePaciente,
        CAST(E.FechaApertura AS DATE)      AS FechaApertura,
        PE.FechaAsignacion                 AS FechaAsignacionProveedor,
        DATEDIFF(HOUR, PE.FechaAsignacion, GETDATE()) AS HorasSinRespuesta
    FROM dbo.Expediente E
    INNER JOIN dbo.cCuenta C              ON C.clCuenta = E.clCuenta
    INNER JOIN dbo.S2_ReferciasMedicas RM ON RM.clExpediente = E.clExpediente
    INNER JOIN dbo.ProveedorxExpediente PE ON PE.clExpediente = E.clExpediente AND PE.clEstatus = 3
    WHERE DATEDIFF(HOUR, PE.FechaAsignacion, GETDATE()) >= @horasMinimas
    ORDER BY PE.FechaAsignacion ASC;
END
GO
