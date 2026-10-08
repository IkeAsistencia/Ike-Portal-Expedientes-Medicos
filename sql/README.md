# Scripts SQL — Portal Expedientes Médicos

Compatible con **SQL Server 2012 Standard Edition (64-bit)**. Notas de
compatibilidad aplicadas en todos los scripts:

- Sin `CREATE OR ALTER` (llegó hasta SQL Server 2016 SP1) → se usa
  `IF OBJECT_ID(...) IS NOT NULL DROP PROCEDURE ...` + `CREATE PROCEDURE`.
- Sin `STRING_SPLIT` (llegó hasta SQL Server 2016) → se usa un
  Table-Valued Parameter (`dbo.IntList`) para listas de IDs.

## Orden de ejecución (en tu base de desarrollo)

1. `00_create_types.sql` — crea el tipo `dbo.IntList` (requerido por 01 y 03)
2. `01_ST_CP_ObtenerExpedientesSinProveedorMedico.sql` — listado principal (Servicio, titular, teléfono, correo, fecha de asignación de proveedor; regla de 8h de gracia antes de considerarlo "sin proveedor")
3. `02_ST_CP_ObtenerCatalogoServicio.sql` — combo Servicio
4. `03_ST_CP_ObtenerCatalogoCuentas.sql` — catálogo de cuentas
5. `04_ST_CP_RegistrarSeguimiento.sql` — inserta en `dbo.Seguimiento` (tabla ya existente)
6. `05_ST_CP_ObtenerExpedientesSinRespuestaProveedor.sql` — usado por el cron de validación de proveedor
7. `07_ST_CP_ObtenerServicioMedico.sql` — combo Subservicio

`06_ST_CP_ObtenerCatalogoSubServicio_DEPRECADO.sql` **NO se ejecuta**.

**Nomenclatura:** los SPs de este proyecto llevan el prefijo `ST_CP_`. En
una base donde ya existían con el nombre anterior (sin prefijo), después
de crear los nuevos y confirmar que el portal funciona se puede correr
`98_borrar_nombres_anteriores.sql` para quitar los viejos.

## Para quien corre los scripts en QA o producción

**Permisos de quien los corre:** crear los objetos requiere permisos de
DDL en la base (`CREATE PROCEDURE`, `CREATE TYPE` y `ALTER` sobre el
esquema `dbo`, por ejemplo el rol `db_ddladmin`). Solo permiso de
ejecución no alcanza.

**Antes de correrlos**, verifica que existan en esa base las tablas y el SP
que usan los scripts:

```sql
SELECT name, type_desc FROM sys.objects
WHERE name IN ('Expediente', 'ProveedorxExpediente', 'CitaxExpediente', 'Check_Up',
               'cCuenta', 'cServicio', 'cSubServicio', 'cEntFed', 'cMunDel',
               'cEspecialidad', 'cPerfilCheckUp', 'cUsrApp', 'Seguimiento',
               'sp_S2_BuscaCuenta')
ORDER BY name;   -- deben salir los 14
```

**Correr** `00` a `05` y `07`, en ese orden (el `06` no). Se pueden volver
a correr sin problema: el `00` solo crea el tipo si no existe y los demás
borran y recrean su SP.

**Permisos del usuario con el que se conecta la app** (el de `DB_USER`;
solo ejecución, sin acceso directo a tablas):

```sql
GRANT EXECUTE ON dbo.ST_CP_ObtenerExpedientesSinProveedorMedico   TO [usuario_app];
GRANT EXECUTE ON dbo.ST_CP_ObtenerCatalogoServicio                TO [usuario_app];
GRANT EXECUTE ON dbo.ST_CP_ObtenerCatalogoCuentas                 TO [usuario_app];
GRANT EXECUTE ON dbo.ST_CP_RegistrarSeguimiento                   TO [usuario_app];
GRANT EXECUTE ON dbo.ST_CP_ObtenerExpedientesSinRespuestaProveedor TO [usuario_app];
GRANT EXECUTE ON dbo.ST_CP_ObtenerServicioMedico                  TO [usuario_app];
GRANT EXECUTE ON dbo.sp_S2_BuscaCuenta                      TO [usuario_app];
GRANT EXECUTE ON TYPE::dbo.IntList                          TO [usuario_app];  -- listas de cuentas (TVP)
```

**Comprobar** que quedaron creados:

```sql
SELECT name, create_date FROM sys.procedures
WHERE name IN ('ST_CP_ObtenerExpedientesSinProveedorMedico', 'ST_CP_ObtenerCatalogoServicio',
               'ST_CP_ObtenerCatalogoCuentas', 'ST_CP_RegistrarSeguimiento',
               'ST_CP_ObtenerExpedientesSinRespuestaProveedor', 'ST_CP_ObtenerServicioMedico');  -- deben salir los 6
SELECT name FROM sys.table_types WHERE name = 'IntList';                             -- debe salir 1
```

## SPs existentes que NO se incluyen aquí (ya están en tu base)

- **`dbo.sp_S2_BuscaCuenta`** — typeahead de cuentas (Configuración Cuentas).

## Confirmado ✅

| Tema | Resolución |
|---|---|
| STRING_SPLIT no disponible en 2012 | Reemplazado por el TVP `dbo.IntList` |
| Tabla de Seguimiento | `dbo.Seguimiento` (clExpediente, clEstatus=9 fijo, Observaciones, clUsrApp, Fecha). Observaciones es `NVARCHAR(1500)` y lleva el encabezado "Cabina Médica --> nombre" o "Proveedores --> nombre" |
| Estatus del expediente | Solo vive en la app (SQLite local), nunca en SQL Server |
| Significado de ProveedorxExpediente.clEstatus = 3 | "Asignación de Proveedor" (estatus que el sistema core le da al expediente al asignarle proveedor) |

## Sigue abierto ⚠️

| Tema | Qué falta |
|---|---|
| Cuentas permitidas | Confirmar si la lista fija (`CUENTAS_PERMITIDAS` en `.env`) fue solo para el piloto o debe seguir así |
| Datos de envío de correo (SMTP, remitente, destinatario real del proveedor) | Ver `jobs/README.md` y `app/services/email_service.py` — el envío está en modo "simulado" (log) hasta tener esta información |
| LEFT JOIN a `dbo.CitaxExpediente` en el listado principal | Quedó sin columnas usadas tras el cambio de query — confirmar si se puede quitar |
