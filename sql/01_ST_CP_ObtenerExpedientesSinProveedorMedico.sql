-- =====================================================================
-- SP: dbo.ST_CP_ObtenerExpedientesSinProveedorMedico
-- Pantalla: Expedientes (listado + filtros)
-- Compatible con SQL Server 2012 (sin CREATE OR ALTER, sin STRING_SPLIT).
-- Requiere haber corrido antes 00_create_types.sql.
--
-- ACTUALIZADO: se reemplazó el SELECT por el query nuevo proporcionado
-- por el usuario (agrega Servicio, titular, teléfono, correo, fecha de
-- asignación de proveedor) y se agregaron los filtros @clServicio y
-- @clSubServicio.
--
-- Los alias de columnas se limpiaron (sin espacios/acentos) para que
-- sean más fáciles de consumir desde Python; no cambia la lógica del
-- query, solo el nombre de salida de cada columna. Mapa:
--   'Fecha de apertura del servicio' -> FechaAperturaServicio
--   'Tipo de servicio'               -> TipoServicio
--   'Tipo de subservicio'            -> TipoSubservicio
--   'Nombre de titular'              -> NombreTitular
--   'Nombre de paciente'             -> NombrePaciente
--   'Fecha asignacion cita'          -> FechaAsignacionProveedor  (OJO: es la fecha en que
--                                        se asignó el proveedor -PE.FechaAsignacion-, no la
--                                        fecha de la cita médica; el nombre original del
--                                        alias podía confundirse con 'Fecha de Cita')
--   'Fecha de Cita'                  -> FechaCita  (ver ACTUALIZADO 4: ahora sale de RM.Cita o
--                                        CKP.FechaCita según subservicio, no de CitaxExpediente)
--   'Número telefonico del usuario'  -> Telefono
--   'Correo del Usuario'             -> Email
--
-- ACTUALIZADO 2: NombrePaciente/Especialidad/Entidad/Municipio ya NO
-- salen siempre de dbo.S2_ReferciasMedicas (RM) -- esa tabla solo
-- aplica a los subservicios 226 "Referencias Médicas" y 383 "CONSULTA
-- MÉDICA EN CONSULTORIO" (se dejaron tal como estaba el query). Para
-- los otros dos subservicios del catálogo de esta pantalla, esos datos
-- viven en subsistemas distintos:
--   420 "Plan Visión" -> dbo.s2_cPuntoVision / s2_cPaqueteDescPuntoVision
--   377 "Check Up"     -> dbo.Check_Up / cPerfilCheckUp
-- El JOIN a RM pasó de INNER a LEFT (si no, los expedientes de Plan
-- Visión/Check Up -que no tienen fila en RM- desaparecían por completo
-- del listado); los JOIN nuevos a PV/PPV y CKP/PKU también son LEFT,
-- por la misma razón pero al revés (un expediente de Referencias
-- Médicas no tiene fila en esas tablas). Un CASE sobre E.clSubServicio
-- elige de cuál de las tres fuentes sale cada columna.
-- Confirmado contra la base real: 226=93, 377=289, 383=300, 420=3
-- expedientes abiertos (clEstatus=0) -- antes del INNER a RM, el
-- listado solo podía mostrar los 93 de Referencias Médicas.
--
-- ACTUALIZADO 3 (SUPERADO por ACTUALIZADO 5, ver abajo): regla de
-- negocio confirmada -- no todo expediente con clEstatus=0 debe
-- mostrarse en esta pantalla. El flujo normal es que Core puede asignar
-- proveedor de forma automática poco después de levantado el
-- expediente; esta pantalla era para escalar manualmente solo los que
-- YA llevaban @horasMinimas (default 8) desde FechaApertura sin que eso
-- haya pasado.
--
-- ACTUALIZADO 4: regla de negocio confirmada -- el expediente solo debe
-- considerarse si YA tiene su fila correspondiente en la tabla del
-- subsistema que le toca según su subservicio (antes, con el LEFT JOIN
-- a RM/PV/CKP, un expediente sin esa fila igual aparecía con esas
-- columnas en NULL). Se agregó el filtro de existencia al WHERE.
--
-- Se quitó el LEFT JOIN a dbo.CitaxExpediente (CE): no se usaba en
-- ninguna columna ni filtro (ver nota anterior), confirmado que se
-- puede quitar.
--
-- FechaCita ahora sale de 2 fuentes según el subservicio (antes salía
-- siempre de RM.Cita): dbo.S2_ReferciasMedicas.Cita (226/383, igual que
-- antes) y dbo.Check_Up.FechaCita (377). Plan Visión (420) no tiene un
-- campo de fecha de cita en dbo.s2_cPuntoVision -- queda NULL ahí.
--
-- ACTUALIZADO 5: se quitó @horasMinimas y su filtro -- confirmado que
-- ya no hace falta la "gracia" de horas desde FechaApertura: el filtro
-- de existencia del ACTUALIZADO 4 (el expediente debe tener ya su fila
-- en RM/PV/CKP según el subservicio) es ahora el que determina cuándo
-- un expediente "ya está listo" para mostrarse en esta pantalla, en vez
-- de un tiempo fijo de espera. No se usa en app/repositories/expedientes_repo.py
-- (la llamada desde Python nunca mandaba este parámetro, usaba el
-- default de 8).
-- =====================================================================
IF OBJECT_ID('dbo.ST_CP_ObtenerExpedientesSinProveedorMedico', 'P') IS NOT NULL
    DROP PROCEDURE dbo.ST_CP_ObtenerExpedientesSinProveedorMedico;
