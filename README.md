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
│   ├── email_service.py        # envío de correo (real si hay SMTP en .env, simulado/log si no)
│   ├── seguimiento_service.py  # reglas de 'Actualizar Core' (rol, longitud, flujo), compartidas por REST y GraphQL
│   ├── estatus_service.py      # reglas del cambio manual de estatus (rol, flujo de regreso), compartidas por REST y GraphQL
│   └── openrouter_service.py   # cliente de OpenRouter (IA) + bitácora de tokens/costo reales
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
├── img/                         # logo de IKE (blanco para el menú, a color con lema para el login) e ícono
└── js/
    ├── app.js                   # arranque, sesión, menú por perfil y navegación (#/pantalla)
    ├── core/                    # api, sesión, router, catálogos, reglas de negocio, formato, toast
    ├── componentes/             # piezas reutilizables: tabla, filtros, multiselect, paginador, KPI, modal
    └── pantallas/               # un módulo por pantalla (su HTML + su lógica)
dev_server_datos_prueba.py       # API con datos de ejemplo, para probar el frontend sin SQL Server
prompts/
└── prompt-portal-expedientes-desde-cero.md  # el pedido completo del proyecto, redactado desde cero
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

## Prompt del proyecto

En [`prompts/prompt-portal-expedientes-desde-cero.md`](prompts/prompt-portal-expedientes-desde-cero.md)
está el pedido completo de este portal redactado como si se hiciera por
primera vez: contexto, perfiles, flujo de negocio, pantallas, integración
con Core, Stored Procedures, API, seguridad, frontend, pruebas, despliegue
y forma de trabajo. Sirve para dos cosas:

- **Entender el proyecto de un vistazo**, sin leer todo el historial.
- **Plantilla para proyectos nuevos:** se conserva la estructura de
  secciones y se cambia el contenido. Las secciones de arquitectura del
  frontend, calidad, despliegue y forma de trabajo casi no cambian entre
  proyectos con este mismo stack.

Si cambia una regla de negocio importante, actualiza también el prompt
para que siga describiendo el portal tal como es.

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

Para **AWS** (EC2 Linux detrás de CloudFront y ALB, QA y producción) hay
plantillas listas en [`deploy/`](deploy/README.md): servicio systemd, script
de despliegue con verificación, workflow de ejemplo y el `.env` por ambiente.

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

1. El portal entra **por RFC**: `POST /auth/rfc/estado` revisa si el RFC
   está autorizado y si ya tiene contraseña; la primera vez se crea con
   `POST /auth/rfc/crear-password` y después se entra con
   `POST /auth/rfc/login`. Los RFC los da de alta el Administrador.
2. Las contraseñas se guardan con hash + salt (PBKDF2-SHA256) en la base
   local; el login por RFC no consulta SQL Server.
3. La app emite su **propio token (JWT)** de 8 horas. **Todos los demás
   endpoints exigen ese token** (`Authorization: Bearer <token>`).
4. Límite de intentos: 10 cada 5 minutos por IP (y RFC). La IP se toma de
   `X-Forwarded-For` según `PROXIES_CONFIABLES` (ver `app/core/red.py`).
5. El login legado por usuario de SISE (`POST /auth/login`, vía
   `dbo.sp_EncriptDesEncriptPassword`) sigue en el código pero está
   **apagado por default** (`LOGIN_LEGADO_HABILITADO=false`).

## Endpoints

| Método | Ruta | Pantalla / uso | Origen del dato |
|---|---|---|---|
| POST | `/auth/rfc/estado` · `/auth/rfc/crear-password` · `/auth/rfc/login` | Inicio de sesión (sin token) | Base local |
| GET | `/expedientes` | Expedientes: tabla + filtros | `dbo.ST_CP_ObtenerExpedientesSinProveedorMedico` + estatus local |
| POST | `/expedientes/enviar-correo-proveedores` | "Enviar correo a proveedores" (Cabina) | Correo + estatus local |
| POST / GET / POST | `/expedientes/corte` · `/expedientes/corte/{id}/descargar` · `/expedientes/corte/{id}/enviar` | Corte en Excel (Administrador) | Excel guardado en la base local + correo |
| GET | `/catalogos/servicios` · `/catalogos/subservicios` · `/catalogos/cuentas` · `/catalogos/cuentas/buscar` | Combos y buscador de cuentas | `dbo.ST_CP_ObtenerCatalogoServicio`, `dbo.ST_CP_ObtenerServicioMedico`, `dbo.ST_CP_ObtenerCatalogoCuentas`, `dbo.sp_S2_BuscaCuenta` |
| POST | `/seguimiento/actualizar` | "Actualizar Core" (Proveedor) | `dbo.ST_CP_RegistrarSeguimiento` + comentario y estatus locales |
| POST | `/seguimiento/estatus` | Estado del caso (Cabina) | Estatus local; regresar/cita también escriben en Core |
| GET | `/seguimiento/comentarios/{exp}` | Comentarios del Proveedor y del Coordinador | Base local |
| GET / POST | `/seguimiento/pago-anticipado/{exp}` | Casilla de pago anticipado | Base local |
| POST / GET | `/seguimiento/comprobante` · `/seguimiento/comprobante/{exp}` · `.../archivo` | Comprobante de pago | Base local |
| GET / POST / DELETE | `/configuracion/cuentas` · `/configuracion/cuentas/limpiar` | Configuración Cuentas (Administrador) | Base local |
| GET / POST | `/admin/accesos` · `/admin/accesos/entidades` · `/admin/accesos/{rfc}/inactivar` · `/reactivar` · `/resetear-password` · `/entidad` | Usuarios y Accesos (Administrador) | Base local |
| POST / GET | `/openrouter` · `/openrouter/iteraciones` · `/openrouter/reporte` | IA vía OpenRouter + bitácora de consumo/costo (Administrador) | `app/services/openrouter_service.py` + base local |
| GET | `/health` | Monitoreo (sin token) | — |

