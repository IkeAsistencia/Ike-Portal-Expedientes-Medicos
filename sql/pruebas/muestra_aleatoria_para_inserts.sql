-- =====================================================================
-- SOLO PARA DESARROLLO/PRUEBAS -- no inserta ni modifica nada por sí
-- solo. Compatible con SQL Server 2012 (sin STRING_AGG, que es de 2017+).
--
-- Flujo pensado para "sembrar" expedientes de prueba nuevos (no para
-- reusar un clExpediente que ya existe):
--   1) Se toman, al azar, 3 expedientes reales por cada uno de los 8
--      subservicios del combo -- junto con su fila ya existente en la
--      tabla de subsistema que le corresponda (mismo mapeo que
--      sql/01_ST_CP_ObtenerExpedientesSinProveedorMedico.sql) -- como
--      "plantilla" de valores realistas (entidad/municipio/nombre/etc.)
--   2) Por cada uno se arma (comentado, SIN ejecutarlo) el INSERT para
--      dbo.Expediente, y justo después el INSERT para su tabla de
--      subsistema -- este último usa @NuevoExpediente como clExpediente
--      en vez del número de la plantilla, porque debe apuntar al
--      expediente NUEVO que se vaya a crear, no al que se usó de ejemplo.
--   3) Ninguna columna IDENTITY se incluye en los INSERT que arma (ni
--      dbo.Expediente.clExpediente ni las tres tablas de subsistema que
--      tienen su propio identity -- Check_Up.clCheckUp,
--      s2_RentaEquipoMedico.clRentaEquipoMedico,
--      s2_EnfermeriaDomicilio.clEnfermeriaDomicilio -- se detectan solas
--      vía sys.columns.is_identity, no hace falta listarlas a mano).
--   4) En dbo.Expediente, cualquier columna de tipo date/datetime
--      (FechaApertura, FechaRegistro, etc.) va con GETDATE() en vez del
--      valor de la plantilla -- excepto FechaTermino, que siempre va NULL
--      (expediente nuevo/abierto, todavía no tiene fecha de término).
--   5) clEstatus siempre va en 0 ("sin proveedor médico asignado") -- es
--      lo que exige dbo.ST_CP_ObtenerExpedientesSinProveedorMedico para
--      que el expediente nuevo se vea en el portal.
--
-- Cómo usarlo cuando de verdad se vaya a sembrar un expediente (a mano,
-- revisando antes cada valor):
--   DECLARE @NuevoExpediente INT;
--   <pegar aquí el INSERT INTO dbo.Expediente (...) VALUES (...);>
--   SET @NuevoExpediente = SCOPE_IDENTITY();
--   <pegar aquí el INSERT INTO <tabla de subsistema> (...) VALUES (...);>
--
-- Mapeo de "nombre del paciente" por tabla de subsistema (ya viene
-- resuelto solo porque se copia de la fila real de esa tabla, no hace
-- falta mapearlo a mano -- se deja aquí nomás de referencia):
--   226/383 -> S2_ReferciasMedicas.NombrePaciente   377 -> Check_Up.NombreBene
--   376 -> S2_SegundaOpinion.NombreBeneficiario     403 -> s2_RentaEquipoMedico.NombrePaciente
--   404 -> s2_EnfermeriaDomicilio.NombrePaciente    420 -> s2_cPuntoVision.Nombre
--   432 -> s2_EnvioDeMedicamentos.Paciente
-- =====================================================================
SET NOCOUNT ON;

IF OBJECT_ID('tempdb..#Muestra') IS NOT NULL DROP TABLE #Muestra;
CREATE TABLE #Muestra (clSubServicio INT, clExpediente INT);

-- Un bloque por subservicio -- cada uno exige que el expediente YA tenga
-- su fila en la tabla de subsistema que le toca (misma regla que el SP
-- real), para que la plantilla traiga datos de verdad y no puros NULL.
-- 376 (Segunda Opinión) es la única excepción: esa tabla dejó de recibir
-- registros desde dic-2021 (ver nota en el SP real), así que se deja sin
-- exigir la fila -- si el azar no encuentra ninguno con fila, igual trae
-- el expediente solo (su INSERT de subsistema va a salir con columnas en
-- NULL, hay que llenarlas a mano al revisar).
INSERT INTO #Muestra (clExpediente, clSubServicio)
SELECT TOP 3 E.clExpediente, 226 FROM dbo.Expediente E
WHERE E.clSubServicio = 226 AND EXISTS (SELECT 1 FROM dbo.S2_ReferciasMedicas RM WHERE RM.clExpediente = E.clExpediente)
ORDER BY NEWID();

INSERT INTO #Muestra (clExpediente, clSubServicio)
SELECT TOP 3 E.clExpediente, 383 FROM dbo.Expediente E
WHERE E.clSubServicio = 383 AND EXISTS (SELECT 1 FROM dbo.S2_ReferciasMedicas RM WHERE RM.clExpediente = E.clExpediente)
ORDER BY NEWID();

