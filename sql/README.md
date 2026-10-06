# Scripts SQL — Portal Expedientes Médicos

Compatible con **SQL Server 2012 Standard Edition (64-bit)**. Notas de
compatibilidad aplicadas en todos los scripts:

- Sin `CREATE OR ALTER` (llegó hasta SQL Server 2016 SP1) → se usa
  `IF OBJECT_ID(...) IS NOT NULL DROP PROCEDURE ...` + `CREATE PROCEDURE`.
- Sin `STRING_SPLIT` (llegó hasta SQL Server 2016) → se usa un
  Table-Valued Parameter (`dbo.IntList`) para listas de IDs.

## Orden de ejecución (en tu base de desarrollo)

1. `00_create_types.sql` — crea el tipo `dbo.IntList` (requerido por 01/02/03/05)
2. `01_sp_ObtenerExpedientesSinProveedorMedico.sql` — listado principal (query actualizado: Servicio, titular, teléfono, correo, fecha de asignación de proveedor; regla de 8h de gracia antes de considerarlo "sin proveedor")
3. `02_sp_ObtenerCatalogoServicio.sql` — combo Servicio
4. `03_sp_ObtenerCatalogoCuentas.sql`
5. `04_sp_RegistrarSeguimiento.sql` — inserta en `dbo.Seguimiento` (tabla ya existente)
6. `05_sp_ObtenerExpedientesSinRespuestaProveedor.sql` — usado por el cron de validación de proveedor
7. `07_sp_ObtenerServicioMedico.sql` — combo Subservicio (reemplaza al SP legado `dbo.sp_GetSubServicios2`, ver abajo)

`06_sp_ObtenerCatalogoSubServicio_DEPRECADO.sql` **NO se ejecuta** —
se conserva solo de referencia.

## SPs existentes que NO se incluyen aquí (ya están en tu base)

- **`dbo.sp_S2_BuscaCuenta`** — typeahead de cuentas (Configuración Cuentas).
- **`dbo.sp_EncriptDesEncriptPassword`** — login. Columnas de salida
  usadas: `clUsrApp`, `Nombre`, `Activo` (ver `app/repositories/auth_repo.py`).
  El parámetro `@pContraseña` es `varchar(10)`, así que la API rechaza
  explícitamente cualquier contraseña de más de 10 caracteres (ver
  `app/schemas/auth.py`) en vez de dejar que SQL Server la trunque en
  silencio.
- **`dbo.sp_GetSubServicios2`** — ⚠️ **YA NO SE USA.** Requiere
  `@clCuenta` + `@pclServicio` (filtra por cobertura de una sola
  cuenta), lo cual no encaja con el filtro Cuenta de la pantalla
  Expedientes (permite varias a la vez). Se reemplazó por
  `dbo.ObtenerServicioMedico` (`07_sp_ObtenerServicioMedico.sql`), que sí
  se crea en esta base.

## Resuelto en esta ronda ✅

| # | Tema | Resolución |
|---|---|---|
| 1 | STRING_SPLIT no disponible en 2012 | Reemplazado por TVP dbo.IntList en los SPs de lectura |
| 2 | Semáforo de cita | Confirmado: menor a 24h Verde, 24-48h Naranja, mayor a 48h Rojo (aplicado ahora al correo del cron, ver más abajo) |
| 4 | Tabla de Seguimiento | Confirmada: dbo.Seguimiento (clExpediente, clEstatus=9 fijo, Observaciones, clUsrApp, Fecha) |
| 5 | Estatus del expediente | Confirmado: solo vive en la app (SQLite local), nunca en SQL Server |
| — | Columnas de salida de sp_EncriptDesEncriptPassword | Confirmado: clUsrApp, Nombre, Activo |
| — | Significado de ProveedorxExpediente.clEstatus = 3 | Confirmado: "Asignación de Proveedor" (estatus que el sistema core le da al expediente al asignarle proveedor) |
| — | Límite real de contraseña | Confirmado 10 caracteres (`@pContraseña varchar(10)`) — la API lo rechaza explícito en vez de truncar |
| — | Host del cliente en el login | No se puede obtener el hostname real del equipo del usuario desde un API web, solo su IP — se manda el hostname del *servidor* donde corre la API |
| — | Parámetro y columnas de sp_GetSubServicios2 | Ya no aplica — ese SP se dejó de usar (ver arriba) |

## Sigue abierto ⚠️

| # | Tema | Qué falta |
|---|---|---|
| 3 | Subservicios/Cuentas permitidas | Confirmar si la lista fija fue solo temporal para el piloto o debe seguir así (ya no aplica al combo Subservicio, que ahora es dinámico vía `dbo.ObtenerServicioMedico`) |
| — | Datos de envío de correo (SMTP, remitente, plantilla, destinatario real del proveedor) | Ver `jobs/README.md` y `app/services/email_service.py` — el envío está en modo "simulado" (log) hasta tener esta información |
| — | LEFT JOIN a dbo.CitaxExpediente en el listado principal | Quedó sin columnas usadas tras el cambio de query — confirmar si se puede quitar |
