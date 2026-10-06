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
frontend/                        # portal (HTML + CSS + JS puro, sin build), servido por FastAPI en "/"
├── index.html                   # marco: login, menú lateral y barra superior
├── css/                         # base.css · layout.css · componentes.css
└── js/
    ├── app.js                   # arranque, sesión, menú por perfil y navegación (#/pantalla)
    ├── core/                    # api, sesión, router, catálogos, reglas de negocio, formato, toast
    ├── componentes/             # piezas reutilizables: tabla, filtros, multiselect, paginador, KPI, modal
    └── pantallas/               # un módulo por pantalla (su HTML + su lógica)
dev_server_datos_prueba.py       # API con datos de ejemplo, para probar el frontend sin SQL Server
```

## 🔒 Sobre las credenciales de la base de datos

- Ahora se soportan **dos modos** (`DB_AUTH_MODE` en `.env`):
  - `windows` — Autenticación integrada de Windows, sin usuario/contraseña
    en ningún archivo. Solo funciona si la app corre en Windows.
  - `sql` — Autenticación de SQL Server. **Tú llenas `DB_USER`/`DB_PASSWORD`
    directamente en tu `.env` local**, que nunca se comparte por chat ni
    se sube a control de versiones (ver `.gitignore`). Coloca ese `.env`
    en el ambiente restringido que definas, con permisos de lectura
    limitados a la cuenta que ejecuta el proceso.

## Requisitos

- Python 3.11+ (el desarrollo se hace con 3.13).
- Driver ODBC de Microsoft para SQL Server:
  - **Windows:** [Microsoft ODBC Driver 17 o 18 para SQL Server](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server) (instalador `.msi`).
  - **Linux:** `unixODBC` y `msodbcsql18`, desde el [repositorio de paquetes de Microsoft para tu distribución](https://learn.microsoft.com/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server).
    En el `.env` usa `DB_DRIVER=ODBC Driver 18 for SQL Server` y `DB_AUTH_MODE=sql`.
- Acceso de red a SQL Server 2012 de desarrollo, con permisos de
  `EXECUTE` sobre los Stored Procedures usados.

## Instalación

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

**Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
chmod 600 .env
```

Edita `.env` con los datos reales de tu ambiente de desarrollo (servidor,
base, y si usas `DB_AUTH_MODE=sql`, tu usuario/contraseña). Genera también
tu propio `JWT_SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Con el entorno virtual activado, los comandos `python ...` de este README
son iguales en Windows y en Linux.

## Antes de arrancar: correr los scripts SQL

Sigue el orden indicado en `sql/README.md` (empieza por
`00_create_types.sql`, requerido por los demás).

## Probar visualmente, SIN necesitar SQL Server todavía

Antes de tener la base de datos real conectada, puedes ver la interfaz
funcionando de punta a punta (login incluido) con datos de ejemplo:

```bash
python dev_server_datos_prueba.py
```

Esto levanta el portal en `http://localhost:8000` con datos inventados (no
toca SQL Server para nada). Ábrelo en tu navegador en esa dirección e
inicia sesión con:

| RFC | Perfil |
|---|---|
| `ADMI000001` | Administrador |
| `CABI000001` | Cabina |
| `PROV000001` | Proveedor (entidad Campeche) |

El servidor los da de alta solo al arrancar. La primera vez que entres con
cada uno, el portal te pide crear su contraseña (mínimo 8 caracteres, con
mayúscula, minúscula, número y carácter especial).

Así puedes confirmar que la parte visual y los flujos (filtros, KPIs,
Seguimiento, Configuración Cuentas) funcionan bien, **antes** de meter la
variable de si la conexión real a SQL Server funciona o no.

## Frontend real (contra tu base de desarrollo)

Una vez que tengas los scripts SQL corridos y tu `.env` configurado:

```bash
uvicorn app.main:app --reload --port 8000
```

y abre `http://localhost:8000` con tu usuario real. Si todavía no hay RFC
dados de alta en tu base local, `python -m scripts.seed_usuarios_prueba`
crea los mismos tres RFC de prueba de la tabla de arriba.

