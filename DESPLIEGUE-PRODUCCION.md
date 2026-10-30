# Despliegue en producción — Portal Promédico

**Documento técnico de requerimientos y procedimiento**

| | |
|---|---|
| Sistema | Portal Promédico (expedientes médicos y directorio de proveedores) |
| Repositorio | `IkeAsistencia/Ike-Portal-Expedientes-Medicos` |
| Destino | AWS — EC2 Linux detrás de CloudFront + WAF + ALB |
| Última actualización | 21 de octubre de 2026 |

---

## 1. Para qué sirve este documento

Reúne **todo lo que hay que tener listo** y **todo lo que hay que hacer**
para poner el portal en producción. Está escrito para repartirse entre
varias áreas: Infraestructura levanta el servidor y la red, Base de Datos
prepara SQL Server, Seguridad autoriza los accesos, y Desarrollo instala y
despliega.

Cada requerimiento dice **quién lo provee** y **qué pasa si falta**, para
que se pueda saber de antemano qué bloquea el arranque y qué solo degrada
una función.

No cubre QA: por decisión del proyecto no se levanta un ambiente de QA
separado, y el despliegue va siempre por etiqueta desde `main`.

---

## 2. Qué se va a desplegar

Un solo proceso de Python (FastAPI sobre uvicorn) que sirve a la vez la
API y el frontend. No hay build de frontend ni contenedores: el código se
clona del repositorio y se corre.

```
Usuario → CloudFront + WAF → ALB → EC2 Linux (uvicorn :8000)
                                        │
                                        ├── SQL Server de SISE  (lectura por Stored Procedures)
                                        ├── SQLite local         (data/app_local.db)
                                        ├── SMTP corporativo     (alertas a proveedores)
                                        └── Google Maps (Places) (búsqueda fuera de la red)
```

**Dos bases de datos, con responsabilidades distintas:**

| | SQL Server (SISE) | SQLite local (`data/app_local.db`) |
|---|---|---|
| Qué guarda | Los expedientes, cuentas y servicios. Es el sistema central | Lo que nace en el portal: accesos y perfiles, estatus, comentarios, comprobantes, cortes, el padrón de proveedores y el catálogo de especialidades |
| Cómo se usa | **Solo lectura**, y únicamente por Stored Procedures | Lectura y escritura |
| Respaldo | El del sistema central | **Responsabilidad de este despliegue** (sección 9) |

El punto importante: el SQLite **no es un caché**. Si se pierde, se pierden
los accesos de los usuarios y todo el seguimiento. Tiene que vivir en un
volumen persistente y respaldado.

---

## 3. Requerimientos

### 3.1 Infraestructura AWS

| Requerimiento | Detalle | Si falta |
|---|---|---|
| **EC2 Linux**, una sola instancia | Sin Auto Scaling de varias réplicas: el control de intentos de login vive en la memoria del proceso, así que dos réplicas lo dejarían sin efecto | Bloquea |
| **Subred privada** | La instancia no debe ser alcanzable directo desde internet | Bloquea |
| **ALB** delante | Health check en `GET /health`; tamaño de carga de al menos **6 MB** | Bloquea |
| **CloudFront + WAF** | Según el esquema de la empresa | Bloquea |
| **Volumen persistente** para `data/` | Con respaldo programado | Bloquea |
| **NAT gateway** con salida HTTPS | Para la consulta a Google Maps, si se activa (sección 3.4) | Degrada: se apaga la búsqueda fuera de la red |

**Puertos:**

| Sentido | Puerto | Para qué |
|---|---|---|
| Entrada a la EC2 | TCP 8000, **solo desde el ALB** | El portal. La aplicación confía en el encabezado `X-Forwarded-For` para contar intentos de login; si alguien puede llegarle directo, puede falsearlo |
| Salida | TCP 1533 | SQL Server de SISE (**no es el 1433 estándar**; es el que usa SISE hoy) |
| Salida | TCP 587 | SMTP corporativo |
| Salida | TCP 443 | Places API de Google Maps (`places.googleapis.com`), si se activa (sección 3.4) |
| Salida (navegador del usuario) | TCP 443 | `maps.googleapis.com`, para pintar el mapa de Google (sección 3.4.1). La consume el navegador, no el servidor |

**Configuración del ALB y CloudFront:**

