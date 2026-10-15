-- =====================================================================
-- SOLO PARA DESARROLLO/PRUEBAS -- no inserta ni modifica nada por sí
-- solo. Compatible con SQL Server 2012 (sin STRING_AGG, que es de 2017+).
--
-- Idea: tomar 3 expedientes AL AZAR de dbo.Expediente por cada uno de los
-- 8 subservicios que maneja la pantalla Expedientes, y a partir de ESOS
-- mismos expedientes armar (pero NO ejecutar) el INSERT que haría falta
-- para "sembrarlos" también en la tabla de subsistema que le corresponda a
-- cada subservicio (mapeo igual al de
-- sql/01_ST_CP_ObtenerExpedientesSinProveedorMedico.sql):
--   226 "Referencias Médicas"            -> dbo.S2_ReferciasMedicas
--   383 "Consulta Médica en Consultorio" -> dbo.S2_ReferciasMedicas (misma tabla que 226)
--   376 "Segunda Opinión"                -> dbo.S2_SegundaOpinion
--   377 "Check Up"                       -> dbo.Check_Up
--   403 "Renta de Equipo Médico"         -> dbo.s2_RentaEquipoMedico
--   404 "Enfermería a Domicilio"         -> dbo.s2_EnfermeriaDomicilio
--   420 "Plan Visión"                    -> dbo.s2_cPuntoVision
--   432 "Envío de Medicamentos"          -> dbo.s2_EnvioDeMedicamentos
--
-- Cómo usarlo:
--   1) Correr el script completo (es una sola conexión/sesión -- los
--      resultados quedan todos en un solo SELECT final al terminar).
--   2) Revisar la columna "InsertComentado": cada fila trae el texto
--      "-- INSERT INTO tabla (cols) VALUES (...);" ya armado con los
--      valores reales de ese expediente, pero comentado (con "--" al
--      inicio) -- a propósito NO se ejecuta ningún INSERT aquí.
--   3) Copiar las líneas que se vayan a usar, quitarles el "--", y
--      revisarlas a mano antes de correrlas en el ambiente de
--      QA/local que se esté sembrando (sobre todo si clExpediente debe
--      ser un número nuevo en vez del mismo que trae la fila original --
--      si se deja igual y la tabla destino ya tiene ese expediente, el
--      INSERT va a tronar por llave duplicada).
--   4) dbo.Expediente normalmente tiene clExpediente como IDENTITY -- si
--      se va a insertar con el mismo número, hace falta
--      "SET IDENTITY_INSERT dbo.Expediente ON" antes del INSERT y
--      "...OFF" después (no lo hace este script).
--
-- Si un expediente de la muestra tiene más de una captura en su tabla de
-- subsistema (documentado como posible en el SP real), van a salir varios
-- INSERT comentados para ese mismo expediente -- es normal, quédate solo
-- con el que corresponda al revisar.
-- =====================================================================
SET NOCOUNT ON;

IF OBJECT_ID('tempdb..#Muestra') IS NOT NULL DROP TABLE #Muestra;
CREATE TABLE #Muestra (clSubServicio INT, clExpediente INT);

;WITH candidatos AS (
    SELECT clExpediente, clSubServicio,
           ROW_NUMBER() OVER (PARTITION BY clSubServicio ORDER BY NEWID()) AS rn
    FROM dbo.Expediente
    WHERE clSubServicio IN (226, 376, 377, 383, 403, 404, 420, 432)
)
INSERT INTO #Muestra (clSubServicio, clExpediente)
SELECT clSubServicio, clExpediente
FROM candidatos
WHERE rn <= 3;

IF OBJECT_ID('tempdb..#Resultado') IS NOT NULL DROP TABLE #Resultado;
CREATE TABLE #Resultado (Subservicio NVARCHAR(100), InsertComentado NVARCHAR(MAX));
GO  -- CREATE PROCEDURE debe ser la única sentencia del batch (SQL Server < 2016 SP1)

