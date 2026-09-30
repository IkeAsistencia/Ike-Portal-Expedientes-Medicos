# SP existente: dbo.sp_EncriptDesEncriptPassword (Login)

Este SP **ya existe** en tu base y no se crea aquí.

## Firma proporcionada

```sql
[dbo].[sp_EncriptDesEncriptPassword]
    @pUsuario      char(15),
    @CreateSession bit = 0,
    @pHost         varchar(20),
    @pContraseña   varchar(10),
    @ip            varchar(20) = ''
```

## Columnas de salida usadas ✅ CONFIRMADO

El SP regresa varias columnas, pero la app solo usa estas 3:

| Columna | Uso |
|---|---|
| `clUsrApp` | Se guarda en cada registro de `dbo.Seguimiento` (bitácora) |
| `Nombre` | Se muestra en la app una vez que el usuario inició sesión |
| `Activo` | Si es falso, se bloquea el acceso |

Si `Activo` es falso, la API responde con el mensaje fijo:
> "Usuario sin permisos o inactivo, valide con el Supervisor"

Esto está centralizado en `app/repositories/auth_repo.py` (constantes
`COLUMNA_CL_USR_APP`, `COLUMNA_NOMBRE`, `COLUMNA_ACTIVO` y
`MENSAJE_USUARIO_INACTIVO`), por si el nombre exacto de alguna columna
cambiara más adelante.

## ⚠️ Sigue sin confirmar: límite real de la contraseña

La pantalla de login pide un campo PASSWORD de **máximo 20 posiciones**,
pero el parámetro `@pContraseña` del SP es `varchar(10)`. Si un usuario
tiene una contraseña de más de 10 caracteres, SQL Server la truncaría
silenciosamente al convertir el parámetro, lo cual podría producir un
resultado incorrecto. **El API por ahora rechaza explícitamente**
cualquier contraseña de más de 10 caracteres con un mensaje claro, en
vez de truncar en silencio — avísenme cuál de los dos límites (10 o 20)
es el correcto para ajustarlo.

## Parámetros armados por la app (`auth_repo.py`)

| Parámetro | Origen |
|---|---|
| `@pUsuario` | Campo USUARIO del login (máx. 15) |
| `@CreateSession` | Fijo en `0`, según indicaste |
| `@pHost` | **Supuesto**: nombre de host del *servidor* donde corre la API (`socket.gethostname()`), NO del equipo del usuario — un API web no puede obtener el nombre de la PC del usuario que la consulta, solo su IP. Si necesitas el hostname real del cliente, hay que capturarlo desde el navegador (JavaScript) y mandarlo en el request; avísame si quieres que lo agregue así. |
| `@pContraseña` | Campo PASSWORD del login (máx. 10, ver límite arriba) |
| `@ip` | IP del cliente HTTP (`request.client.host`, o `X-Forwarded-For` si hay proxy/balanceador de por medio) |
