# Prompt — Portal Expedientes Médicos (desde cero)

> **Cómo reutilizar este prompt en otro proyecto:** conserva la estructura
> de secciones (contexto, usuarios, flujo, pantallas, datos, API,
> seguridad, frontend, calidad, despliegue y forma de trabajo) y cambia el
> contenido de cada una. Las secciones 11 a 14 casi no cambian entre
> proyectos del mismo stack.

---

## 1. Contexto y objetivo

Necesito construir el **Portal Expedientes Médicos** de IKE Asistencia: una
aplicación web interna donde **Cabina Médica** da seguimiento a los
expedientes médicos que llevan 8 horas o más sin proveedor asignado en el
sistema core (SISE), los manda a los **proveedores médicos**, y estos
responden desde el mismo portal. Un **Administrador** gestiona accesos y
genera cortes en Excel.

- Usuarios: entre 40 y 60 personas en total (Cabina Médica y Proveedores),
  todas colaboradores o asociados de IKE. No todos conectados a la vez.
- El portal **solo consulta** la base de SISE y **agrega registros** a su
  bitácora de seguimiento. No cobra, no maneja tarjetas y no modifica el
  flujo de Core.
- Idioma de la interfaz, el código (nombres de variables, comentarios) y la
  documentación: **español**.

## 2. Stack y restricciones técnicas

- **Backend:** Python 3.13 + FastAPI + uvicorn. Validación con Pydantic.
- **Base de datos de negocio:** SQL Server **2012 Standard** (SISE),
  acceso **exclusivamente por Stored Procedures** vía `pyodbc` (ODBC Driver
  17/18). Nada de SQL embebido contra SISE.
  - Compatibilidad 2012: sin `CREATE OR ALTER` (usar `IF OBJECT_ID(...) IS
    NOT NULL DROP PROCEDURE` + `CREATE`), sin `STRING_SPLIT` (usar un
    Table-Valued Parameter `dbo.IntList` para listas de IDs).
  - Pool de conexiones ODBC activo y "calentado" al arrancar la app, con
    timeout corto para no colgar el arranque si SQL Server no responde.
- **Base propia de la app:** SQLite local (un archivo en `data/`), para
  todo lo que no vive en SISE: accesos, estatus de trabajo, comentarios,
  comprobantes, cortes, configuración y alertas enviadas.
- **Frontend:** HTML + CSS + JavaScript puro con **módulos ES**, sin
  frameworks ni paso de compilación. Lo sirve el mismo FastAPI en `/`
  (portal y API en el mismo origen; sin CORS para el portal).
- **API adicional:** GraphQL (Strawberry) en `/graphql` con la misma lógica
  que el REST; el explorador visual se puede apagar por configuración.
- **Excel:** openpyxl.
- **Configuración:** archivo `.env` (pydantic-settings), nunca en el
  repositorio. Incluir `.env.example` documentado.
- Debe correr en **Windows** (desarrollo) y en un **servidor Linux**
  (producción, detrás de un proxy con TLS).

## 3. Perfiles y permisos

| Perfil | Qué hace | Pantallas |
|---|---|---|
| **Administrador** | Da de alta y administra accesos; configura cuentas; genera cortes en Excel | Usuarios y Accesos (inicio), Configuración Cuentas, Expedientes (sin entrar al detalle) |
| **Cabina Médica** (Coordinador) | Revisa expedientes, los manda a proveedores, revisa respuestas y decide el estado | Expedientes (inicio), Seguimiento |
| **Proveedor** | Atiende los expedientes que le mandan y registra su seguimiento | Expedientes (solo su bandeja), Seguimiento |

- Qué pantalla ve cada perfil se decide en **un solo lugar** del frontend
  y el backend valida cada permiso por su cuenta (nunca confiar solo en
  ocultar botones).
- Si alguien escribe la ruta de una pantalla que no le corresponde, se le
  regresa a su pantalla de inicio.

## 4. Flujo de negocio del expediente

Estatus (viven solo en la app, en SQLite; nunca en SQL Server):

1. **Abierto** — el SP de SISE lo regresa cuando lleva **8 horas o más**
   abierto sin proveedor (antes de eso Core aún puede asignarlo solo).
