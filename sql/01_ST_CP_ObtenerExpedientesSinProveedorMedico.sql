-- =====================================================================
-- SP: dbo.ST_CP_ObtenerExpedientesSinProveedorMedico
-- Pantalla: Expedientes (listado + filtros)
-- Compatible con SQL Server 2012 (sin CREATE OR ALTER, sin STRING_SPLIT).
-- Requiere haber corrido antes 00_create_types.sql.
--
-- Esta pantalla solo trabaja 3 subservicios, cada uno con su propio
-- subsistema de datos en Core:
--   377 "Check Up"                      -> dbo.Check_Up / cPerfilCheckUp
--   383 "CONSULTA MÉDICA EN CONSULTORIO" -> dbo.S2_ReferciasMedicas
--   420 "Plan Visión"                    -> dbo.s2_cPuntoVision / s2_cPaqueteDescPuntoVision
-- Un expediente solo se considera "sin proveedor médico" si, además de
-- estar en dbo.Expediente con clEstatus=0, YA tiene su fila registrada
-- en el subsistema que le corresponde según su subservicio -- si Core
-- todavía no la creó, el expediente no está listo para escalarse aquí.
-- Cualquier otro subservicio (Ambulancia, Consulta Médica Virtual,
-- Médico a Domicilio, Referencias Médicas, etc.) queda fuera de esta
-- pantalla por completo.
--
-- Los alias de columnas se limpiaron (sin espacios/acentos) para que
-- sean más fáciles de consumir desde Python. Mapa:
--   'Fecha de apertura del servicio' -> FechaAperturaServicio
--   'Tipo de servicio'               -> TipoServicio
--   'Tipo de subservicio'            -> TipoSubservicio
--   'Nombre de titular'              -> NombreTitular
--   'Nombre de paciente'             -> NombrePaciente
--   'Fecha asignacion cita'          -> FechaAsignacionProveedor  (OJO: es la fecha en que
--                                        se asignó el proveedor -PE.FechaAsignacion-, no la
--                                        fecha de la cita médica)
--   'Fecha de Cita'                  -> FechaCita  (sale de S2_ReferciasMedicas.Cita para 383,
--                                        de Check_Up.FechaCita para 377; Plan Visión -420- no
--                                        tiene ese dato en s2_cPuntoVision, queda NULL)
--   'Número telefonico del usuario'  -> Telefono
--   'Correo del Usuario'             -> Email
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
            ELSE RM.NombrePaciente   -- 383
        END                                                                                     AS NombrePaciente,
        CASE E.clSubServicio
            WHEN 420 THEN PPV.dsPaqueteDesc
            WHEN 377 THEN PKU.dsPerfil
            ELSE ESP.dsEspecialidad   -- 383
        END                                                                                     AS Especialidad,
        CASE E.clSubServicio
            WHEN 420 THEN VE.dsEntFed
            WHEN 377 THEN KE.dsEntFed
            ELSE EF.dsEntFed   -- 383
        END                                                                                     AS Entidad,
        CASE E.clSubServicio
            WHEN 420 THEN VMD.dsMunDel
            WHEN 377 THEN KMD.dsMunDel
            ELSE MD.dsMunDel   -- 383
        END                                                                                     AS Municipio,
        CAST(PE.FechaAsignacion AS DATE)                                                        AS FechaAsignacionProveedor,
        CASE E.clSubServicio
            WHEN 420 THEN NULL                                                                  -- s2_cPuntoVision no tiene fecha de cita
            WHEN 377 THEN CAST(CKP.FechaCita AS DATE)
            ELSE CAST(RM.Cita AS DATE)   -- 383
        END                                                                                     AS FechaCita,
        E.Telefono1                                                                             AS Telefono,
        E.Email                                                                                 AS Email
    FROM dbo.Expediente E
    INNER JOIN dbo.cServicio S              ON S.clServicio = E.clServicio
    INNER JOIN dbo.cSubServicio SS           ON SS.clSubServicio = E.clSubServicio
    INNER JOIN dbo.cCuenta C                 ON C.clCuenta = E.clCuenta
    INNER JOIN dbo.cUsrApp U                 ON U.clUsrApp = E.clUsrApp
    -- Consulta Médica en Consultorio (383): subsistema dbo.S2_ReferciasMedicas.
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
    WHERE E.clEstatus = 0                          -- "sin proveedor médico asignado"
        AND E.clSubServicio IN (377, 383, 420)     -- únicos subservicios que maneja esta pantalla
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
              OR (E.clSubServicio = 383 AND RM.clExpediente IS NOT NULL)
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