El frontend es HTML + CSS + JavaScript puro con módulos ES (sin frameworks
ni build step). Lo sirve el mismo FastAPI (`app/main.py`, al final), así
que portal y API comparten origen: no hace falta configurar URL ni CORS.
Como usa módulos, **no funciona abriendo `index.html` con doble clic**
(`file://`); siempre entra por `http://localhost:8000`.

### Cómo está organizado el frontend

- Cada pantalla vive en `frontend/js/pantallas/<pantalla>.js` y trae su
  propio HTML. Todas siguen el mismo contrato, que `app.js` usa para
  montarlas y navegar: `montar(contenedor)`, `aplicarPermisos()`,
  `alEntrar()` y `reiniciar()` (las tres últimas son opcionales).
- Lo que se repite entre pantallas (tabla de expedientes, filtros,
  multiselect de cuentas, paginador, KPIs, modal) está en
  `frontend/js/componentes/`.
- Qué pantalla ve cada perfil se decide en un solo lugar:
  `pantallaPermitida()` en `frontend/js/app.js`.
- Cuando una pantalla cambia el estatus de un expediente, avisa con un
  evento (`notificarCambioEstatus`, en `core/reglas-expedientes.js`) y las
  demás actualizan sus datos en memoria, sin importarse entre sí.
- Para agregar una pantalla nueva: crea su módulo en `pantallas/`,
  regístralo en `PANTALLAS` de `app.js`, agrega su entrada al menú en
  `index.html` (con `data-pantalla="..."`) y su regla en `pantallaPermitida()`.

Documentación interactiva del API (Swagger) en `http://localhost:8000/docs`.

## Despliegue en un servidor

En cualquier sistema operativo, el portal necesita lo mismo:

- **Un solo proceso de uvicorn**, sin `--workers`: el límite de intentos
  de login vive en la memoria del proceso (ver `app/core/rate_limit.py`).
- **Un proxy inverso con TLS** delante (uvicorn solo habla HTTP), con
  uvicorn escuchando en `127.0.0.1:8000` para no exponerlo a la red.
- **El proxy debe reemplazar `X-Forwarded-For` con la IP real del cliente.**
  La app cuenta los intentos de login por esa IP; si el proxy no la manda,
  todos los usuarios aparecen como la misma IP y se bloquean entre sí, y
  si la agrega al final, un cliente puede falsearla.
- **Publicarlo en la raíz de un dominio** (`https://expedientes.dominio/`),
  no bajo una subruta: el portal llama a la API con rutas absolutas.
- **Hora local de México en el servidor** (`America/Mexico_City`): las
  fechas que guarda la app (estatus, comentarios, cortes) usan la hora
  del servidor.
- **Respaldo de `data/app_local.db`**: es la única copia de accesos,
  estatus, comentarios, comprobantes y cortes.
- El job de alertas programado cada hora (ver `jobs/README.md`).

### Windows

Para correrlo como servicio de Windows, una opción es
[NSSM](https://nssm.cc/), con estos valores:

- Path: `C:\ruta\al\proyecto\.venv\Scripts\python.exe`
- Startup directory: `C:\ruta\al\proyecto`
- Arguments: `-m uvicorn app.main:app --host 127.0.0.1 --port 8000`

El proxy con TLS puede ser IIS con *Application Request Routing* (ARR) y
*URL Rewrite*, reenviando a `http://127.0.0.1:8000`.

### Linux

Servicio systemd (rutas y usuario de ejemplo):

```ini
# /etc/systemd/system/portal-expedientes.service
[Unit]
Description=Portal Expedientes Medicos
After=network-online.target

[Service]
User=portal
WorkingDirectory=/opt/portal-expedientes
Environment=TZ=America/Mexico_City
ExecStart=/opt/portal-expedientes/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now portal-expedientes
journalctl -u portal-expedientes -f     # logs
```

Proxy nginx:

```nginx
server {
    listen 443 ssl;
    server_name expedientes.dominio;
    # ssl_certificate / ssl_certificate_key del dominio
    client_max_body_size 6m;   # comprobantes de pago de hasta 5 MB

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        # La app toma la IP del cliente de aquí: se REEMPLAZA con la IP real
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

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