2. **En Espera de Respuesta** — Cabina lo mandó al proveedor por correo.
3. **Seguimiento Proveedor** — el proveedor registró su seguimiento
   ("Actualizar Core"). Queda en solo lectura para él.
4. Desde ahí Cabina decide:
   - **Finalizado**.
   - **Regresar a Proveedor** (vuelve a En Espera) con comentario
     obligatorio, que se registra en Core y se avisa por correo.
   - **Seguimiento de Cita** (solo si es pago anticipado): cita aceptada,
     comentario obligatorio en Core y aviso por correo. El proveedor
     responde subiendo el comprobante de pago y vuelve a Seguimiento
     Proveedor.

**Pago anticipado:** el proveedor marca la casilla "¿Es un expediente de
pago anticipado?" antes de su primer comentario; después de ese envío ya
no se puede cambiar.

## 5. Pantallas

### 5.1 Inicio de sesión (por RFC)
- Paso 1: RFC. Se valida que esté autorizado y activo.
- Paso 2: si es su primera vez, **crea contraseña** (mínimo 8 caracteres,
  con mayúscula, minúscula, número y carácter especial) y la confirma; si
  ya tiene, la captura. Botón para mostrar/ocultar contraseña y liga
  "Cambiar RFC".
- Contraseñas con hash + salt (PBKDF2-SHA256). Token JWT propio de 8 horas.
- Recordar el último RFC en el navegador y saltar directo al paso 2.
- Logo de IKE a color con su lema sobre la tarjeta de login.

### 5.2 Expedientes (bandeja principal)
- **Indicadores (KPIs) clicables** que filtran la tabla:
  - Cabina: sin asignar (Abierto), en espera de respuesta, seguimiento
    proveedor, seguimiento de cita.
  - Proveedor: en espera de respuesta, seguimiento de cita.
  - Administrador: total y en proceso.
- **Filtros:** número de expediente, fecha inicio/fin (rango máximo de 3
  meses, ambas obligatorias si se usa una; por defecto los últimos 3
  meses), servicio y subservicio (en cascada), cuentas (multiselección con
  buscador, "Seleccionar todo" y "Limpiar"), entidad (solo Proveedor) y
  estado (oculto para Proveedor). Buscar por número de expediente ignora
  los demás filtros. `Enter` busca.
- Estado inicial del filtro: Cabina "Abierto"; Proveedor y Administrador
  "En Espera de Respuesta". El Proveedor solo ve "En Espera de Respuesta"
  y "Seguimiento de Cita" (y "Seguimiento Proveedor" si busca por número).
- **Tabla** paginada de 25 en 25, con encabezado fijo al hacer scroll y
  renglones alternos en azul suave. Columnas: #, casilla, Fecha Apertura,
  Expediente, Cuenta, Servicio, Subservicio (estas siete fijas al
  desplazar a la derecha), Titular, Paciente, Especialidad, Entidad,
  Municipio, Fecha Asignación Proveedor, Fecha Cita, Teléfono, Correo,
  Estado (badge de color). El número de expediente abre Seguimiento,
  excepto para el Administrador.
- **Acciones:** "Enviar correo a proveedores" (solo Cabina; pasa los
  seleccionados a En Espera) y "Generar corte" (solo Administrador).