INSERT INTO #Muestra (clExpediente, clSubServicio)
SELECT TOP 3 E.clExpediente, 376 FROM dbo.Expediente E
WHERE E.clSubServicio = 376
ORDER BY NEWID();

INSERT INTO #Muestra (clExpediente, clSubServicio)
SELECT TOP 3 E.clExpediente, 377 FROM dbo.Expediente E
WHERE E.clSubServicio = 377 AND EXISTS (SELECT 1 FROM dbo.Check_Up CKP WHERE CKP.clExpediente = E.clExpediente)
ORDER BY NEWID();

INSERT INTO #Muestra (clExpediente, clSubServicio)
SELECT TOP 3 E.clExpediente, 403 FROM dbo.Expediente E
WHERE E.clSubServicio = 403 AND EXISTS (SELECT 1 FROM dbo.s2_RentaEquipoMedico REM WHERE REM.clExpediente = E.clExpediente)
ORDER BY NEWID();

INSERT INTO #Muestra (clExpediente, clSubServicio)
SELECT TOP 3 E.clExpediente, 404 FROM dbo.Expediente E
WHERE E.clSubServicio = 404 AND EXISTS (SELECT 1 FROM dbo.s2_EnfermeriaDomicilio ED WHERE ED.clExpediente = E.clExpediente)
ORDER BY NEWID();

INSERT INTO #Muestra (clExpediente, clSubServicio)
SELECT TOP 3 E.clExpediente, 420 FROM dbo.Expediente E
WHERE E.clSubServicio = 420 AND EXISTS (SELECT 1 FROM dbo.s2_cPuntoVision PV WHERE PV.clExpediente = E.clExpediente)
ORDER BY NEWID();

INSERT INTO #Muestra (clExpediente, clSubServicio)
SELECT TOP 3 E.clExpediente, 432 FROM dbo.Expediente E
WHERE E.clSubServicio = 432 AND EXISTS (SELECT 1 FROM dbo.s2_EnvioDeMedicamentos EM WHERE EM.clExpediente = E.clExpediente)
ORDER BY NEWID();

IF OBJECT_ID('tempdb..#Resultado') IS NOT NULL DROP TABLE #Resultado;
CREATE TABLE #Resultado (Subservicio NVARCHAR(100), InsertComentado NVARCHAR(MAX));
GO  -- CREATE PROCEDURE debe ser la única sentencia del batch (SQL Server < 2016 SP1)