Además, `jobs/validar_estatus_proveedor.py` corre por fuera del servidor
web (ver `jobs/README.md`) y usa `dbo.ST_CP_ObtenerExpedientesSinRespuestaProveedor`
para mandar alertas por correo.

## OpenRouter (IA) — consumo y costo

Integración con [OpenRouter](https://openrouter.ai) (puerta de entrada a
modelos de IA de varios proveedores bajo un solo API) exclusiva del perfil
**Administrador** — mismo criterio que `/admin/accesos`, sin excepción
para sesiones SISE legadas. No tiene equivalente en GraphQL a propósito,
igual que `/admin/accesos`.

1. Crea tu API key en <https://openrouter.ai/keys> y ponla en tu `.env`
   como `OPENROUTER_API_KEY` (ver `.env.example`). Sin esto, `POST
   /openrouter` responde 400 — no hay "modo simulado" como en el correo,
   porque el costo real es justo el dato que se quiere medir.
2. `POST /openrouter` — manda `{"mensaje": "...", "modelo": "...",
   "descripcion": "..."}` a OpenRouter (modelo opcional, usa
   `OPENROUTER_MODELO_DEFAULT` si se omite) y regresa el contenido
   generado junto con tokens y costo **reales** (los que OpenRouter
   regresa en `usage`, ver su
   [Usage Accounting](https://openrouter.ai/docs/use-cases/usage-accounting)).
   Cada llamada queda guardada en la base local (tabla
   `openrouter_iteraciones`).
3. `GET /openrouter/iteraciones?desde=&hasta=` — la bitácora cruda,
   petición por petición.
4. `GET /openrouter/reporte?desde=&hasta=` — resumen: total de
   peticiones, tokens de entrada/salida/totales, costo total y
   promedio, desglose por modelo, desglose por día, y las peticiones
   de mayor consumo de tokens y de mayor costo.

Lógica en `app/services/openrouter_service.py` (cliente HTTP) y
`app/repositories/openrouter_repo.py` (bitácora y agregados). Pruebas:
`tests/test_openrouter.py` (sin llamar a OpenRouter real).

## GraphQL (nuevo)

Todo lo de la tabla de arriba también está disponible por GraphQL, en
`/graphql` — misma lógica de negocio, mismos repositorios, mismos
Stored Procedures, solo expuesto de otra forma. **Es nuevo en este
proyecto y no reemplaza el REST** (ambos siguen funcionando).

- Guía paso a paso, pensada para quien es nuevo en GraphQL, con
  ejemplos para copiar y pegar: **`app/graphql/README.md`**.
- Pruebas automatizadas: `tests/test_graphql.py`.
- El frontend (`frontend/index.html`) sigue usando el REST por ahora.

## ⚠️ Pendientes / a confirmar

Ver el detalle en `sql/README.md` y `jobs/README.md`. Resumen:

1. **Datos de SMTP y correo real del proveedor** — el envío de correos
   funciona de punta a punta, pero en "modo simulado" (solo se registra en
   el log) hasta tener host, remitente y credenciales de un SMTP real, y
   hasta saber de dónde sacar el correo del proveedor (el query solo trae
   el del paciente). **Necesario antes de producción.**
2. **Cuentas permitidas fijas** — confirmar si `CUENTAS_PERMITIDAS` sigue
   siendo una lista fija y cuál es la de producción (el default del código
   y el de `.env.example` no son la misma lista).
3. **LEFT JOIN a `dbo.CitaxExpediente`** en el listado principal — quedó
   sin columnas usadas; confirmar si se puede quitar.
4. **Corte 8h/24h del cron** — se implementó como escalonado (8-24h
   naranja, 24h+ rojo); confirmar si la intención era otra.

## ✅ Ya confirmado

- `ProveedorxExpediente.clEstatus = 3` = "Asignación de Proveedor" (el
  estatus que el sistema core le da al expediente cuando se le asigna un
  proveedor). Se usa tanto para `FechaAsignacionProveedor` en el listado
  como para detectar "sin respuesta" en el cron de alertas.