- **Actualización automática cada 20 segundos** repitiendo la última
  búsqueda, con aviso cuando llega un expediente nuevo y, para Cabina y
  Administrador, cuando un proveedor responde ("El proveedor respondió:
  expediente X"). Aviso fijo para Cabina si hay respuestas por revisar.

### 5.3 Seguimiento de expedientes
- Buscador por número de expediente cuando se entra desde el menú.
- **Información General** (fondo azul como los renglones de la tabla):
  expediente, fecha de apertura, titular, paciente, entidad, municipio,
  teléfono, correo y la casilla de pago anticipado. La casilla se ve
  morada sin marcar y verde azulada marcada (todo el renglón, no solo el
  cuadro); solo el Proveedor puede cambiarla.
- **Comentarios del Proveedor** y **Comentarios del Coordinador**: cada
  comentario muestra arriba `Proveedores --> {nombre}` o
  `Cabina Médica --> {nombre}` (igual que en Core) con su fecha y hora, y
  abajo el texto. En pago anticipado, visor del comprobante (ver/descargar).
- **Estado del Caso** (solo Cabina): Abierto, Finalizado, Regresar a
  Proveedor, Seguimiento de Cita (solo si es pago anticipado). Regresar y
  Cita exigen comentario.
- **Registrar seguimiento** (solo Proveedor): observaciones con mínimo 50
  caracteres y contador; al marcar pago anticipado se agrega `PA-` al
  inicio del texto y al desmarcar se borra el comentario; si el
  expediente ya es pago anticipado el cuadro arranca con `PA-`. En
  "Seguimiento de Cita" el comprobante es obligatorio (PDF, JPG o PNG,
  máximo 5 MB, validando la firma real del archivo, no solo la
  extensión). Tras enviarse queda un aviso fijo de éxito y el formulario
  bloqueado.

### 5.4 Configuración Cuentas (Administrador)
- Buscador de cuentas en SISE con al menos 3 letras (solo letras), agregar
  y quitar cuentas de la lista configurada, y limpiar la lista.

### 5.5 Usuarios y Accesos (Administrador)
- Alta de acceso: RFC (4 letras + 6 números), nombre y perfil; para
  Proveedor además **entidad** (catálogo de las 32 entidades) y **correo**,
  obligatorios. La persona crea su contraseña en su primer ingreso.
- Lista con perfil, entidad, correo, estado y si ya creó contraseña, y
  acciones: inactivar/reactivar, resetear contraseña y cambiar entidad
  (modal) de un Proveedor.

### 5.6 Corte de expedientes (modal, Administrador)
- Solo con expedientes seleccionados que compartan el mismo estatus
  (validado también en el backend). Genera un Excel, lo guarda, muestra
  una vista previa, permite descargarlo y "Confirmar y enviar" por correo.

## 6. Integración con Core (SISE)

- Lo que se inserta con `dbo.ST_CP_RegistrarSeguimiento` en
  `dbo.Seguimiento.Observaciones` lleva este formato, con el nombre de
  quien inició sesión (tomado del token, nunca del formulario):
  ```
  Cabina Médica --> {nombre del coordinador}
  {comentario}

  Proveedores --> {nombre del proveedor}
  {comentario}          ← con "PA-" al inicio si es pago anticipado
  ```
- El backend garantiza el `PA-` en pago anticipado (lo agrega si falta,
  sin duplicarlo).
- `@Observaciones` es `NVARCHAR(1500)`: el límite del cuadro de texto debe
  descontar el encabezado, y el backend rechaza con mensaje claro lo que
  no quepa (nunca dejar que SQL Server lo corte en silencio).
- La copia local del comentario (la que muestra el portal) se guarda sin
  el encabezado; el nombre se obtiene de los accesos al consultarla.
- Cabina solo escribe en Core al regresar o aceptar la cita; finalizar no
  escribe en Core.

## 7. Stored Procedures

**Se crean** (scripts numerados en `sql/`, con un `sql/README.md` que
indique el orden):
1. `00_create_types.sql` — tipo `dbo.IntList`.
2. `dbo.ST_CP_ObtenerExpedientesSinProveedorMedico` — listado principal, con la
   regla de 8 horas de gracia (`@horasMinimas`), filtros por expediente,
   fechas, servicio, subservicio y cuentas (TVP).
3. `dbo.ST_CP_ObtenerCatalogoServicio` — combo Servicio.
4. `dbo.ST_CP_ObtenerCatalogoCuentas` — catálogo de cuentas, con lista fija
   opcional (`CUENTAS_PERMITIDAS` en `.env`).
5. `dbo.ST_CP_RegistrarSeguimiento` — inserta en `dbo.Seguimiento`
   (clExpediente, clEstatus=9, Observaciones, clUsrApp, Fecha).
6. `dbo.ST_CP_ObtenerExpedientesSinRespuestaProveedor` — para el job de alertas
   (`ProveedorxExpediente.clEstatus = 3` = asignación de proveedor).
7. `dbo.ST_CP_ObtenerServicioMedico` — combo Subservicio en cascada.

**Ya existen** en la base: `dbo.sp_S2_BuscaCuenta` (buscador de cuentas).

## 8. API REST

Todas exigen `Authorization: Bearer <token>`, salvo login y salud.

| Ruta | Uso |
|---|---|
| `POST /auth/rfc/estado`, `/auth/rfc/crear-password`, `/auth/rfc/login` | Inicio de sesión por RFC |
| `GET /expedientes` | Listado con filtros + estatus local |
| `POST /expedientes/enviar-correo-proveedores` | Envío a proveedores (Cabina) |
| `POST /expedientes/corte`, `GET /expedientes/corte/{id}/descargar`, `POST /expedientes/corte/{id}/enviar` | Corte en Excel (Administrador) |
| `GET /catalogos/servicios`, `/catalogos/subservicios`, `/catalogos/cuentas`, `/catalogos/cuentas/buscar` | Catálogos |
| `POST /seguimiento/actualizar` | Registrar seguimiento en Core (Proveedor) |
| `POST /seguimiento/estatus` | Cambiar estatus (Cabina; regresar/cita escriben en Core) |
| `GET /seguimiento/comentarios/{exp}` | Comentarios con nombre de quien escribió |
| `GET/POST /seguimiento/pago-anticipado/{exp}` | Casilla de pago anticipado |
| `POST /seguimiento/comprobante`, `GET /seguimiento/comprobante/{exp}`, `GET .../archivo` | Comprobante de pago |
| `GET/POST/DELETE /configuracion/cuentas`, `POST /configuracion/cuentas/limpiar` | Configuración de cuentas |
| `GET/POST /admin/accesos`, `GET /admin/accesos/entidades`, `POST /admin/accesos/{rfc}/inactivar` · `/reactivar` · `/resetear-password` · `/entidad` | Accesos (Administrador) |
| `GET /health` | Monitoreo, sin autenticación |

## 9. Seguridad

- `JWT_SECRET_KEY` obligatorio: la app no arranca con el valor de ejemplo.
- Límite de intentos en login: 10 cada 5 minutos por IP (y RFC), en
  memoria del proceso. La IP se toma de `X-Forwarded-For`; documentar que
  el proxy debe **reemplazar** ese encabezado con la IP real.
- Protección IDOR: un Proveedor solo puede leer comentarios, comprobantes
  y pago anticipado de expedientes en los estatus que le corresponden (En
  Espera de Respuesta, Seguimiento Proveedor y Seguimiento de Cita), aunque
  llame a la API directo con otro número.
- Validar la firma real de los archivos subidos; encabezado
  `X-Content-Type-Options: nosniff` en todas las respuestas.
- HTML escapado en correos y en todo lo que pinte el frontend.
- CORS configurable (solo para clientes externos) y explorador de GraphQL
  apagable para producción.
- `.env` y las bases `data/*.db` fuera del repositorio desde el primer
  commit.

## 10. Correo y job de alertas

- Correos: aviso a proveedores, aviso de regreso/cita al proveedor, envío
  del corte con el Excel adjunto y alertas del job. Si `SMTP_HOST` y
  `SMTP_REMITENTE` están vacíos, el envío queda **simulado** (solo se
  registra en el log) y la app funciona igual.
- **Job de alertas** (`jobs/validar_estatus_proveedor.py`): script que
  corre, revisa y termina; se programa cada hora (Programador de tareas en
  Windows, cron en Linux). Alerta **naranja** de 8 a 24 horas sin
  respuesta y **roja** de 24 horas o más; no repite alertas ya enviadas.

## 11. Arquitectura del frontend

```
frontend/
├── index.html          # solo el marco: login, menú lateral y barra superior
├── css/                # base.css (tokens y utilidades) · layout.css · componentes.css
├── img/                # logo de IKE (blanco para el menú, a color con lema) e ícono
└── js/
    ├── app.js          # arranque, sesión, menú por perfil y navegación por hash (#/pantalla)
    ├── core/           # api, sesión, router, catálogos, reglas de negocio, formato, avisos
    ├── componentes/    # tabla, filtros, multiselect, paginador, KPI, modal, campo numérico
    └── pantallas/      # un módulo por pantalla, con su HTML y su lógica
```

- Cada pantalla expone el mismo contrato: `montar(contenedor)`,
  `aplicarPermisos()`, `alEntrar()` y `reiniciar()`.
- Las pantallas no se importan entre sí para avisarse cambios: cuando una
  cambia el estatus de un expediente emite un evento y las demás
  actualizan sus datos en memoria.
- El botón "atrás" del navegador funciona y al recargar se conserva la
  pantalla.
- **Diseño:** paleta institucional (azul marino en el menú, azul de
  acción). Cada tarjeta lleva encabezado y borde en un tono suave
  (azul, verde azulado, morado, ámbar, verde) para que las secciones no
  se pierdan sobre el fondo; en Seguimiento cada sección tiene su tono y
  en las demás pantallas se alternan azul (formularios/filtros) y verde
  azulado (resultados/listas). Logo de IKE en blanco en el menú.
- **Formato de fechas:** siempre `aaaa-mm-dd` (y `aaaa-mm-dd HH:mm` con
  hora), sin depender del idioma del navegador; igual en el Excel.
- **Número de expediente:** campo de texto con teclado numérico, solo
  dígitos y máximo 10, sin flechas. Filtrar lo que se escriba o pegue en
  JavaScript, **sin** `maxlength` (el navegador cortaría lo pegado antes
  de limpiarlo y se perderían dígitos). En Seguimiento el campo mide lo
  justo para 10 dígitos.
- Debe verse bien en escritorio y en celular, sin scroll horizontal de la
  página.

## 12. Calidad y pruebas

- **pytest** sin SQL Server real: sustituir `call_procedure` por fakes y
  usar una SQLite temporal por prueba. Cubrir permisos por perfil, reglas
  de negocio, formato exacto de lo que llega a Core, límites, IDOR y que el
  portal se sirva en `/` sin tapar la API (y que los `.js` salgan como
  `text/javascript`).
- **Servidor de datos de prueba** (`dev_server_datos_prueba.py`): levanta
  el portal con datos inventados, sin SQL Server; sus fakes deben respetar
  los filtros como el SP real (por ejemplo, el filtro por número de
  expediente) y dar de alta solos los RFC de prueba al arrancar.
- **RFC de prueba** (`scripts/seed_usuarios_prueba.py`), con el mismo
  formato que exige el alta: `ADMI000001`, `CABI000001`, `PROV000001`
  (Proveedor con entidad y correo).
- Antes de dar por terminado un cambio de interfaz, probarlo en un
  navegador real con los tres perfiles.

## 13. Documentación y despliegue

- `README.md`: arquitectura, instalación en Windows y en Linux, cómo
  probar sin SQL Server, cómo está organizado el frontend y cómo agregar
  una pantalla, y despliegue.
- `sql/README.md` y `jobs/README.md` (Programador de tareas y cron).
- Requisitos de despliegue a documentar:
  - Un solo proceso de uvicorn (sin `--workers`), escuchando en
    `127.0.0.1:8000` detrás de un proxy con TLS (nginx o IIS).
  - Publicar en la raíz de un dominio, no en una subruta.
  - Zona horaria del servidor `America/Mexico_City` (la app guarda fechas
    con la hora local).
  - Respaldo del archivo SQLite (única copia de accesos, estatus,
    comentarios, comprobantes y cortes).
  - En Linux: `unixODBC` + `msodbcsql18`, autenticación SQL (no la
    integrada de Windows), servicio systemd y límite de carga de 6 MB en
    el proxy.

## 14. Forma de trabajo

- Avanza por fases que se puedan revisar: (1) estructura y conexión,
  (2) login y accesos, (3) Expedientes, (4) Seguimiento y Core,
  (5) Administración y corte, (6) correo y job, (7) documentación y
  despliegue. Al cerrar cada fase: pruebas en verde y un commit.
- Mensajes de commit en español, describiendo el porqué.
- Nunca subir (push) sin confirmarlo conmigo, y revisar antes que no vaya
  nada sensible.
- Si algo del negocio no está claro, pregúntame antes de suponer; deja
  los supuestos explícitos en el README.

## 15. Pendientes por confirmar

- Datos del servidor SMTP y del remitente, y de dónde sale el correo real
  del proveedor.
- Si la lista fija de cuentas permitidas fue solo para el piloto.
- Si el `LEFT JOIN` a `dbo.CitaxExpediente` del listado principal se puede
  quitar.
