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
--     where clServicio = 4 and clSubServicio in (226,376,377,383,403,404,420,432)
--
-- Igual que dbo.ST_CP_ObtenerCatalogoServicio, el Servicio siempre es el
-- mismo (clServicio = 4, "Asistencia Médica"), así que se deja fijo
-- como default. La lista de Subservicios permitidos también se deja
-- fija — confirmar si debe salir de configuración en vez de estar fija
-- en el SP.
-- NOTA: se pidió incluir también el 483, pero ese id no existe en
-- dbo.cSubServicio de esta base (IKE_TEST) — se dejó fuera aquí.
-- ACTUALIZADO 2: la lista debe ser EXACTAMENTE la misma que trabaja
-- dbo.ST_CP_ObtenerExpedientesSinProveedorMedico (sql/01_..._Medico.sql)
-- -- si un subservicio sale aquí pero esa pantalla no lo soporta (o
-- viceversa), el combo ofrece algo que siempre da 0 resultados, o
-- esconde algo que sí tiene datos. Se agregaron los 4 que faltaban:
-- 376 Segunda Opinión, 403 Renta de Equipo Médico, 404 Enfermería a
-- Domicilio, 432 Envío de Medicamentos.
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
      AND clSubServicio IN (226, 376, 377, 383, 403, 404, 420, 432);
END
GO
