# SP existente: dbo.sp_GetSubServicios2 (combo Subservicio, en cascada de Servicio)

> ⚠️ **DEPRECADO — ya no se usa.** Confirmado corriendo el SP: recibe
> `@clCuenta` (obligatorio) + `@pclServicio`, y filtra por la cobertura
> de esa cuenta específica. Eso no encaja con el filtro Cuenta de la
> pantalla Expedientes, que permite elegir varias cuentas a la vez.
> Se reemplazó por `dbo.ObtenerServicioMedico`
> (`09_sp_ObtenerServicioMedico.sql`), que ya no depende de la cuenta.
> Este archivo se conserva solo como referencia histórica.

Este SP **ya existe** en tu base y no se crea aquí.

## Uso

Recibe el parámetro `clServicio` (el valor seleccionado en el combo
Servicio) y regresa el catálogo de subservicios correspondiente.

La app lo llama así (`app/repositories/catalogos_repo.py`):

```python
call_procedure("dbo.sp_GetSubServicios2", {"clServicio": cl_servicio})
```

## ⚠️ Sin confirmar

- **Nombre exacto del parámetro de entrada.** Asumimos `@clServicio`
  (es el nombre que nos diste), pero si el SP lo espera con otro nombre
  o en otra posición, hay que ajustar esa única llamada.
- **Columnas de salida.** Asumimos que regresa al menos `clSubServicio`
  y `dsSubservicio` (mismos nombres que usa `dbo.cSubServicio`), igual
  que el catálogo anterior. Si los nombres reales son distintos, el
  único lugar a tocar es `listar_subservicios()` en
  `app/repositories/catalogos_repo.py`.

Para confirmar ambos puntos, corre manualmente en SSMS:

```sql
EXEC dbo.sp_GetSubServicios2 @clServicio = 4;
```

y comparte las columnas que regresa.
