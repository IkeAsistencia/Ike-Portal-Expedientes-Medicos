# Portal Expedientes Médicos (Python + FastAPI + SQL Server)

Backend REST del sistema de gestión de Expedientes Médicos, sucesor formal
del prototipo HTML. Lee y escribe contra SQL Server **exclusivamente por
Stored Procedures**. Compatible con **SQL Server 2012 Standard Edition**.

## Arquitectura

```
app/
├── main.py                    # arranque de FastAPI
├── config.py                  # settings desde variables de entorno (.env)
├── core/
│   └── security.py             # JWT propio de la app + dependencia de login
├── db/
│   ├── connection.py           # conexión a SQL Server (pyodbc) + ejecución de SPs (soporta TVP)
│   └── local_store.py          # SQLite local (estatus, config. cuentas, alertas de proveedor enviadas)
├── services/
│   └── email_service.py        # envío de correo (real si hay SMTP en .env, simulado/log si no)
├── schemas/                    # modelos Pydantic (request/response)
├── repositories/                # una función por cada operación de datos
├── routers/                     # endpoints HTTP (FastAPI routers)
└── graphql/                     # capa GraphQL (mismo backend, expuesto en /graphql — ver su propio README.md)

sql/                             # scripts T-SQL de los Stored Procedures
tests/                           # pruebas automatizadas (no requieren SQL Server real)
jobs/
├── validar_estatus_proveedor.py # cron: alerta expedientes sin respuesta del proveedor (8h/24h)
└── README.md                    # cómo programarlo con el Programador de tareas de Windows
frontend/
└── index.html                   # frontend funcional (HTML+JS puro) que consume la API
dev_server_datos_prueba.py       # API con datos de ejemplo, para probar el frontend sin SQL Server
```

## 🔒 Sobre las credenciales de la base de datos

- Ahora se soportan **dos modos** (`DB_AUTH_MODE` en `.env`):
  - `windows` — Autenticación integrada de Windows, sin usuario/contraseña en ningún archivo.
  - `sql` — Autenticación de SQL Server. **Tú llenas `DB_USER`/`DB_PASSWORD`
    directamente en tu `.env` local**, que nunca se comparte por chat ni
    se sube a control de versiones (ver `.gitignore`). Coloca ese `.env`
    en el ambiente restringido que definas, con permisos de lectura
    limitados a la cuenta que ejecuta el proceso.

## Requisitos

- Python 3.11+
- [Microsoft ODBC Driver 17 (o 18) para SQL Server](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server)
- Acceso de red a SQL Server 2012 de desarrollo, con permisos de
  `EXECUTE` sobre los Stored Procedures usados.

## Instalación

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac

pip install -r requirements.txt
copy .env.example .env        # Windows (o: cp .env.example .env)
```

Edita `.env` con los datos reales de tu ambiente de desarrollo (servidor,
base, y si usas `DB_AUTH_MODE=sql`, tu usuario/contraseña). Genera también
tu propio `JWT_SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Antes de arrancar: correr los scripts SQL

Sigue el orden indicado en `sql/README.md` (empieza por
`00_create_types.sql`, requerido por los demás).

## Probar visualmente, SIN necesitar SQL Server todavía

Antes de tener la base de datos real conectada, puedes ver la interfaz
funcionando de punta a punta (login incluido) con datos de ejemplo:

```bash
python dev_server_datos_prueba.py
```

Esto levanta la API en `http://localhost:8000` con datos inventados (no
toca SQL Server para nada). Luego abre `frontend/index.html` directamente
en tu navegador (doble clic) e inicia sesión con:

- Usuario: `ijimenez`
- Contraseña: `clave123`

Así puedes confirmar que la parte visual y los flujos (filtros, KPIs,
Seguimiento, Configuración Cuentas) funcionan bien, **antes** de meter la
variable de si la conexión real a SQL Server funciona o no.

## Frontend real (contra tu base de desarrollo)

Una vez que tengas los scripts SQL corridos y tu `.env` configurado:

```bash
uvicorn app.main:app --reload --port 8000
```

y abre `frontend/index.html` igual, con tu usuario real. El frontend
detecta automáticamente `http://localhost:8000`; si tu API corre en otra
URL/puerto, usa el enlace "Configuración de conexión" en la pantalla de
login para apuntarlo a la URL correcta.

El frontend es un único archivo HTML autocontenido (sin frameworks ni
build step) — puedes abrirlo directamente o servirlo con cualquier
servidor estático (`python -m http.server`, Live Server de VS Code, etc.).
CORS ya está habilitado en el backend (`app/main.py`) para que esto
funcione sin configuración adicional en desarrollo.

Documentación interactiva del API (Swagger) en `http://localhost:8000/docs`.

## Ejecutar las pruebas (sin necesitar SQL Server)

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

## Flujo de autenticación

1. `POST /auth/login` con `{"usuario": "...", "password": "..."}` (según
   la pantalla de acceso: usuario máx. 15, password máx. 20 — el SP legado
   solo soporta 10 caracteres de contraseña, ver `LARGO_MAXIMO_PASSWORD_SP`
   en `app/repositories/auth_repo.py`).