-- Procedimiento TEMPORAL (vive solo en esta sesión): arma, para cualquier
-- tabla, el texto comentado de un INSERT por cada fila que cumpla @where,
-- usando sys.columns/sys.types -- así sirve igual para dbo.Expediente que
-- para cualquiera de las 7 tablas de subsistema, sin tener que listar las
-- columnas a mano. Reglas que aplica solo:
--   - Nunca incluye una columna IDENTITY (se genera sola al insertar).
--   - Si la tabla NO es dbo.Expediente y tiene columna clExpediente, esa
--     columna sale como el texto literal "@NuevoExpediente" en vez del
--     número real de la plantilla -- debe apuntar al expediente nuevo que
--     se cree, no al que se usó de ejemplo (ver encabezado del script).
--   - Si la tabla SÍ es dbo.Expediente, cualquier columna date/datetime
--     sale como GETDATE() -- excepto FechaTermino, que sale como NULL --
--     y clEstatus siempre sale como 0.
-- NUNCA ejecuta el INSERT que arma -- solo lo arma como texto.
CREATE PROCEDURE #GenerarInserts
    @etiqueta NVARCHAR(100),
    @tabla    SYSNAME,
    @where    NVARCHAR(MAX) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @q CHAR(1) = CHAR(39);   -- comilla simple, para no pelearse con el escapado anidado

    DECLARE @columna SYSNAME, @tipo SYSNAME;
    DECLARE @columnas NVARCHAR(MAX) = '';
    DECLARE @valoresExpr NVARCHAR(MAX) = '';
    DECLARE @expr NVARCHAR(MAX);

    DECLARE cur CURSOR LOCAL FAST_FORWARD FOR
        SELECT c.name, ty.name
        FROM sys.columns c
        JOIN sys.types ty ON ty.user_type_id = c.user_type_id
        WHERE c.object_id = OBJECT_ID(@tabla)
          AND c.is_identity = 0   -- nunca se setea a mano, se genera sola
        ORDER BY c.column_id;

    OPEN cur;
    FETCH NEXT FROM cur INTO @columna, @tipo;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        IF @columnas <> '' SET @columnas = @columnas + ', ';
        SET @columnas = @columnas + '[' + @columna + ']';

        IF @tabla <> 'dbo.Expediente' AND @columna = 'clExpediente'
            -- FK al expediente NUEVO (todavía no existe mientras se arma
            -- este texto) -- se deja como placeholder literal, no como
            -- valor real de la plantilla.
            SET @expr = @q + '@NuevoExpediente' + @q;
        ELSE IF @tabla = 'dbo.Expediente' AND @columna = 'FechaTermino'
            -- Expediente nuevo/abierto: todavía no tiene fecha de término.
            SET @expr = @q + 'NULL' + @q;
        ELSE IF @tabla = 'dbo.Expediente' AND @tipo IN ('date','datetime','datetime2','smalldatetime','time','datetimeoffset')
            -- Todas las fechas de dbo.Expediente (FechaApertura, FechaRegistro,
            -- etc.) van con la fecha/hora real de cuando se vaya a insertar,
            -- no con la de la plantilla que se usó de ejemplo.
            SET @expr = @q + 'GETDATE()' + @q;
        ELSE IF @tabla = 'dbo.Expediente' AND @columna = 'clEstatus'
            -- Siempre 0 ("sin proveedor médico asignado") -- es lo que exige
            -- dbo.ST_CP_ObtenerExpedientesSinProveedorMedico para que el
            -- expediente nuevo aparezca en el portal.
            SET @expr = @q + '0' + @q;
        ELSE IF @tipo IN ('char','varchar','nchar','nvarchar','text','ntext','xml','uniqueidentifier',
                           'date','datetime','datetime2','smalldatetime','time','datetimeoffset')
            -- Tipo con comillas: se escapa cualquier comilla simple que traiga el valor
            -- (REPLACE la duplica) y se envuelve entre comillas.
            SET @expr =
                'CASE WHEN [' + @columna + '] IS NULL THEN ' + @q + 'NULL' + @q +
                ' ELSE ' + REPLICATE(@q, 4) +
                ' + REPLACE(CONVERT(NVARCHAR(MAX), [' + @columna + ']), ' + REPLICATE(@q, 4) + ', ' + REPLICATE(@q, 6) + ')' +
                ' + ' + REPLICATE(@q, 4) + ' END';
        ELSE
            -- Numérico/bit/otros: se convierte a texto tal cual, sin comillas.
            SET @expr = 'ISNULL(CONVERT(NVARCHAR(MAX), [' + @columna + ']), ' + @q + 'NULL' + @q + ')';

        IF @valoresExpr <> ''
            SET @valoresExpr = @valoresExpr + ' + ' + @q + ', ' + @q + ' + ' + @expr;
        ELSE
            SET @valoresExpr = @expr;

        FETCH NEXT FROM cur INTO @columna, @tipo;
    END
    CLOSE cur; DEALLOCATE cur;

    DECLARE @sql NVARCHAR(MAX) =
        'SELECT ''' + REPLACE(@etiqueta, '''', '''''') + ''' AS Subservicio, ' +
        '''-- INSERT INTO ' + @tabla + ' (' + @columnas + ') VALUES ('' + ' +
        @valoresExpr +
        ' + '');'' AS InsertComentado FROM ' + @tabla +
        CASE WHEN @where IS NOT NULL THEN ' WHERE ' + @where ELSE '' END;

    INSERT INTO #Resultado (Subservicio, InsertComentado)
    EXEC sp_executesql @sql;
END
GO

-- Por cada subservicio: INSERT de dbo.Expediente, una nota recordando el
-- paso de SCOPE_IDENTITY() que falta hacer a mano, y el INSERT de su
-- tabla de subsistema (con @NuevoExpediente como placeholder, ver arriba).
EXEC #GenerarInserts 'Referencias Médicas (226) - Expediente', 'dbo.Expediente', 'clExpediente IN (SELECT clExpediente FROM #Muestra WHERE clSubServicio = 226)';
INSERT INTO #Resultado VALUES ('Referencias Médicas (226) - Nota', '-- DECLARE @NuevoExpediente INT; -- después del INSERT de arriba: SET @NuevoExpediente = SCOPE_IDENTITY();');
EXEC #GenerarInserts 'Referencias Médicas (226) - Subsistema', 'dbo.S2_ReferciasMedicas', 'clExpediente IN (SELECT clExpediente FROM #Muestra WHERE clSubServicio = 226)';

EXEC #GenerarInserts 'Consulta Médica en Consultorio (383) - Expediente', 'dbo.Expediente', 'clExpediente IN (SELECT clExpediente FROM #Muestra WHERE clSubServicio = 383)';
INSERT INTO #Resultado VALUES ('Consulta Médica en Consultorio (383) - Nota', '-- DECLARE @NuevoExpediente INT; -- después del INSERT de arriba: SET @NuevoExpediente = SCOPE_IDENTITY();');
EXEC #GenerarInserts 'Consulta Médica en Consultorio (383) - Subsistema', 'dbo.S2_ReferciasMedicas', 'clExpediente IN (SELECT clExpediente FROM #Muestra WHERE clSubServicio = 383)';

EXEC #GenerarInserts 'Segunda Opinión (376) - Expediente', 'dbo.Expediente', 'clExpediente IN (SELECT clExpediente FROM #Muestra WHERE clSubServicio = 376)';
INSERT INTO #Resultado VALUES ('Segunda Opinión (376) - Nota', '-- DECLARE @NuevoExpediente INT; -- después del INSERT de arriba: SET @NuevoExpediente = SCOPE_IDENTITY(); -- ojo: esta tabla ya no recibe registros desde dic-2021, puede venir vacío.');
EXEC #GenerarInserts 'Segunda Opinión (376) - Subsistema', 'dbo.S2_SegundaOpinion', 'clExpediente IN (SELECT clExpediente FROM #Muestra WHERE clSubServicio = 376)';

EXEC #GenerarInserts 'Check Up (377) - Expediente', 'dbo.Expediente', 'clExpediente IN (SELECT clExpediente FROM #Muestra WHERE clSubServicio = 377)';
INSERT INTO #Resultado VALUES ('Check Up (377) - Nota', '-- DECLARE @NuevoExpediente INT; -- después del INSERT de arriba: SET @NuevoExpediente = SCOPE_IDENTITY();');
EXEC #GenerarInserts 'Check Up (377) - Subsistema', 'dbo.Check_Up', 'clExpediente IN (SELECT clExpediente FROM #Muestra WHERE clSubServicio = 377)';

EXEC #GenerarInserts 'Renta de Equipo Médico (403) - Expediente', 'dbo.Expediente', 'clExpediente IN (SELECT clExpediente FROM #Muestra WHERE clSubServicio = 403)';
INSERT INTO #Resultado VALUES ('Renta de Equipo Médico (403) - Nota', '-- DECLARE @NuevoExpediente INT; -- después del INSERT de arriba: SET @NuevoExpediente = SCOPE_IDENTITY();');
EXEC #GenerarInserts 'Renta de Equipo Médico (403) - Subsistema', 'dbo.s2_RentaEquipoMedico', 'clExpediente IN (SELECT clExpediente FROM #Muestra WHERE clSubServicio = 403)';

EXEC #GenerarInserts 'Enfermería a Domicilio (404) - Expediente', 'dbo.Expediente', 'clExpediente IN (SELECT clExpediente FROM #Muestra WHERE clSubServicio = 404)';
INSERT INTO #Resultado VALUES ('Enfermería a Domicilio (404) - Nota', '-- DECLARE @NuevoExpediente INT; -- después del INSERT de arriba: SET @NuevoExpediente = SCOPE_IDENTITY();');
EXEC #GenerarInserts 'Enfermería a Domicilio (404) - Subsistema', 'dbo.s2_EnfermeriaDomicilio', 'clExpediente IN (SELECT clExpediente FROM #Muestra WHERE clSubServicio = 404)';

EXEC #GenerarInserts 'Plan Visión (420) - Expediente', 'dbo.Expediente', 'clExpediente IN (SELECT clExpediente FROM #Muestra WHERE clSubServicio = 420)';
INSERT INTO #Resultado VALUES ('Plan Visión (420) - Nota', '-- DECLARE @NuevoExpediente INT; -- después del INSERT de arriba: SET @NuevoExpediente = SCOPE_IDENTITY();');
EXEC #GenerarInserts 'Plan Visión (420) - Subsistema', 'dbo.s2_cPuntoVision', 'clExpediente IN (SELECT clExpediente FROM #Muestra WHERE clSubServicio = 420)';

EXEC #GenerarInserts 'Envío de Medicamentos (432) - Expediente', 'dbo.Expediente', 'clExpediente IN (SELECT clExpediente FROM #Muestra WHERE clSubServicio = 432)';
INSERT INTO #Resultado VALUES ('Envío de Medicamentos (432) - Nota', '-- DECLARE @NuevoExpediente INT; -- después del INSERT de arriba: SET @NuevoExpediente = SCOPE_IDENTITY();');
EXEC #GenerarInserts 'Envío de Medicamentos (432) - Subsistema', 'dbo.s2_EnvioDeMedicamentos', 'clExpediente IN (SELECT clExpediente FROM #Muestra WHERE clSubServicio = 432)';

-- Resultado final: Expediente / Nota / Subsistema, agrupados por
-- subservicio (el orden alfabético de "Subservicio" ya deja Expediente
-- antes que Nota antes que Subsistema dentro de cada grupo).
SELECT * FROM #Resultado ORDER BY Subservicio, InsertComentado;

DROP PROCEDURE #GenerarInserts;
DROP TABLE #Muestra;
DROP TABLE #Resultado;
