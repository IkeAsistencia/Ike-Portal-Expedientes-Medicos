# Scripts SQL — API Expedientes Médicos

Compatible con **SQL Server 2012 Standard Edition (64-bit)**. Notas de
compatibilidad aplicadas en todos los scripts:

- Sin `CREATE OR ALTER` (llegó hasta SQL Server 2016 SP1) → se usa
  `IF OBJECT_ID(...) IS NOT NULL DROP PROCEDURE ...` + `CREATE PROCEDURE`.
- Sin `STRING_SPLIT` (llegó hasta SQL Server 2016) → se usa un
  Table-Valued Parameter (`dbo.IntList`) para listas de IDs.

## Orden de ejecución (en tu base de desarrollo)

1. `00_create_types.sql` — crea el tipo `dbo.IntList` (requerido por 01/02/03/06)
2. `01_sp_ObtenerExpedientesSinProveedorMedico.sql` — listado principal (query actualizado: Servicio, titular, teléfono, correo, fecha de asignación de proveedor)
3. `02_sp_ObtenerCatalogoServicio.sql` — combo Servicio
4. `03_sp_ObtenerCatalogoCuentas.sql`
5. `04_sp_RegistrarSeguimiento.sql` — inserta en `dbo.Seguimiento` (tabla ya existente)
6. `06_sp_ObtenerExpedientesSinRespuestaProveedor.sql` — usado por el cron de validación de proveedor
7. `09_sp_ObtenerServicioMedico.sql` — combo Subservicio (reemplaza al SP legado `dbo.sp_GetSubServicios2`, ver abajo)

`07_sp_ObtenerCatalogoSubServicio_DEPRECADO.sql` **NO se ejecuta** —
se conserva solo de referencia.

## SPs existentes que NO se incluyen aquí (ya están en tu base)

- **`dbo.sp_S2_BuscaCuenta`** — typeahead de cuentas (Configuración Cuentas).
- **`dbo.sp_EncriptDesEncriptPassword`** — login. Ver
  `05_login_sp_EncriptDesEncriptPassword_NOTAS.md` (columnas de salida
  ya confirmadas: clUsrApp, Nombre, Activo; sigue pendiente el límite
  real de la contraseña).
- **`dbo.sp_GetSubServicios2`** — ⚠️ **YA NO SE USA.** Requiere
  `@clCuenta` + `@pclServicio` (filtra por cobertura de una sola
  cuenta), lo cual no encaja con el filtro Cuenta de la pantalla
  Expedientes (permite varias a la vez). Se reemplazó por
  `dbo.ObtenerServicioMedico` (`09_sp_ObtenerServicioMedico.sql`), que sí
  se crea en esta base. Ver `08_subservicios_sp_GetSubServicios2_NOTAS.md`
  para el detalle de por qué se dejó de usar.

## Resuelto en esta ronda ✅

| # | Tema | Resolución |
|---|---|---|
| 1 | STRING_SPLIT no disponible en 2012 | Reemplazado por TVP dbo.IntList en los SPs de lectura |
| 2 | Semáforo de cita | Confirmado: menor a 24h Verde, 24-48h Naranja, mayor a 48h Rojo (aplicado ahora al correo del cron, ver más abajo) |
| 4 | Tabla de Seguimiento | Confirmada: dbo.Seguimiento (clExpediente, clEstatus=9 fijo, Observaciones, clUsrApp, Fecha) |
| 5 | Estatus del expediente | Confirmado: solo vive en la app (SQLite local), nunca en SQL Server |
| — | Columnas de salida de sp_EncriptDesEncriptPassword | Confirmado: clUsrApp, Nombre, Activo |
| — | Significado de ProveedorxExpediente.clEstatus = 3 | Confirmado: "Asignación de Proveedor" (estatus que el sistema core le da al expediente al asignarle proveedor) |

## Sigue abierto ⚠️

| # | Tema | Qué falta |
|---|---|---|
| 3 | Subservicios/Cuentas permitidas | Confirmar si la lista fija fue solo temporal para el piloto o debe seguir así (ya no aplica al combo Subservicio, que ahora es dinámico vía sp_GetSubServicios2) |
| — | Límite real de contraseña (10 o 20 caracteres) | Ver 05_login_sp_EncriptDesEncriptPassword_NOTAS.md |
| — | Cómo obtener el host real del equipo del usuario | Ver 05_login_sp_EncriptDesEncriptPassword_NOTAS.md |
| — | Parámetro y columnas de sp_GetSubServicios2 | Ver 08_subservicios_sp_GetSubServicios2_NOTAS.md |
| — | Datos de envío de correo (SMTP, remitente, plantilla, destinatario real del proveedor) | Ver `jobs/README.md` y `app/services/email_service.py` — el envío está en modo "simulado" (log) hasta tener esta información |
| — | LEFT JOIN a dbo.CitaxExpediente en el listado principal | Quedó sin columnas usadas tras el cambio de query — confirmar si se puede quitar |
