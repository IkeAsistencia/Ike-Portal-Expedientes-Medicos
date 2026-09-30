-- =====================================================================
-- SP: dbo.ObtenerExpedientesSinProveedorMedico
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
--   'Fecha de Cita'                  -> FechaCita  (ahora viene de RM.Cita, no de CitaxExpediente)
--   'Número telefonico del usuario'  -> Telefono
--   'Correo del Usuario'             -> Email
--
-- NOTA: el LEFT JOIN a dbo.CitaxExpediente (CE) se dejó tal como estaba
-- en el query proporcionado, pero ninguna de sus columnas se usa ya en
-- el SELECT ni en el WHERE — parece un join que quedó sin uso al
-- cambiar la fuente de la fecha de cita a RM.Cita. Lo dejamos por
-- fidelidad a lo que compartiste; avísame si se puede quitar.
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
-- =====================================================================
IF OBJECT_ID('dbo.ObtenerExpedientesSinProveedorMedico', 'P') IS NOT NULL
    DROP PROCEDURE dbo.ObtenerExpedientesSinProveedorMedico;
GO

CREATE PROCEDURE dbo.ObtenerExpedientesSinProveedorMedico
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
        CAST(RM.Cita AS DATE)                                                                   AS FechaCita,
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
    LEFT JOIN dbo.CitaxExpediente CE         ON CE.clExpediente = E.clExpediente
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
    ORDER BY E.clExpediente DESC;
END
GO
