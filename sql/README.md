# Scripts SQL — Portal Expedientes Médicos

Compatible con **SQL Server 2012 Standard Edition (64-bit)**. Notas de
compatibilidad aplicadas en todos los scripts:

- Sin `CREATE OR ALTER` (llegó hasta SQL Server 2016 SP1) → se usa
  `IF OBJECT_ID(...) IS NOT NULL DROP PROCEDURE ...` + `CREATE PROCEDURE`.
- Sin `STRING_SPLIT` (llegó hasta SQL Server 2016) → se usa un
  Table-Valued Parameter (`dbo.IntList`) para listas de IDs.

## Orden de ejecución (en tu base de desarrollo)

1. `00_create_types.sql` — crea el tipo `dbo.IntList` (requerido por 01 y 03)
2. `01_sp_ObtenerExpedientesSinProveedorMedico.sql` — listado principal (Servicio, titular, teléfono, correo, fecha de asignación de proveedor; regla de 8h de gracia antes de considerarlo "sin proveedor")
3. `02_sp_ObtenerCatalogoServicio.sql` — combo Servicio
4. `03_sp_ObtenerCatalogoCuentas.sql` — catálogo de cuentas
5. `04_sp_RegistrarSeguimiento.sql` — inserta en `dbo.Seguimiento` (tabla ya existente)
6. `05_sp_ObtenerExpedientesSinRespuestaProveedor.sql` — usado por el cron de validación de proveedor
7. `07_sp_ObtenerServicioMedico.sql` — combo Subservicio

`06_sp_ObtenerCatalogoSubServicio_DEPRECADO.sql` **NO se ejecuta**.

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
