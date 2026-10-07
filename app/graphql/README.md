# GraphQL — Guía rápida (para quien es nuevo en esto)

Se agregó una capa GraphQL **junto al REST que ya existía** (nada se
quitó). Vive en `app/graphql/` y usa exactamente los mismos
repositorios (`app/repositories/`) que el REST — es decir, los mismos
Stored Procedures, la misma base local, la misma lógica de negocio.
Solo cambia **cómo se piden los datos** desde afuera.

**Importante (seguridad):** las mutations que cambian datos
(`actualizarSeguimiento`, `actualizarEstatus`, `agregarCuenta`,
`eliminarCuenta`, `limpiarCuentasConfiguradas`) delegan sus reglas de
rol/flujo de trabajo en `app/services/seguimiento_service.py`,
`app/services/estatus_service.py` y
`accesos_repo.verificar_rol_administrador` — los mismos módulos que usa
el REST (`app/routers/seguimiento.py`,
`app/routers/configuracion_cuentas.py`). Si agregas una mutation nueva
que modifique datos, reutiliza esas reglas en vez de llamar al
repositorio directo: de lo contrario GraphQL vuelve a ser una puerta
trasera que se salta los permisos por perfil.

> **Disponibilidad:** el explorador GraphiQL solo aparece si
> `GRAPHQL_IDE_HABILITADO=true` en tu `.env` (apagado por default; en QA y
> producción debe quedar apagado). La mutation `login` es el login legado
> por usuario de SISE y está apagada por default
> (`LOGIN_LEGADO_HABILITADO=false`): el token se obtiene con el login por
> RFC del REST y sirve igual para GraphQL.

## ¿Qué es GraphQL, en corto?

En vez de tener una URL distinta por cada cosa que quieres hacer (como
en REST: `GET /expedientes`, `GET /catalogos/servicios`, etc.), en
GraphQL hay **una sola URL** (`/graphql`) y tú le mandas un texto
describiendo exactamente qué campos quieres de vuelta. Ventaja: si solo
necesitas el nombre y el estatus de cada expediente, solo pides esos
dos campos — no te regresan los 15.

## Cómo probarlo (sin escribir código)

1. Levanta la API como siempre:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
   o, para probar con datos de ejemplo sin SQL Server:
   ```bash
   python dev_server_datos_prueba.py
   ```
2. Abre en tu navegador: **http://localhost:8000/graphql**
3. Verás un editor visual (GraphiQL) donde puedes escribir consultas y
   ejecutarlas con el botón ▶ — con autocompletado incluido.

## Ejemplos para copiar y pegar en GraphiQL

### 1. Obtener el token (primero que nada)

El token se pide con el login por RFC del REST (el mismo que usa el
portal). Por ejemplo, en PowerShell, con un RFC de prueba que ya tenga
contraseña:

```powershell
$r = Invoke-RestMethod -Method Post -Uri http://localhost:8000/auth/rfc/login `
  -ContentType "application/json" `
  -Body '{"rfc": "CABI000001", "password": "TU_CONTRASEÑA"}'
$r.access_token
```

Copia el valor de `access_token` de la respuesta. En GraphiQL, abre el
panel de abajo "Headers" (o "Request Headers") y pon:

```json
{ "Authorization": "Bearer PEGA_AQUI_EL_TOKEN" }
```

A partir de aquí, todas las demás consultas necesitan ese header (igual
que con el REST).

### 2. Listado de Expedientes, con filtros

```graphql
query {
  expedientes(filtro: { clServicio: 4, clExpediente: 1001 }) {
    expediente
    cuenta
    tipoServicio
    tipoSubservicio
    nombrePaciente
    fechaCita
    estatus
  }
}
```

Prueba quitando o agregando campos dentro de las llaves `{ }` — ese es
el punto central de GraphQL: tú decides qué campos regresan.

### 3. Catálogos (Servicio y Subservicio en cascada)

```graphql
query {
  servicios { clave descripcion }
  subservicios(clServicio: 4) { clave descripcion }
}
```

(Sí, puedes pedir varias cosas en una sola consulta.)

### 4. Registrar un seguimiento

```graphql
mutation {
  actualizarSeguimiento(datos: { clExpediente: 1001, comentario: "Se contactó al proveedor." }) {
    ok
    mensaje
  }
}
```

### 5. Cambiar el estatus de un expediente

```graphql
mutation {
  actualizarEstatus(datos: { clExpediente: 1001, estatus: SEGUIMIENTO_PROVEEDOR }) {
    ok
  }
}
```

### 6. Enviar correo a proveedores

```graphql
mutation {
  enviarCorreoProveedores(datos: { expedientes: [1001, 1002] }) {
    enviados
    expedientes
  }
}
```

### 7. Configuración de Cuentas

```graphql
mutation { agregarCuenta(datos: { clCuenta: 2819, nombre: "Cuenta Demo" }) { ok } }

query { cuentasConfiguradas { clCuenta nombre } }

mutation { eliminarCuenta(clCuenta: 2819) { ok } }

mutation { limpiarCuentasConfiguradas { ok mensaje } }
```

## Diferencias a tener en cuenta

- **Todo pasa por POST a `/graphql`**, nunca hay un GET a una URL
  distinta por cada operación (salvo GraphiQL mismo, que es GET).
- **El código de HTTP casi siempre es 200**, incluso si hubo un error de
  negocio (credenciales inválidas, sesión expirada, etc.) — el error va
  dentro de la respuesta, en un arreglo `"errors"`. Esto es normal en
  GraphQL, no es un bug.
- **Los nombres de campo se ven en camelCase** (`tipoServicio`,
  `fechaCita`) aunque en Python están en snake_case
  (`tipo_servicio`) — Strawberry hace esa conversión automáticamente.
- Las pruebas automatizadas de esta capa están en `tests/test_graphql.py`
  (correr con `pytest tests/test_graphql.py -v`), en paralelo a las del
  REST en `tests/test_smoke.py`.

## Qué NO cambió

- Los Stored Procedures son los mismos (`sql/`).
- El frontend (`frontend/index.html`) **sigue usando el REST**, tal
  cual — no se tocó. Si más adelante quieren que el frontend use
  GraphQL en vez de REST, es un cambio aparte (avísenme cuando lo
  decidan).
- El cron (`jobs/validar_estatus_proveedor.py`) también sigue usando
  los repositorios directamente, sin pasar por REST ni GraphQL — no
  necesita cambiar.
