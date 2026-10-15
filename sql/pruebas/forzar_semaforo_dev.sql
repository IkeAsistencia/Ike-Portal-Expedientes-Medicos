-- =====================================================================
-- SOLO PARA DESARROLLO/PRUEBAS -- nunca correr en producción.
--
-- Toma hasta 4 expedientes abiertos (clEstatus=0) de cada subservicio
-- que maneja la pantalla Expedientes y les mueve FechaApertura hacia
-- atrás, uno para cada color del semáforo (verde/amarillo/naranja/rojo),
-- según el grupo al que pertenezca (ver app/services/semaforo_service.py):
--   Primer contacto  (226/377/420/432): amarillo 6h, naranja 12h, rojo 24h
--   Segundo contacto (383/376/404/403): amarillo 12h, naranja 48h, rojo 72h
--
-- Si un subservicio no tiene 4 expedientes abiertos ahorita, simplemente
-- se ajustan los que haya (puede terminar sin probar algún color para
-- ese subservicio en particular).
--
-- OJO: esto SOBRESCRIBE la FechaApertura real de esos expedientes -- no
-- hay forma de "deshacerlo" automáticamente. Anota los clExpediente que
-- toque (los imprime el SELECT final) si te importa su fecha original.
-- =====================================================================
DECLARE @ahora DATETIME = GETDATE();

;WITH candidatos AS (
    SELECT clExpediente, clSubServicio,
           ROW_NUMBER() OVER (PARTITION BY clSubServicio ORDER BY clExpediente DESC) AS rn
    FROM dbo.Expediente
    WHERE clEstatus = 0
      AND clSubServicio IN (226, 376, 377, 383, 403, 404, 420, 432)
),
primer_contacto AS (   -- 226/377/420/432: amarillo 6h, naranja 12h, rojo 24h
    SELECT clExpediente,
        CASE rn
            WHEN 1 THEN 1    -- verde  (<6h)
            WHEN 2 THEN 7    -- amarillo (6-12h)
            WHEN 3 THEN 13   -- naranja (12-24h)
            WHEN 4 THEN 25   -- rojo    (>24h)
        END AS horas_atras
    FROM candidatos
    WHERE clSubServicio IN (226, 377, 420, 432) AND rn <= 4
),
segundo_contacto AS (   -- 383/376/404/403: amarillo 12h, naranja 48h, rojo 72h
    SELECT clExpediente,
        CASE rn
            WHEN 1 THEN 1    -- verde  (<12h)
            WHEN 2 THEN 13   -- amarillo (12-48h)
            WHEN 3 THEN 49   -- naranja (48-72h)
            WHEN 4 THEN 73   -- rojo    (>72h)
        END AS horas_atras
    FROM candidatos
    WHERE clSubServicio IN (383, 376, 404, 403) AND rn <= 4
),
todos AS (
    SELECT * FROM primer_contacto
    UNION ALL
    SELECT * FROM segundo_contacto
)
UPDATE E
    SET E.FechaApertura = DATEADD(HOUR, -t.horas_atras, @ahora)
FROM dbo.Expediente E
INNER JOIN todos t ON t.clExpediente = E.clExpediente;

-- Verificación: qué quedó y cuántas horas lleva cada uno.
SELECT
    E.clExpediente,
    E.clSubServicio,
    SS.dsSubservicio,
    E.FechaApertura,
    CAST(DATEDIFF(MINUTE, E.FechaApertura, GETDATE()) / 60.0 AS DECIMAL(12,1)) AS horas_transcurridas   -- algunos expedientes abiertos llevan miles de horas
FROM dbo.Expediente E
INNER JOIN dbo.cSubServicio SS ON SS.clSubServicio = E.clSubServicio
WHERE E.clEstatus = 0
  AND E.clSubServicio IN (226, 376, 377, 383, 403, 404, 420, 432)
ORDER BY E.clSubServicio, E.FechaApertura DESC;

-- =====================================================================
-- Para probar el caso "En Espera de Respuesta" (ya escalado a proveedor,
-- verde <=120min / naranja 120-180min / rojo >180min): ese dato NO vive
-- aquí en SQL Server, vive en la base local SQLite del portal
-- (data/app_local.db, tabla estatus_expediente). Ejemplo:
--
--   UPDATE estatus_expediente
--   SET fecha_cambio = datetime('now', '-150 minutes')
--   WHERE cl_expediente = 18108235;
-- =====================================================================
