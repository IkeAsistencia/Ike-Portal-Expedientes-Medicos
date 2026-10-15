-- =====================================================================
-- SP: dbo.ST_CP_ObtenerExpedientesSinProveedorMedico
-- Pantalla: Expedientes (listado + filtros)
-- Compatible con SQL Server 2012 (sin CREATE OR ALTER, sin STRING_SPLIT).
-- Requiere haber corrido antes 00_create_types.sql.
--
-- Esta pantalla trabaja 8 subservicios, cada uno con su propio
-- subsistema de datos en Core (mapeo confirmado contra la base real,
-- "Puntos a modificar.docx" de Cabina Médica, octubre 2026):
--   226 "Referencias Médicas"            -> dbo.S2_ReferciasMedicas
--   376 "Segunda Opinión"                -> dbo.S2_SegundaOpinion
--   377 "Check Up"                       -> dbo.Check_Up / cPerfilCheckUp
--   383 "CONSULTA MÉDICA EN CONSULTORIO" -> dbo.S2_ReferciasMedicas (misma tabla que 226)
--   403 "Renta de Equipo Médico"         -> dbo.s2_RentaEquipoMedico
--   404 "Enfermería a Domicilio"         -> dbo.s2_EnfermeriaDomicilio
--   420 "Plan Visión"                    -> dbo.s2_cPuntoVision / s2_cPaqueteDescPuntoVision
--   432 "Envío de Medicamentos"          -> dbo.s2_EnvioDeMedicamentos
--
-- OJO -- 226 "Referencias Médicas" había quedado EXCLUIDO del combo
-- Subservicio en el frontend (SUBSERVICIOS_EXCLUIDOS en
-- app/repositories/catalogos_repo.py, decisión del 2026-10-12, "pausado").
-- El documento de Cabina Médica que pide este cambio sí incluye
-- "Referencia" entre los servicios de primer contacto -- se agregó aquí
-- al SP porque así se pidió explícitamente, pero falta confirmar con el
-- negocio si esa pausa ya se levantó; si no, el combo seguirá sin
-- mostrarlo aunque el SP ya lo traiga.
--
-- Un expediente solo se considera "sin proveedor médico" si, además de
-- estar en dbo.Expediente con clEstatus=0, YA tiene su fila registrada
-- en el subsistema que le corresponde según su subservicio -- si Core
-- todavía no la creó, el expediente no está listo para escalarse aquí.
-- Cualquier otro subservicio (Ambulancia, Consulta Médica Virtual,
-- Médico a Domicilio, etc.) queda fuera de esta pantalla por completo.
--
-- Los alias de columnas se limpiaron (sin espacios/acentos) para que
-- sean más fáciles de consumir desde Python. Mapa:
--   'Fecha de apertura del servicio' -> FechaAperturaServicio
--   'Tipo de servicio'               -> TipoServicio
--   'Tipo de subservicio'            -> TipoSubservicio
--   'Nombre de titular'              -> NombreTitular
--   'Nombre de paciente'             -> NombrePaciente (sale de la tabla del subsistema de
--                                        cada subservicio -- ver Especialidad más abajo)
--   'Fecha asignacion cita'          -> FechaAsignacionProveedor  (OJO: es la fecha en que
--                                        se asignó el proveedor -PE.FechaAsignacion-, no la
--                                        fecha de la cita médica)
--   'Fecha de Cita'                  -> FechaCita  (solo existe el dato para 226/383
--                                        -S2_ReferciasMedicas.Cita-, 377 -Check_Up.FechaCita-,
--                                        403 -s2_RentaEquipoMedico.FechaIniciio, así está
--                                        escrito en la tabla real- y 404
--                                        -s2_EnfermeriaDomicilio.FechaInicio-; 420/376/432
--                                        no tienen ese campo en su subsistema, queda NULL)
--   'Número telefonico del usuario'  -> Telefono
--   'Correo del Usuario'             -> Email
--
-- Especialidad: solo 226/383 (catálogo dbo.cEspecialidad), 377 (perfil de
-- Check Up) y 420 (paquete de Plan Visión) tienen un dato equivalente a
-- "especialidad" en su subsistema. Para 376/403/404/432 no hay un campo
-- así -- queda NULL.
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
        E.FechaApertura                                                                        AS FechaAperturaCompleta,   -- con hora, para calcular el semáforo (ver app/services/semaforo_service.py)
        E.clExpediente                                                                        AS Expediente,
        E.clSubServicio                                                                        AS ClSubServicio,          -- código numérico, para el semáforo (no se muestra en pantalla)
        C.Nombre                                                                               AS Cuenta,
        S.dsServicio                                                                            AS TipoServicio,
        SS.dsSubservicio                                                                        AS TipoSubservicio,
        CONCAT(E.NombreUsrPF, ' ', ISNULL(E.ApellidoPaternoPF, ''), ' ', ISNULL(E.ApellidoMaternoPF, '')) AS NombreTitular,
        CASE E.clSubServicio
            WHEN 420 THEN PV.Nombre
            WHEN 377 THEN CKP.NombreBene
            WHEN 376 THEN SO.NombreBeneficiario
            WHEN 403 THEN REM.NombrePaciente
            WHEN 404 THEN ED.NombrePaciente
            WHEN 432 THEN EM.Paciente
            ELSE RM.NombrePaciente   -- 226/383
        END                                                                                     AS NombrePaciente,
        CASE E.clSubServicio
            WHEN 420 THEN PPV.dsPaqueteDesc
            WHEN 377 THEN PKU.dsPerfil
            WHEN 376 THEN NULL
            WHEN 403 THEN NULL
            WHEN 404 THEN NULL
            WHEN 432 THEN NULL
            ELSE ESP.dsEspecialidad   -- 226/383
        END                                                                                     AS Especialidad,
        CASE E.clSubServicio
            WHEN 420 THEN VE.dsEntFed
            WHEN 377 THEN KE.dsEntFed
            WHEN 376 THEN OE.dsEntFed
            WHEN 403 THEN RE.dsEntFed
            WHEN 404 THEN DE.dsEntFed
            WHEN 432 THEN ME.dsEntFed
            ELSE EF.dsEntFed   -- 226/383
        END                                                                                     AS Entidad,
        CASE E.clSubServicio
            WHEN 420 THEN VMD.dsMunDel
            WHEN 377 THEN KMD.dsMunDel
            WHEN 376 THEN OMD.dsMunDel
            WHEN 403 THEN RMD.dsMunDel
            WHEN 404 THEN DMD.dsMunDel
            WHEN 432 THEN MMD.dsMunDel
            ELSE MD.dsMunDel   -- 226/383
        END                                                                                     AS Municipio,
        CAST(PE.FechaAsignacion AS DATE)                                                        AS FechaAsignacionProveedor,
        CASE E.clSubServicio
            WHEN 420 THEN NULL                                                                  -- s2_cPuntoVision no tiene fecha de cita
            WHEN 377 THEN CAST(CKP.FechaCita AS DATE)
            WHEN 376 THEN NULL                                                                  -- S2_SegundaOpinion no tiene fecha de cita
            WHEN 403 THEN CAST(REM.FechaIniciio AS DATE)                                         -- nombre real de la columna (con doble "i")
            WHEN 404 THEN CAST(ED.FechaInicio AS DATE)
            WHEN 432 THEN NULL                                                                  -- s2_EnvioDeMedicamentos no tiene fecha de cita
            ELSE CAST(RM.Cita AS DATE)   -- 226/383
        END                                                                                     AS FechaCita,
        E.Telefono1                                                                             AS Telefono,
        E.Email                                                                                 AS Email
    FROM dbo.Expediente E
    INNER JOIN dbo.cServicio S              ON S.clServicio = E.clServicio
    INNER JOIN dbo.cSubServicio SS           ON SS.clSubServicio = E.clSubServicio
    INNER JOIN dbo.cCuenta C                 ON C.clCuenta = E.clCuenta
    INNER JOIN dbo.cUsrApp U                 ON U.clUsrApp = E.clUsrApp
    -- IMPORTANTE: las 7 tablas de subsistema de abajo NO son únicas por
    -- clExpediente -- confirmado contra la base real que varias pueden
    -- tener 2, 3 e incluso 5 filas para el mismo expediente (capturas
    -- repetidas/corregidas). Un LEFT JOIN normal multiplicaría la fila del
    -- expediente por cada una de esas filas -- se usa OUTER APPLY + TOP 1
    -- para quedarnos con una sola (la más reciente por FechaAp).
    --
    -- Consulta Médica en Consultorio (383): subsistema dbo.S2_ReferciasMedicas.
    OUTER APPLY (
        SELECT TOP 1 RM0.*
        FROM dbo.S2_ReferciasMedicas RM0
        WHERE RM0.clExpediente = E.clExpediente
        ORDER BY RM0.FechaAp DESC
    ) RM
    LEFT JOIN dbo.cEntFed EF                 ON EF.CodEnt = RM.CodEnt
    LEFT JOIN dbo.cMunDel MD                 ON MD.CodEnt = RM.CodEnt AND MD.CodMD = RM.CodMD
    LEFT JOIN dbo.cEspecialidad ESP          ON ESP.clEspecialidad = RM.clEspecialidad
    -- Plan Visión (420): subsistema dbo.s2_cPuntoVision.
    OUTER APPLY (
        SELECT TOP 1 PV0.*
        FROM dbo.s2_cPuntoVision PV0
        WHERE PV0.clExpediente = E.clExpediente
        ORDER BY PV0.FechaAp DESC
    ) PV
    LEFT JOIN dbo.s2_cPaqueteDescPuntoVision PPV ON PPV.clPaqueteDesc = PV.clPaquete
    LEFT JOIN dbo.cEntFed VE                 ON VE.CodEnt = PV.CodEnt
    LEFT JOIN dbo.cMunDel VMD                ON VMD.CodEnt = PV.CodEnt AND VMD.CodMD = PV.CodMD
    -- Check Up (377): subsistema dbo.Check_Up.
    OUTER APPLY (
        SELECT TOP 1 CKP0.*
        FROM dbo.Check_Up CKP0
        WHERE CKP0.clExpediente = E.clExpediente
        ORDER BY CKP0.FechaAp DESC, CKP0.clCheckUp DESC
    ) CKP
    LEFT JOIN dbo.cPerfilCheckUp PKU         ON PKU.clPerfil = CKP.clCheckUpTipo
    LEFT JOIN dbo.cEntFed KE                 ON KE.CodEnt = CKP.CodEnt
    LEFT JOIN dbo.cMunDel KMD                ON KMD.CodEnt = CKP.CodEnt AND KMD.CodMD = CKP.CodMD
    -- Segunda Opinión (376): subsistema dbo.S2_SegundaOpinion (OJO: su columna de
    -- entidad se llama "ConEnt", no "CodEnt" como en las demás tablas).
    OUTER APPLY (
        SELECT TOP 1 SO0.*
        FROM dbo.S2_SegundaOpinion SO0
        WHERE SO0.clExpediente = E.clExpediente
        ORDER BY SO0.FechaAp DESC
    ) SO
    LEFT JOIN dbo.cEntFed OE                 ON OE.CodEnt = SO.ConEnt
    LEFT JOIN dbo.cMunDel OMD                ON OMD.CodEnt = SO.ConEnt AND OMD.CodMD = SO.CodMD
    -- Renta de Equipo Médico (403): subsistema dbo.s2_RentaEquipoMedico.
    OUTER APPLY (
        SELECT TOP 1 REM0.*
        FROM dbo.s2_RentaEquipoMedico REM0
        WHERE REM0.clExpediente = E.clExpediente
        ORDER BY REM0.FechaAp DESC, REM0.clRentaEquipoMedico DESC
    ) REM
    LEFT JOIN dbo.cEntFed RE                 ON RE.CodEnt = REM.CodEnt
    LEFT JOIN dbo.cMunDel RMD                ON RMD.CodEnt = REM.CodEnt AND RMD.CodMD = REM.CodMD
    -- Enfermería a Domicilio (404): subsistema dbo.s2_EnfermeriaDomicilio.
    OUTER APPLY (
        SELECT TOP 1 ED0.*
        FROM dbo.s2_EnfermeriaDomicilio ED0
        WHERE ED0.clExpediente = E.clExpediente
        ORDER BY ED0.FechaAp DESC, ED0.clEnfermeriaDomicilio DESC
    ) ED
    LEFT JOIN dbo.cEntFed DE                 ON DE.CodEnt = ED.CodEnt
    LEFT JOIN dbo.cMunDel DMD                ON DMD.CodEnt = ED.CodEnt AND DMD.CodMD = ED.CodMd
    -- Envío de Medicamentos (432): subsistema dbo.s2_EnvioDeMedicamentos.
    OUTER APPLY (
        SELECT TOP 1 EM0.*
        FROM dbo.s2_EnvioDeMedicamentos EM0
        WHERE EM0.clExpediente = E.clExpediente
        ORDER BY EM0.FechaAp DESC
    ) EM
    LEFT JOIN dbo.cEntFed ME                 ON ME.CodEnt = EM.CodEnt
    LEFT JOIN dbo.cMunDel MMD                ON MMD.CodEnt = EM.CodEnt AND MMD.CodMD = EM.CodMD
    LEFT JOIN dbo.ProveedorxExpediente PE    ON PE.clExpediente = E.clExpediente AND PE.clEstatus = 3
    WHERE E.clEstatus = 0                                        -- "sin proveedor médico asignado"
        AND E.clSubServicio IN (226, 376, 377, 383, 403, 404, 420, 432)   -- subservicios que maneja esta pantalla
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
              OR (E.clSubServicio IN (226, 383) AND RM.clExpediente IS NOT NULL)
              OR (E.clSubServicio = 403 AND REM.clExpediente IS NOT NULL)
              OR (E.clSubServicio = 404 AND ED.clExpediente IS NOT NULL)
              OR (E.clSubServicio = 432 AND EM.clExpediente IS NOT NULL)
              -- 376 (Segunda Opinión) NO exige fila en S2_SegundaOpinion: esa tabla
              -- dejó de recibir registros nuevos desde diciembre de 2021 (confirmado
              -- contra la base real), mientras que Core sigue abriendo expedientes de
              -- este subservicio con normalidad hasta la fecha. Exigir la fila oculta
              -- TODOS los casos actuales -- queda pendiente confirmar con negocio/Core
              -- si esos datos (NombreBeneficiario, entidad, municipio) migraron a otra
              -- tabla; mientras tanto, el expediente se muestra igual, con esos campos
              -- en NULL si no hay fila.
              OR (E.clSubServicio = 376)
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