- El proxy debe **reemplazar** `X-Forwarded-For` con la IP real del cliente,
  no agregarla al final. El portal bloquea por IP tras varios intentos de
  login fallidos: si todos los usuarios llegan con la misma IP se bloquean
  entre sí, y si la IP viene al final de la lista, un cliente puede
  inventarla y evadir el bloqueo.
- **Límite de carga de 6 MB**: los comprobantes de pago aceptan hasta 5 MB
  y el resto es margen para el encabezado.
- **Sin caché para la API**, y reenviando el encabezado `Authorization`. Solo
  `/css/*`, `/js/*` e `/img/*` se pueden cachear.
- **Publicar en la raíz del dominio**, no en una subruta: el portal llama a
  la API con rutas absolutas y bajo una subruta no encontraría nada.

### 3.2 Base de datos SISE (SQL Server)

| Requerimiento | Detalle | Si falta |
|---|---|---|
| Conectividad desde la EC2 | Por VPN o Direct Connect, al puerto 1533 | Bloquea |
| **Stored Procedures creados** | Los de la carpeta `sql/`: correr `00` a `05` y `07`, **en ese orden**. El `00_create_types.sql` va primero porque los demás lo necesitan, y el `06` está marcado como DEPRECADO: **no se corre** | Bloquea |
| **Usuario de aplicación** | Solo con `GRANT EXECUTE` sobre esos procedimientos y sobre el tipo `dbo.IntList`. **Sin permisos de lectura directa a las tablas** | Bloquea |
| Certificado del servidor | Si es válido, `DB_TRUST_SERVER_CERTIFICATE=false`. Si no, hay que ponerlo en `true` y dejarlo documentado como excepción | Degrada la seguridad del canal |

Quien **crea** los procedimientos necesita permisos de esquema `dbo` (rol
`db_ddladmin`); el usuario con el que se conecta la aplicación **no**. Son
dos usuarios distintos y conviene que así sea.

### 3.3 Correo (SMTP)

| Requerimiento | Detalle | Si falta |
|---|---|---|
| Host, puerto, usuario, contraseña y remitente | Del SMTP corporativo | Degrada: los correos quedan en "modo simulado" (se registran en el log y no salen) |
| **Correo y entidad de cada proveedor** | Se capturan en Usuarios y Accesos al dar de alta el perfil Proveedor | A las entidades sin proveedor no les llega correo (Cabina ve el aviso; los expedientes igual pasan a "En Espera de Respuesta") |
| **Tope de envíos de la cuenta** | 100 al día (`SMTP_LIMITE_DIARIO`). Falta confirmar si el servidor cuenta por mensaje o por destinatario (`SMTP_CUENTA_POR_DESTINATARIO`) | Si el tope real es menor que el configurado, el servidor de correo rechazaría los envíos de más |

"Enviar correo a proveedores" manda **un solo correo** con toda la
selección, en copia oculta, a los proveedores de las entidades que aparecen
en ella. El portal lleva el contador del día, pide confirmación al acercarse
al tope y, al llegar, ya no deja salir correos (ver
`app/services/envio_correo_service.py`).

### 3.4 Places API de Google Maps

| Requerimiento | Detalle | Si falta |
|---|---|---|
| `GOOGLE_MAPS_API_KEY` | Llave de un proyecto de Google Cloud con la "Places API" habilitada | Degrada: la búsqueda fuera de la red responde "no configurada" y el resto del portal sigue igual |
| **Facturación activa** en ese proyecto de Google Cloud | Google exige una cuenta de facturación (tarjeta) para emitir la llave, aunque haya crédito mensual gratuito | Sin ella, Google rechaza la llave aunque esté bien copiada |
| **Presupuesto/alertas** en Google Cloud | Cada búsqueda tiene costo por consulta (no por resultado); sin un tope, un uso intenso del botón puede generar cargos inesperados | No bloquea, pero expone a la empresa a un gasto no previsto |
| Salida HTTPS con NAT | La consulta sale **del servidor**, no del navegador del usuario | Degrada igual, pero con error de conexión |

Sirve para proponer establecimientos fuera de la red cuando el padrón no
tiene ninguno en la zona buscada. Google regresa el giro real del negocio
(buena señal por especialidad) y puede incluir el nombre del médico y
reseñas de pacientes -- revisar con cumplimiento/legal antes de activarla
si eso es relevante para la empresa. No es indispensable para operar.