2. Internamente se llama a `dbo.sp_EncriptDesEncriptPassword` (SP ya
   existente en tu base) para validar credenciales y obtener `clUsrApp`.
3. Si el login es correcto, la API emite su **propio token (JWT)**, ya
   que `@CreateSession` se manda fijo en `0`.
4. **Todos los demás endpoints exigen ese token** (`Authorization: Bearer <token>`).
5. En `/seguimiento/actualizar`, el `clUsrApp` que se guarda en
   `dbo.Seguimiento` se toma del token — nunca de un campo libre del
   formulario.

## Endpoints

| Método | Ruta | Auth | Pantalla / uso | Origen del dato |
|---|---|---|---|---|
| POST | `/auth/login` | No | Pantalla de acceso | `dbo.sp_EncriptDesEncriptPassword` (SQL Server, ya existente) |
| GET | `/expedientes` | Sí | Expedientes: tabla + filtros (incluye Servicio/Subservicio) | `dbo.ObtenerExpedientesSinProveedorMedico` + estatus local |
| POST | `/expedientes/enviar-correo-proveedores` | Sí | Botón "Enviar correo a proveedores" | `app/services/email_service.py` (simulado hasta configurar SMTP) |
| GET | `/catalogos/servicios` | Sí | Combo Servicio | `dbo.ObtenerCatalogoServicio` |
| GET | `/catalogos/subservicios?cl_servicio=` | Sí | Combo Subservicio (cascada de Servicio) | `dbo.sp_GetSubServicios2` (ya existente) |
| GET | `/catalogos/cuentas` | Sí | Combo Cuenta | `dbo.ObtenerCatalogoCuentas` |
| GET | `/catalogos/cuentas/buscar?texto=` | Sí | Configuración Cuentas (typeahead) | `dbo.sp_S2_BuscaCuenta` (ya existente) |
| POST | `/seguimiento/actualizar` | Sí | Botón "Actualizar en SISE" | `dbo.RegistrarSeguimiento` → INSERT en `dbo.Seguimiento` |
| POST | `/seguimiento/estatus` | Sí | Cambio de estatus del expediente | Base local (SQLite) — no toca SQL Server |
| GET/POST/DELETE | `/configuracion/cuentas` | Sí | Grid de Configuración Cuentas | Base local (SQLite) |
| POST | `/configuracion/cuentas/limpiar` | Sí | Botón "Cancelar" del grid | Base local (SQLite) |

Además, `jobs/validar_estatus_proveedor.py` corre por fuera del servidor
web (programado con el Programador de tareas de Windows — ver
`jobs/README.md`) y usa `dbo.ObtenerExpedientesSinRespuestaProveedor`
para mandar alertas por correo.

## GraphQL (nuevo)

Todo lo de la tabla de arriba también está disponible por GraphQL, en
`/graphql` — misma lógica de negocio, mismos repositorios, mismos
Stored Procedures, solo expuesto de otra forma. **Es nuevo en este
proyecto y no reemplaza el REST** (ambos siguen funcionando).

- Guía paso a paso, pensada para quien es nuevo en GraphQL, con
  ejemplos para copiar y pegar: **`app/graphql/README.md`**.
- Pruebas automatizadas: `tests/test_graphql.py`.
- El frontend (`frontend/index.html`) sigue usando el REST por ahora.

## ⚠️ Pendientes / a confirmar contigo

Ver el detalle completo en `sql/README.md` y `jobs/README.md`. Resumen:

1. **Límite real de la contraseña** — la pantalla permite 20 caracteres
   pero el SP solo soporta 10 (`@pContraseña varchar(10)`). Por ahora la
   API rechaza explícitamente contraseñas de más de 10 caracteres en vez
   de truncar en silencio.
2. **Host del cliente** — un API web solo puede obtener confiablemente la
   IP del usuario, no el nombre de su PC. Por ahora se manda el hostname
   del *servidor* donde corre la API. Avísame si necesitas capturar el
   hostname real del cliente desde el navegador.
3. **Cuentas permitidas fijas** — confirmar si debe seguir siendo una
   lista fija o depender de otro criterio.
4. **Parámetro y columnas de `sp_GetSubServicios2`** — se asumió el
   nombre del parámetro (`clServicio`) y de las columnas de salida
   (`clSubServicio`, `dsSubservicio`); confirmar corriendo el SP manualmente.
5. **Datos de SMTP y correo real del proveedor** — *pendiente a propósito
   para esta sesión*. El botón "Enviar correo a proveedores" y el cron
   funcionan de punta a punta, pero en "modo simulado" (solo registran en
   el log) hasta tener host/usuario/contraseña de un servidor SMTP real,
   y hasta saber de dónde sacar el correo del proveedor (el query solo
   trae el correo del paciente).
6. **Corte 8h/24h del cron** — se implementó como escalonado (8-24h
   naranja, 24h+ rojo); confirmar si la intención era otra.

## ✅ Ya confirmado

- `ProveedorxExpediente.clEstatus = 3` = "Asignación de Proveedor" (el
  estatus que el sistema core le da al expediente cuando se le asigna un
  proveedor). Se usa tanto para `FechaAsignacionProveedor` en el listado
  como para detectar "sin respuesta" en el cron de alertas.