-- Procedimiento TEMPORAL (vive solo en esta sesión, se borra solo al
-- desconectar o al final de este script): arma, para cualquier tabla, el
-- texto comentado de un INSERT por cada fila que cumpla @where, usando
-- sys.columns/sys.types para no tener que listar las columnas a mano (así
-- sirve igual para dbo.Expediente que para cualquiera de las 7 tablas de
-- subsistema). NUNCA ejecuta el INSERT que arma -- solo lo arma como texto.
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
        ORDER BY c.column_id;

    OPEN cur;
    FETCH NEXT FROM cur INTO @columna, @tipo;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        IF @columnas <> '' SET @columnas = @columnas + ', ';
        SET @columnas = @columnas + '[' + @columna + ']';

        IF @tipo IN ('char','varchar','nchar','nvarchar','text','ntext','xml','uniqueidentifier',
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

-- Un par de llamadas por subservicio: el INSERT para dbo.Expediente y el
-- de su tabla de subsistema, con los 3 expedientes que le tocaron en #Muestra.
EXEC #GenerarInserts 'Referencias Médicas (226) - Expediente', 'dbo.Expediente', 'clExpediente IN (SELECT clExpediente FROM #Muestra WHERE clSubServicio = 226)';
EXEC #GenerarInserts 'Referencias Médicas (226) - Subsistema', 'dbo.S2_ReferciasMedicas', 'clExpediente IN (SELECT clExpediente FROM #Muestra WHERE clSubServicio = 226)';

EXEC #GenerarInserts 'Consulta Médica en Consultorio (383) - Expediente', 'dbo.Expediente', 'clExpediente IN (SELECT clExpediente FROM #Muestra WHERE clSubServicio = 383)';
EXEC #GenerarInserts 'Consulta Médica en Consultorio (383) - Subsistema', 'dbo.S2_ReferciasMedicas', 'clExpediente IN (SELECT clExpediente FROM #Muestra WHERE clSubServicio = 383)';

EXEC #GenerarInserts 'Segunda Opinión (376) - Expediente', 'dbo.Expediente', 'clExpediente IN (SELECT clExpediente FROM #Muestra WHERE clSubServicio = 376)';
EXEC #GenerarInserts 'Segunda Opinión (376) - Subsistema', 'dbo.S2_SegundaOpinion', 'clExpediente IN (SELECT clExpediente FROM #Muestra WHERE clSubServicio = 376)';

EXEC #GenerarInserts 'Check Up (377) - Expediente', 'dbo.Expediente', 'clExpediente IN (SELECT clExpediente FROM #Muestra WHERE clSubServicio = 377)';
EXEC #GenerarInserts 'Check Up (377) - Subsistema', 'dbo.Check_Up', 'clExpediente IN (SELECT clExpediente FROM #Muestra WHERE clSubServicio = 377)';

EXEC #GenerarInserts 'Renta de Equipo Médico (403) - Expediente', 'dbo.Expediente', 'clExpediente IN (SELECT clExpediente FROM #Muestra WHERE clSubServicio = 403)';
EXEC #GenerarInserts 'Renta de Equipo Médico (403) - Subsistema', 'dbo.s2_RentaEquipoMedico', 'clExpediente IN (SELECT clExpediente FROM #Muestra WHERE clSubServicio = 403)';

EXEC #GenerarInserts 'Enfermería a Domicilio (404) - Expediente', 'dbo.Expediente', 'clExpediente IN (SELECT clExpediente FROM #Muestra WHERE clSubServicio = 404)';
EXEC #GenerarInserts 'Enfermería a Domicilio (404) - Subsistema', 'dbo.s2_EnfermeriaDomicilio', 'clExpediente IN (SELECT clExpediente FROM #Muestra WHERE clSubServicio = 404)';

EXEC #GenerarInserts 'Plan Visión (420) - Expediente', 'dbo.Expediente', 'clExpediente IN (SELECT clExpediente FROM #Muestra WHERE clSubServicio = 420)';
EXEC #GenerarInserts 'Plan Visión (420) - Subsistema', 'dbo.s2_cPuntoVision', 'clExpediente IN (SELECT clExpediente FROM #Muestra WHERE clSubServicio = 420)';

EXEC #GenerarInserts 'Envío de Medicamentos (432) - Expediente', 'dbo.Expediente', 'clExpediente IN (SELECT clExpediente FROM #Muestra WHERE clSubServicio = 432)';
EXEC #GenerarInserts 'Envío de Medicamentos (432) - Subsistema', 'dbo.s2_EnvioDeMedicamentos', 'clExpediente IN (SELECT clExpediente FROM #Muestra WHERE clSubServicio = 432)';

-- Resultado final: una fila por INSERT comentado, agrupado por subservicio.
SELECT * FROM #Resultado ORDER BY Subservicio, InsertComentado;

DROP PROCEDURE #GenerarInserts;
DROP TABLE #Muestra;
DROP TABLE #Resultado;