#### 3.4.1 Mapa de los resultados (segunda llave)

Los **Términos de Servicio** de Google prohíben mostrar contenido de la
Places API sobre un mapa que no sea de Google (*Maps Service Specific Terms*,
sección 14.2: *"Customer must not use Google Maps Content from the Places API
in conjunction with a non-Google map"*). Por eso los resultados se pintan
con **Maps JavaScript API**, que necesita una **segunda llave**, distinta de
la anterior:

| Variable | Dónde vive | Restricción obligatoria |
|---|---|---|
| `GOOGLE_MAPS_API_KEY` | Solo el servidor (nunca sale al navegador) | Restringir por IP del servidor y limitar a **Places API (New)** |
| `GOOGLE_MAPS_BROWSER_API_KEY` | **Viaja al navegador** | Restringir por **dominio (HTTP referrers)** y limitar a **Maps JavaScript API** |

Si la segunda llave no se configura, la búsqueda sigue funcionando normal:
los resultados se muestran en lista y el botón "Mapa" no aparece (el portal
explica por qué).

| Requerimiento | Detalle | Si falta |
|---|---|---|
| `GOOGLE_MAPS_BROWSER_API_KEY` | Llave restringida por dominio, solo con Maps JavaScript API | Degrada: los resultados de Google se ven en lista; el resto funciona igual |
| `GOOGLE_MAPS_MAP_ID` | Opcional: Map ID del estilo (Cloud Console > Map Management) | Se usa `DEMO_MAP_ID`, válido para desarrollo pero no para producción |
| Cargas de mapa | 10,000 cargas/mes sin costo; después ≈ USD $7 por 1,000 | Hay costo sólo si se rebasa el tope mensual |

Referencias: [seguridad de llaves](https://developers.google.com/maps/api-security-best-practices)
y [precios](https://developers.google.com/maps/billing-and-pricing/pricing).

### 3.6 Software en el servidor

| | |
|---|---|
| Python | **3.13** (mínimo soportado: 3.11) |
| Driver ODBC | `unixODBC` y `msodbcsql18`, del repositorio de Microsoft para la distribución |
| Git | Para clonar y actualizar el código |
| Zona horaria | **`America/Mexico_City`** |

La zona horaria no es un detalle cosmético: las fechas de estatus,
comentarios, cortes y alertas se guardan con la hora del servidor. Con el
servidor en UTC, los cortes de día quedarían desfasados seis horas.

### 3.7 Dominio y certificado

| | |
|---|---|
| Dominio | `promedico.ikeasistencia.com` (propuesta, por confirmar) |
| Certificado TLS | En CloudFront / ALB. uvicorn solo habla HTTP |

### 3.8 Datos y cuentas

| Requerimiento | Detalle |
|---|---|
| **RFC del primer administrador** | Se da de alta a mano (sección 5, paso 7); de ahí en adelante él da de alta a los demás desde el portal |
| **`CUENTAS_PERMITIDAS`** | La lista de cuentas que el portal puede ver. Está pendiente de confirmar: el valor que trae el código y el de `.env.example` **no son la misma lista** |
| Padrón de proveedores | Se carga desde el portal con la plantilla de Excel. No requiere nada en el despliegue |

---

## 4. Lo que debe quedar resuelto antes de salir

No son pasos de instalación: son decisiones o datos que alguien tiene que
entregar. Conviene revisarlas en conjunto antes de agendar la salida.

| # | Qué falta | Quién lo resuelve | Por qué importa |
|---|---|---|---|
| 1 | De dónde se saca el **correo del proveedor** | Negocio / SISE | Sin esto las alertas de 8 y 24 horas no llegan a su destinatario |
| 2 | Credenciales reales del **SMTP** | Infraestructura | Sin ellas los correos solo se escriben en el log |
| 3 | La lista de **`CUENTAS_PERMITIDAS`** de producción | Negocio | Define qué expedientes se ven; hoy hay dos listas distintas y ninguna confirmada |
| 4 | Dos hallazgos de seguridad **pendientes de decisión** | Negocio / Desarrollo | Ver abajo |
| 5 | Confirmar el **corte de 8 h / 24 h** de las alertas | Negocio | Se implementó escalonado (8-24 h naranja, 24 h+ rojo); si la intención era otra, cambia el comportamiento del job |

**Sobre el punto 4**, los dos hallazgos están documentados en
`SECURITY-REVIEW.md` y siguen abiertos a propósito, esperando definición:

| Severidad | Dónde | Qué pasa |
|---|---|---|
| 🟡 MEDIUM | `GET /directorio-proveedores/citas` | Devuelve **todas** las citas del portal, sin filtrar por usuario |
| 🟡 MEDIUM | Cancelar cita | No valida que la cita sea de quien la cancela, y los folios son consecutivos (se pueden adivinar) |

Ninguno de los dos impide instalar, pero ambos exponen datos de citas entre
usuarios. **Conviene cerrarlos antes de la salida**, no después.

---

## 5. Preparar el servidor (una sola vez)

Los pasos 1 a 7 se hacen una vez. A partir de ahí, cada versión nueva se
despliega con un solo comando (sección 6).

### Paso 1 — Sistema operativo

Instalar Python 3.13, `git`, `unixODBC` y `msodbcsql18` desde el
repositorio de Microsoft para la distribución. Fijar la zona horaria:

```bash
sudo timedatectl set-timezone America/Mexico_City
```

### Paso 2 — Usuario de servicio y código

El portal **no corre como `root`**:

```bash
sudo useradd --system --create-home portal
sudo git clone https://github.com/IkeAsistencia/Ike-Portal-Expedientes-Medicos.git /opt/portal-expedientes
sudo chown -R portal:portal /opt/portal-expedientes
cd /opt/portal-expedientes
sudo -u portal python3.13 -m venv .venv
sudo -u portal .venv/bin/pip install -r requirements.txt
```

### Paso 3 — Archivo `.env`

Partir de `.env.example`, llenarlo con los valores de la sección 7 y
dejarlo con permisos cerrados:

```bash
sudo -u portal cp .env.example .env
sudo chmod 600 .env
sudo chown portal:portal .env
```

Los permisos `600` importan: ahí van la contraseña de SQL Server, la del
SMTP y la llave con la que se firman las sesiones.

### Paso 4 — Carpeta de datos

`data/` se crea sola al arrancar, pero **debe estar en el volumen
persistente y respaldado** antes del primer arranque. Si se monta después,
se pierde lo que se haya guardado mientras tanto.

### Paso 5 — Servicio

```bash
sudo cp deploy/portal-expedientes.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now portal-expedientes
```

Y permitir que el usuario `portal` reinicie **solo su propio servicio**, que
es lo que necesita el script de despliegue (`sudo visudo -f /etc/sudoers.d/portal`):

```
portal ALL=(root) NOPASSWD: /usr/bin/systemctl restart portal-expedientes
```

### Paso 6 — Job de alertas

Revisa cada hora los expedientes con proveedor asignado que no han tenido
respuesta y manda las alertas. Corre, hace su revisión y termina: no se
queda vivo.

```bash
sudo mkdir -p /var/log/portal-expedientes
sudo chown portal /var/log/portal-expedientes
```

En el `crontab -e` del usuario `portal`:

```cron
TZ=America/Mexico_City
0 * * * * cd /opt/portal-expedientes && .venv/bin/python -m jobs.validar_estatus_proveedor >> /var/log/portal-expedientes/job.log 2>&1
```

El `cd` no es opcional: sin él no encuentra el `.env` ni el paquete `app`.

### Paso 7 — Primer administrador

```bash
cd /opt/portal-expedientes
sudo -u portal .venv/bin/python -c "from app.db.local_store import init_local_db; from app.repositories import accesos_repo as a; init_local_db(); a.alta_acceso('RFCDELADMIN', 'Nombre del administrador', a.PERFIL_ADMINISTRADOR)"
```

De ahí en adelante, el administrador da de alta a los demás desde el portal.

> **Aquí no se corre `scripts/seed_usuarios_prueba.py`.** Ese script es de
> desarrollo: crea RFC de prueba con una contraseña conocida y publicada en
> el repositorio.

---

## 6. Desplegar una versión

Siempre **por etiqueta**, nunca por rama:

```bash
sudo -u portal /opt/portal-expedientes/deploy/desplegar.sh v1.0.0
```

El script actualiza el código, instala dependencias, reinicia el servicio y
**no termina bien hasta que `/health` responde**. Si el portal no levanta,
falla con el comando exacto para ver el log.

Se despliega por etiqueta y no por rama porque una rama se mueve: al
revisar un incidente tres semanas después, `test` o `main` ya no son lo que
se instaló ese día. Una etiqueta sí.

El repositorio incluye `deploy/github-actions-deploy.yml.ejemplo` para
automatizarlo (etiqueta `v*` → producción). **No está activo**; para
activarlo hay que copiarlo a `.github/workflows/` y cargar los secretos
`PROD_HOST`, `PROD_USER` y `PROD_SSH_KEY`.

---

## 7. Variables del `.env` de producción

| Variable | Valor | Qué pasa si está mal |
|---|---|---|
| `DB_AUTH_MODE` | `sql` | En Linux no existe la autenticación de Windows; con otro valor no conecta |
| `DB_SERVER` | Servidor e instancia de SISE, con el puerto (`servidor,1533`) | No conecta |
| `DB_NAME` | Base productiva | No conecta |
| `DB_USER`, `DB_PASSWORD` | Usuario de aplicación, solo con `EXECUTE` | No conecta |
| `DB_DRIVER` | `ODBC Driver 18 for SQL Server` | No conecta |
| `DB_TRUST_SERVER_CERTIFICATE` | `false` si el certificado es válido | Con `true` el canal se cifra pero no se valida contra quién |
| `LOCAL_DB_PATH` | Ruta del SQLite en el volumen persistente | Si apunta a disco efímero, **se pierden accesos y seguimiento** |
| `JWT_SECRET_KEY` | Uno propio, que no se repita en ningún otro lado: `python -c "import secrets; print(secrets.token_hex(32))"`. **En AWS va en Secrets Manager, no aquí** (sección 7.1) | Con una llave reutilizada, una sesión de otro ambiente valdría aquí |
| `JWT_EXPIRE_MINUTES` | El acordado para producción | Sesiones más largas o más cortas de lo esperado |
| `CUENTAS_PERMITIDAS` | La lista confirmada (pendiente, sección 4) | Se ven de más o de menos |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_REMITENTE`, `SMTP_USAR_TLS` | Del SMTP corporativo | Sin ellos, los correos solo se registran en el log |
| `SMTP_DESTINATARIO_PRUEBA` | **Vacío en producción** | Si queda con valor, los correos se desvían a ese buzón |
| `SMTP_LIMITE_DIARIO`, `SMTP_AVISO_LIMITE` | `100` y `80`, o lo que autorice quien administra la cuenta de correo | Con un tope mayor al real, el servidor de correo rechazaría los envíos de más |
| `SMTP_CUENTA_POR_DESTINATARIO` | `true` hasta confirmar cómo cuenta el servidor | Con `false` y un servidor que cuenta por destinatario, el portal se pasaría del tope sin darse cuenta |
| `GOOGLE_MAPS_API_KEY` | Llave de Google Cloud con la Places API habilitada y facturación activa (opcional, sección 3.4). Solo la usa el servidor | Sin ella se apaga la búsqueda fuera de la red |
| `GOOGLE_MAPS_BROWSER_API_KEY` | Llave **distinta**, restringida por dominio y solo con Maps JavaScript API (sección 3.4.1) | Los resultados se muestran en lista en vez de mapa |
| `PROXIES_CONFIABLES` | `2` con CloudFront + ALB; `1` si solo hay ALB | Un número mal puesto rompe el conteo de intentos de login |
| `CORS_ALLOWED_ORIGINS` | **Vacío** | Con valor, otros sitios podrían llamar a la API desde el navegador |
| `GRAPHQL_IDE_HABILITADO` | **`false`** | Con `true` queda expuesto el explorador de GraphQL |
| `LOGIN_LEGADO_HABILITADO` | **`false`** | Con `true` queda abierta la ruta de login anterior |

`GOOGLE_MAPS_TIMEOUT_SEGUNDOS` y `GOOGLE_MAPS_MAXIMO_RESULTADOS` tienen un
valor por omisión razonable; solo hay que tocarlos si el servicio
responde lento.

---

## 7.1 Secretos en AWS Secrets Manager

En AWS las llaves **no** se dejan en el `.env` del servidor: las administra
Secrets Manager. La app las lee al arrancar y las deja en el entorno, y
**ganan sobre lo que diga el `.env`** — así una llave vieja olvidada en la
instancia no puede tener prioridad sobre el secreto administrado.

| Variable | Valor en producción |
|---|---|
| `SECRETOS_AWS_MODO` | **`obligatorio`** (ver abajo) |
| `SECRETOS_AWS_NOMBRE` | `encryption-portal-medicos` |
| `SECRETOS_AWS_REGION` | `mx-central-1` |
| `SECRETOS_AWS_CLAVE` | vacío (solo si el secreto es texto plano) |

### Modos

| Modo | Qué hace | Cuándo usarlo |
|---|---|---|
| `off` | No toca AWS. Default. | Desarrollo y pruebas |
| `obligatorio` | Si el secreto no se lee, **la app no arranca** | **Producción** |
| `opcional` | Si falla, sigue con el entorno | Primera puesta en marcha |

En producción debe ir `obligatorio`: es preferible un servicio caído y
visible a uno que arrancó "bien" pero con Google Maps apagado o con un
`JWT_SECRET_KEY` inseguro. El error sale en `journalctl -u portal-expedientes`
con el nombre del secreto y la región, nunca con el valor.

### Formato del secreto

Lo recomendado es guardarlo como **JSON**, con el nombre de cada variable en
mayúsculas:

```json
{
  "GOOGLE_MAPS_API_KEY": "...",
  "GOOGLE_MAPS_BROWSER_API_KEY": "...",
  "GOOGLE_MAPS_MAP_ID": "...",
  "JWT_SECRET_KEY": "..."
}
```

Se admiten estas variables (y **solo** estas — el resto se ignora con un
aviso en el log, porque el secreto lo administra otra área y no debe poder
reescribir `PATH` ni nada del proceso):

`GOOGLE_MAPS_API_KEY`, `GOOGLE_MAPS_BROWSER_API_KEY`, `GOOGLE_MAPS_MAP_ID`,
`JWT_SECRET_KEY`, `DB_PASSWORD`, `SMTP_USER`, `SMTP_PASSWORD`.

Si el secreto se guardó como **texto plano** (una sola llave suelta), hay que
decir a cuál variable corresponde con `SECRETOS_AWS_CLAVE`. Sin eso se ignora
con un aviso: es mejor que adivinar y poner la llave en el lugar equivocado.

### Permisos de IAM

La instancia (rol de EC2, o el task role si algún día se pasa a ECS) necesita
**solo** `secretsmanager:GetSecretValue` sobre el ARN de ese secreto:

```json
{
  "Effect": "Allow",
  "Action": "secretsmanager:GetSecretValue",
  "Resource": "arn:aws:secretsmanager:mx-central-1:<cuenta>:secret:encryption-portal-medicos-*"
}
```

Nada más: ni listar secretos, ni escribirlos. La app solo lee.

### Probar que quedó bien

```bash
# Debe imprimir los NOMBRES de las variables aplicadas, nunca los valores.
sudo journalctl -u portal-expedientes -n 50 | grep "Secretos de AWS"
# Esperado: "Secretos de AWS: aplicadas 4 variable(s): GOOGLE_MAPS_API_KEY, ..."
```

Si el servicio no arranca y el log dice `No se pudo leer el secreto`, el
problema es de IAM o de la región, no del código.

Cuidado con `SMTP_DESTINATARIO_PRUEBA`: es una válvula pensada para
desarrollo, que manda **todos** los correos a un solo buzón. En producción
debe quedar vacía. Un detalle que ya costó una confusión: si el nombre de
la variable se escribe mal, la aplicación **no arranca** (no acepta
variables que no reconoce), lo cual es intencional: es preferible que falle
al arrancar a que corra con una configuración que nadie quiso.

---

## 8. Verificación después de desplegar

| # | Qué revisar | Resultado esperado |
|---|---|---|
| 1 | `curl -fsS https://<dominio>/health` | `{"status":"ok"}` |
| 2 | Entrar con un RFC de cada perfil | Administrador, Cabina y Proveedor ven su pantalla |
| 3 | Abrir un expediente del listado | Trae datos reales de SISE (confirma los Stored Procedures y los permisos) |
| 4 | Cabina manda un correo a un proveedor de prueba | **Llega de verdad**, no solo al log |
| 5 | Buscar en el Directorio **fuera de la red** (Google Maps, si se activó) | Devuelve resultados. Si dice "no configurada", falta el `GOOGLE_MAPS_API_KEY`; si da error de conexión, falta el NAT |
| 5b | Ver los resultados **en el mapa** | Si muestra un mapa gris con "For development purposes only", la llave no tiene restricción/facturación correcta |
| 6 | Subir un comprobante de ~4 MB | Se guarda (confirma el límite de carga del ALB) |
| 7 | `journalctl -u portal-expedientes -n 100` | Sin errores |
| 8 | Esperar al siguiente cambio de hora y revisar `job.log` | El job corrió y dejó su registro |

La 3, la 4 y la 6 son las que de verdad distinguen un despliegue sano: son
las que tocan SQL Server, el SMTP y el ALB. Las demás pueden pasar aunque
algo esté mal configurado del otro lado.

---

## 9. Operación

### Respaldos

**`data/app_local.db` es la única copia** de los accesos y perfiles de
usuario, los estatus y comentarios, los comprobantes, los cortes, el padrón
de proveedores y el catálogo de especialidades. SISE **no** tiene nada de
eso.

Hay que respaldarlo con la frecuencia que el negocio acepte perder. Si se
pierde el archivo, todos los usuarios quedan fuera del portal hasta que un
administrador los vuelva a dar de alta uno por uno.

### Logs

| Qué | Dónde |
|---|---|
| Portal | `journalctl -u portal-expedientes` |
| Job de alertas | `/var/log/portal-expedientes/job.log` |

### Regresar a la versión anterior

```bash
# Respaldar PRIMERO
sudo -u portal cp /opt/portal-expedientes/data/app_local.db /ruta/respaldo/app_local.db.$(date +%F-%H%M)

sudo -u portal /opt/portal-expedientes/deploy/desplegar.sh v0.9.0
```

El respaldo antes de regresar no es protocolo de más: el portal **agrega
columnas al SQLite automáticamente** al arrancar una versión nueva. Esas
columnas no se quitan solas al volver atrás, y una versión anterior podría
no saber leer la estructura nueva. Con el respaldo se puede volver al
estado exacto.

---

## 10. Lo que no se debe hacer en producción

| | Por qué |
|---|---|
| Correr `uvicorn --workers N` o varias réplicas | El control de intentos de login vive en la memoria del proceso. Con varios procesos, cada uno cuenta por su lado y el bloqueo deja de servir |
| Correr `scripts/seed_usuarios_prueba.py` | Crea RFC de prueba con una contraseña conocida y publicada |
| Dejar `GRAPHQL_IDE_HABILITADO=true` | Expone el explorador de GraphQL del portal |
| Publicar el portal bajo una subruta | El frontend llama a la API con rutas absolutas |
| Abrir el puerto 8000 a algo que no sea el ALB | La aplicación confía en `X-Forwarded-For`, que entonces se puede falsear |
| Dejar `data/` en disco efímero | Se pierden los accesos y todo el seguimiento |

---

## 11. Pendientes conocidos del portal

No bloquean el despliegue, pero conviene que las áreas los sepan antes de
recibir el portal:

| | |
|---|---|
| Validación de cédula profesional | Valida el formato, **no consulta el Registro Nacional de Profesionistas**. Un número con formato correcto pero inexistente pasa |
| Columna "Zona" del padrón | Muestra la clave de la entidad en vez del nombre |
| Coordenadas del padrón | Solo 75 de 666 proveedores se pueden ubicar en el mapa. El resto depende de que el área llene esas columnas en el Excel de carga |
| `LEFT JOIN` a `dbo.CitaxExpediente` | Quedó sin columnas usadas en el listado principal; falta confirmar si se puede quitar |

---

## Anexo — Documentos relacionados

| Documento | Qué cubre |
|---|---|
| `deploy/README.md` | Las plantillas que acompañan a este procedimiento |
| `sql/README.md` | Orden de los Stored Procedures y los `GRANT` exactos |
| `jobs/README.md` | Reglas del job de alertas y cómo programarlo |
| `SECURITY-REVIEW.md` | Hallazgos de seguridad, corregidos y pendientes |
| `WEB-SCRAPING-DOCTORALIA.md` | Por qué no se amplía el directorio con scraping, y el análisis de CLUES y Google Maps |
| `README.md` | Arquitectura, instalación local y endpoints |