GO

CREATE PROCEDURE dbo.ST_CP_ObtenerExpedientesSinProveedorMedico
    @clExpediente  INT           = NULL,
    @fechaInicio   DATE          = NULL,
    @fechaFin      DATE          = NULL,
    @clServicio    INT           = NULL,
    @clSubServicio INT           = NULL,
    @Cuenta        dbo.IntList   READONLY
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        CAST(E.FechaApertura AS DATE)                                                        AS FechaAperturaServicio,
        E.clExpediente                                                                        AS Expediente,
        C.Nombre                                                                               AS Cuenta,
        S.dsServicio                                                                            AS TipoServicio,
        SS.dsSubservicio                                                                        AS TipoSubservicio,
        CONCAT(E.NombreUsrPF, ' ', ISNULL(E.ApellidoPaternoPF, ''), ' ', ISNULL(E.ApellidoMaternoPF, '')) AS NombreTitular,
        CASE E.clSubServicio
            WHEN 420 THEN PV.Nombre
            WHEN 377 THEN CKP.NombreBene
            ELSE RM.NombrePaciente
        END                                                                                     AS NombrePaciente,
        CASE E.clSubServicio
            WHEN 420 THEN PPV.dsPaqueteDesc
            WHEN 377 THEN PKU.dsPerfil
            ELSE ESP.dsEspecialidad
        END                                                                                     AS Especialidad,
        CASE E.clSubServicio
            WHEN 420 THEN VE.dsEntFed
            WHEN 377 THEN KE.dsEntFed
            ELSE EF.dsEntFed
        END                                                                                     AS Entidad,
        CASE E.clSubServicio
            WHEN 420 THEN VMD.dsMunDel
            WHEN 377 THEN KMD.dsMunDel
            ELSE MD.dsMunDel
        END                                                                                     AS Municipio,
        CAST(PE.FechaAsignacion AS DATE)                                                        AS FechaAsignacionProveedor,
        CASE E.clSubServicio
            WHEN 420 THEN NULL                                                                  -- s2_cPuntoVision no tiene fecha de cita
            WHEN 377 THEN CAST(CKP.FechaCita AS DATE)
            ELSE CAST(RM.Cita AS DATE)
        END                                                                                     AS FechaCita,
        E.Telefono1                                                                             AS Telefono,
        E.Email                                                                                 AS Email
    FROM dbo.Expediente E
    INNER JOIN dbo.cServicio S              ON S.clServicio = E.clServicio
    INNER JOIN dbo.cSubServicio SS           ON SS.clSubServicio = E.clSubServicio
    INNER JOIN dbo.cCuenta C                 ON C.clCuenta = E.clCuenta
    INNER JOIN dbo.cUsrApp U                 ON U.clUsrApp = E.clUsrApp
    -- Referencias Médicas (226) / Consulta Médica en Consultorio (383): igual que antes.
    LEFT JOIN dbo.S2_ReferciasMedicas RM     ON RM.clExpediente = E.clExpediente
    LEFT JOIN dbo.cEntFed EF                 ON EF.CodEnt = RM.CodEnt
    LEFT JOIN dbo.cMunDel MD                 ON MD.CodEnt = RM.CodEnt AND MD.CodMD = RM.CodMD
    LEFT JOIN dbo.cEspecialidad ESP          ON ESP.clEspecialidad = RM.clEspecialidad
    -- Plan Visión (420): subsistema dbo.s2_cPuntoVision.
    LEFT JOIN dbo.s2_cPuntoVision PV         ON PV.clExpediente = E.clExpediente
    LEFT JOIN dbo.s2_cPaqueteDescPuntoVision PPV ON PPV.clPaqueteDesc = PV.clPaquete
    LEFT JOIN dbo.cEntFed VE                 ON VE.CodEnt = PV.CodEnt
    LEFT JOIN dbo.cMunDel VMD                ON VMD.CodEnt = PV.CodEnt AND VMD.CodMD = PV.CodMD
    -- Check Up (377): subsistema dbo.Check_Up.
    LEFT JOIN dbo.Check_Up CKP               ON CKP.clExpediente = E.clExpediente
    LEFT JOIN dbo.cPerfilCheckUp PKU         ON PKU.clPerfil = CKP.clCheckUpTipo
    LEFT JOIN dbo.cEntFed KE                 ON KE.CodEnt = CKP.CodEnt
    LEFT JOIN dbo.cMunDel KMD                ON KMD.CodEnt = CKP.CodEnt AND KMD.CodMD = CKP.CodMD
    LEFT JOIN dbo.ProveedorxExpediente PE    ON PE.clExpediente = E.clExpediente AND PE.clEstatus = 3
    WHERE E.clEstatus = 0   -- fijo: "sin proveedor médico asignado"
        AND (@clExpediente  IS NULL OR E.clExpediente = @clExpediente)
        AND (@fechaInicio   IS NULL OR CAST(E.FechaApertura AS DATE) >= @fechaInicio)
        AND (@fechaFin      IS NULL OR CAST(E.FechaApertura AS DATE) <= @fechaFin)
        AND (@clServicio    IS NULL OR E.clServicio = @clServicio)
        AND (@clSubServicio IS NULL OR E.clSubServicio = @clSubServicio)
        AND (
              NOT EXISTS (SELECT 1 FROM @Cuenta)
              OR E.clCuenta IN (SELECT Value FROM @Cuenta)
            )
        -- El expediente solo cuenta si ya tiene su fila en la tabla del
        -- subsistema que le corresponde según su subservicio (si no,
        -- Core todavía no lo terminó de registrar del lado de ese
        -- subsistema).
        AND (
              (E.clSubServicio = 420 AND PV.clExpediente IS NOT NULL)
              OR (E.clSubServicio = 377 AND CKP.clExpediente IS NOT NULL)
              OR (E.clSubServicio NOT IN (420, 377) AND RM.clExpediente IS NOT NULL)
            )
    ORDER BY E.clExpediente DESC;
