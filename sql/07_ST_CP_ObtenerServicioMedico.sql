-- =====================================================================
-- SP: dbo.ST_CP_ObtenerServicioMedico
-- Pantalla: Expedientes (combo Subservicio en Filtros)
--
-- Reemplaza el uso del SP legado dbo.sp_GetSubServicios2 -- DEPRECADO
-- desde este script. Ese SP legado filtraba por cobertura de una cuenta
-- específica (@clCuenta), lo cual no aplica aquí: el filtro Cuenta de
-- la pantalla Expedientes permite elegir varias cuentas a la vez, así
-- que el catálogo de Subservicio no puede depender de una sola cuenta.
--
-- Basado en:
--   select clServicio, dsServicio from dbo.cServicio where clServicio = 4
--   select clSubServicio, dsSubServicio from dbo.cSubServicio
--     where clServicio = 4 and clSubServicio in (226,377,420,383)
--
-- Igual que dbo.ST_CP_ObtenerCatalogoServicio, el Servicio siempre es el
-- mismo (clServicio = 4, "Asistencia Médica"), así que se deja fijo
-- como default. La lista de Subservicios permitidos (226,377,420,383)
-- también se deja fija — confirmar si debe salir de configuración en
-- vez de estar fija en el SP.
-- NOTA: se pidió incluir también el 483, pero ese id no existe en
-- dbo.cSubServicio de esta base (IKE_TEST) — se dejó fuera aquí.
-- ACTUALIZADO: se agregó el 226 "Referencias Médicas" -- es el único de
-- los 4 subservicios de esta pantalla con expedientes reales hoy en
-- IKE_TEST; sin él en esta lista, el combo Subservicio (y el filtro
-- local del frontend) lo escondían aunque el SP de expedientes ya lo
-- trajera bien. Ver sql/01_ST_CP_ObtenerExpedientesSinProveedorMedico.sql.
-- =====================================================================
IF OBJECT_ID('dbo.ST_CP_ObtenerServicioMedico', 'P') IS NOT NULL
    DROP PROCEDURE dbo.ST_CP_ObtenerServicioMedico;
GO

CREATE PROCEDURE dbo.ST_CP_ObtenerServicioMedico
    @clServicio INT = 4
AS
BEGIN
    SET NOCOUNT ON;

    -- Valida que el Servicio exista antes de usarlo (evita depender de
    -- que el valor recibido en @clServicio sea correcto a ciegas).
    DECLARE @clServicioValido INT;

    SELECT @clServicioValido = clServicio
    FROM dbo.cServicio
    WHERE clServicio = @clServicio;

    SELECT
        clSubServicio,
        dsSubServicio
    FROM dbo.cSubServicio
    WHERE clServicio = @clServicioValido
      AND clSubServicio IN (226, 377, 420, 383);
END
GO