END
GO

-- =====================================================================
-- EJEMPLO DE EJECUCIÓN (para probar en prod)
-- @Cuenta es un Table-Valued Parameter (tipo dbo.IntList, creado por
-- 00_create_types.sql) -- no se puede pasar como un escalar normal, hay
-- que declarar una variable de tabla y pasarla.
--
-- IMPORTANTE: el SP en sí no acota a 3 meses -- esa regla vive en el
-- portal (Python, app/repositories/expedientes_repo.py:_piso_fecha_inicio),
-- que calcula "hoy - 3 meses" y lo manda como @fechaInicio. Si se llama
-- al SP con @fechaInicio = NULL, SÍ trae expedientes de cualquier
-- antigüedad (no hay ningún tope de fecha dentro del SP).
--
-- Caso "entra un usuario por primera vez" (como lo hace el portal al
-- abrir la pantalla Expedientes, sin filtros puestos todavía): sin
-- expediente puntual, sin filtro de servicio/subservicio, @fechaInicio
-- = hoy - 3 meses, @fechaFin = NULL (sin tope superior), y @Cuenta
-- vacío -- vacío significa "sin filtro de cuenta" (el WHERE lo
-- interpreta como "trae todas"), NO "no traer nada".
-- =====================================================================
DECLARE @CuentaVacio dbo.IntList;   -- sin filas = sin filtro de cuenta

EXEC dbo.ST_CP_ObtenerExpedientesSinProveedorMedico
    @clExpediente  = NULL,
    @fechaInicio   = '2026-07-12',   -- = hoy - 3 meses; calcúlalo en el momento de probar, ej. CAST(DATEADD(MONTH, -3, GETDATE()) AS DATE)
    @fechaFin      = NULL,           -- sin tope superior
    @clServicio    = NULL,
    @clSubServicio = NULL,
    @Cuenta        = @CuentaVacio;

-- Variante filtrando por 1 o más cuentas (ej. selección en el combo de Cuenta) --
-- misma regla de @fechaInicio que arriba:
DECLARE @CuentaFiltro dbo.IntList;
INSERT INTO @CuentaFiltro (Value) VALUES (2819), (2868);

EXEC dbo.ST_CP_ObtenerExpedientesSinProveedorMedico
    @clExpediente  = NULL,
    @fechaInicio   = '2026-07-12',
    @fechaFin      = NULL,
    @clServicio    = NULL,
    @clSubServicio = NULL,
    @Cuenta        = @CuentaFiltro;

-- Variante búsqueda puntual por número de expediente (ignora fechas/cuenta):
DECLARE @CuentaBusqueda dbo.IntList;

EXEC dbo.ST_CP_ObtenerExpedientesSinProveedorMedico
    @clExpediente  = 18108081,
    @Cuenta        = @CuentaBusqueda;
