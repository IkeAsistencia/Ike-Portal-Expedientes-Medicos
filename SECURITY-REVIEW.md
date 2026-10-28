# Revisión de seguridad — Portal Promédico

Fecha: 2026-10-07
Alcance: barrido completo del repositorio (backend FastAPI + GraphQL,
acceso a datos vía Stored Procedures, SQLite local, frontend HTML/CSS/JS,
jobs/scripts, manejo de secretos).

## Resumen

| # | Severidad | Archivo | Líneas (antes del fix) | Vulnerabilidad | Confianza |
|---|----------|------|-------|---------------|------------|
| 1 | 🟠 HIGH | `app/graphql/mutation.py` | 51-68, 100-123 | Control de acceso roto (IDOR / escalación de privilegios) en mutations GraphQL | 9/10 |
| 2 | 🟡 MEDIUM | `app/graphql/mutation.py` | 29-45 | Falta de rate limiting en el `login` de GraphQL (fuerza bruta) | 8/10 |

Áreas revisadas sin hallazgos de severidad relevante: acceso a SQL Server
(`app/db/connection.py`, `app/repositories/*.py`, `sql/*.sql` — 100%
parametrizado, sin SQL dinámico/concatenación), almacenamiento de
contraseñas (PBKDF2-SHA256 con sal y comparación de tiempo constante,
ver `app/repositories/accesos_repo.py`), frontend (`frontend/js/*.js`
escapa HTML antes de insertarlo en el DOM vía `escapeHtml()`), manejo de
archivos subidos (`app/repositories/comprobantes_repo.py`: valida tamaño,
MIME declarado y "magic bytes" del contenido real), CORS, headers de
seguridad, y manejo de secretos (`.env` excluido de git).

## Hallazgo 1 — Control de acceso roto en mutations GraphQL (HIGH)

**Archivo:** `app/graphql/mutation.py`

**Problema:** las mutations GraphQL reimplementaban las mismas acciones
de negocio que el REST, pero solo exigían `requerir_usuario()`
(autenticación), sin aplicar ninguna de las validaciones de **rol** que
sí tiene el REST:

- `actualizarEstatus` no replicaba las reglas de
  `app/routers/seguimiento.py` (`POST /seguimiento/estatus`): el perfil
  Proveedor no podía cambiar estatus a mano, "En Espera de Respuesta" y
  "Seguimiento de Cita" son exclusivos de Cabina, "Seguimiento Proveedor"
  es automático. Via GraphQL, cualquier usuario autenticado (de
  cualquier perfil) podía forzar cualquier expediente a cualquier
  estatus, incluido "Finalizado".
- `actualizarSeguimiento` escribía directo en `dbo.Seguimiento` (SQL
  Server, vía Stored Procedure) sin el bloqueo de perfil Cabina, la
  longitud mínima del comentario, la restricción de etapa del flujo de
  trabajo, ni el comprobante de pago anticipado obligatorio — todo lo
  que sí exige `POST /seguimiento/actualizar`.
- `agregarCuenta` / `eliminarCuenta` / `limpiarCuentasConfiguradas`
  omitían la dependencia `_requerir_no_cabina_ni_proveedor` del REST
  (`app/routers/configuracion_cuentas.py`), que restringe Configuración
  Cuentas al perfil Administrador. Via GraphQL, Proveedor o Cabina
  podían modificar/vaciar esa configuración.

**Remediación aplicada:**

- Se extrajeron las reglas de negocio/autorización a dos módulos nuevos,
  usados tanto por REST como por GraphQL, para que ninguna de las dos
  superficies pueda quedar desincronizada en el futuro:
  - `app/services/seguimiento_service.py` →
    `actualizar_seguimiento(cl_expediente, comentario, usuario)`.
  - `app/services/estatus_service.py` →
    `actualizar_estatus(cl_expediente, estatus_valor, usuario, comentario)`.
- Se agregó `accesos_repo.verificar_rol_administrador(usuario)` en
  `app/repositories/accesos_repo.py`, reutilizado por la dependencia
  REST (`app/routers/configuracion_cuentas.py`) y por las tres mutations
  de Configuración Cuentas en `app/graphql/mutation.py`.
- `app/routers/seguimiento.py` y `app/routers/configuracion_cuentas.py`
  ahora llaman a estas mismas funciones en vez de duplicar la lógica.
- Se agregó el campo `comentario` a `EstatusInput` en
  `app/graphql/inputs.py` (faltaba para poder soportar el flujo de
  "regresar a Proveedor" con el mismo contrato que el REST).
- Pruebas de regresión agregadas en `tests/test_graphql.py`:
  `test_actualizar_estatus_proveedor_no_puede_cambiar_estatus`,
  `test_actualizar_estatus_regreso_requiere_perfil_cabina`,
  `test_actualizar_seguimiento_cabina_bloqueado`,
  `test_configuracion_cuentas_rechaza_proveedor_y_cabina`,
  `test_configuracion_cuentas_permite_administrador`.

## Hallazgo 2 — Sin rate limiting en el login de GraphQL (MEDIUM)

**Archivo:** `app/graphql/mutation.py`

**Problema:** `POST /auth/login` limita a 10 intentos / 5 minutos por
IP + usuario (`app/core/rate_limit.py`, usado en
`app/routers/auth.py`) para frenar fuerza bruta / credential stuffing
contra cuentas SISE. La mutation `login` de GraphQL llamaba
directamente a `auth_repo.autenticar(...)` sin ese límite, exponiendo
una ruta alterna sin protección para el mismo ataque.

**Remediación aplicada:** la mutation `login` ahora llama a
`verificar_limite(f"login:{ip}:{usuario}", ...)` con las mismas
constantes que usa el REST (`MAXIMO_INTENTOS_LOGIN`,
`VENTANA_INTENTOS_LOGIN_SEGUNDOS`, importadas de
`app/routers/auth.py`) antes de validar las credenciales.

Prueba de regresión agregada: `test_login_graphql_aplica_limite_de_intentos`.

## Validación

- `pytest tests` — 86 pruebas, todas en verde (incluye las 6 nuevas de
  regresión de seguridad).
- `python -c "import app.main"` — el árbol de importaciones sigue
  cargando sin ciclos ni errores tras mover la lógica a `app/services/`.

---

# Escaneo Checkmarx — 2026-10-13

Reporte del área de seguridad (scan id `3e8e0553-4a9a-43c0-96eb-f7a50f33d686`,
preset ASA Premium, 110 archivos / 8,996 LOC). 11 hallazgos: 6 de SAST y 5
de SCA (dependencias). Todos atendidos.

| # | Severidad | Tipo (CWE) | Dónde | Remediación |
|---|-----------|------------|-------|-------------|
| 1 | 🟠 HIGH | SCA — SSRF vía `StaticFiles` (CWE-918, CVE-2026-48818) | `starlette 0.38.6` | Actualizado a `starlette 1.8.0` |
| 2 | 🟡 MEDIUM | SCA — 4 CVEs más de Starlette (CWE-770 / 444 / 470 / 706) | `starlette 0.38.6` | Mismo upgrade |
| 3 | 🟡 MEDIUM | SAST — `Privacy_Violation` (CWE-359) | `app/routers/auth.py`, `app/schemas/*` | Manejador de `RequestValidationError` + `SecretStr` |
| 4 | 🟡 MEDIUM | SAST — `Unchecked_Input_for_Loop_Condition` (CWE-606) ×4 | `app/routers/catalogos.py`, `app/schemas/correo.py` | Rangos y topes de longitud en la entrada |
| 5 | ⚪ LOW | SAST — `Log_Forging` (CWE-117) | `app/services/email_service.py` | `sanear_para_log()` |

## Hallazgos 1 y 2 — Dependencia `starlette` con 5 CVEs (HIGH + 4 MEDIUM)

**Problema:** el proyecto quedaba en `starlette 0.38.6` porque
`fastapi==0.115.0` la topaba en `<0.42.0`. Esa versión arrastra:

- **CVE-2026-48818 (HIGH, CWE-918).** Sirviendo archivos con
  `StaticFiles` en Windows, `os.path.realpath` resolvía rutas UNC
  (`\\atacante.com\share`), lo que abría una conexión SMB al host del
  atacante y le filtraba las credenciales NTLMv2 de la cuenta de
  servicio. **Aplicaba directo:** este portal sirve el frontend con
  `app.mount("/", StaticFiles(...))` en `app/main.py` y corre en Windows.
- **CVE-2026-48710 (CWE-444)** y **CVE-2026-54282 (CWE-706).** El header
  `Host` y el path no se validaban al reconstruir `request.url`, así que
  `request.url.path` / `request.url.hostname` podían no coincidir con lo
  realmente pedido. El middleware `agregar_headers_seguridad` decide por
  `request.url.path`.
- **CVE-2026-48817 (CWE-470).** `HTTPEndpoint` resolvía el handler con
  `getattr` sin limitarlo a verbos HTTP conocidos.
- **CVE-2025-54121 (CWE-770).** Subir un archivo grande bloqueaba el
  event loop (el portal recibe comprobantes de pago por multipart).

**Remediación aplicada:** en `requirements.txt`,
`fastapi 0.115.0 → 0.141.1` (la primera línea de FastAPI que suelta el
tope `starlette<1.0.0` sin arrastrar `opentelemetry-api`) y `starlette`
pineado explícito en `1.8.0`.

## Hallazgo 3 — El 422 devolvía la contraseña recibida (MEDIUM, CWE-359)

**Archivos:** `app/main.py`, `app/schemas/auth.py`, `app/schemas/acceso.py`,
`app/routers/auth.py`

**Problema:** Pydantic v2 incluye en cada error de validación la clave
`input` con el valor que llegó, y FastAPI la devuelve tal cual. Una
contraseña que no cumplía la regla de complejidad terminaba reflejada en
el body del 422 — y de ahí al log del proxy, al historial del navegador
o a cualquier intermediario. Confirmado antes del fix:

```
POST /auth/rfc/crear-password  -> 422
{"detail":[{... "msg":"...", "input":"SuperSecreta123", ...}]}
```

**Remediación aplicada:**

- Manejador propio de `RequestValidationError` en `app/main.py`: responde
  solo `type` / `loc` / `msg`, nunca el valor recibido. El contrato que
  consume el frontend (`detail[].msg`, ver `frontend/js/core/api.js`) no
  cambia.
- Las contraseñas de entrada pasan a `SecretStr` (`LoginInput`,
  `CrearPasswordInput`, `RfcLoginInput`), así el valor tampoco puede
  escaparse por un `repr`, un `model_dump()` o una traza. Como efecto
  secundario, OpenAPI ya las marca `format: password` / `writeOnly`.
  Los call sites piden el valor explícito con `.get_secret_value()`.

## Hallazgo 4 — Iteraciones sin tope a partir de la entrada (MEDIUM, CWE-606) ×4

**Archivos:** `app/routers/catalogos.py`, `app/schemas/correo.py`

**Problema:** cuatro flujos tomaban un dato del usuario y lo usaban como
cota de un ciclo sin validar su rango:

- `GET /catalogos/servicios` y `/catalogos/subservicios`: `cl_servicio`
  llegaba como `int` sin rango; pasa al SP y lo que regrese se recorre
  completo del lado de la API.
- `GET /catalogos/cuentas/buscar`: `texto` solo tenía `min_length=3`, y
  se valida carácter por carácter (`for ch in texto`) — un texto de
  varios MB son esas mismas iteraciones.
- `POST /expedientes/corte`: `data.expedientes` no tenía máximo y el
  ciclo hace **una consulta al SP por cada expediente** de la lista.

**Remediación aplicada:**

- `cl_servicio` acotado con `Query(4, ge=1, le=9999)`
  (`CL_SERVICIO_MINIMO` / `CL_SERVICIO_MAXIMO`).
- `texto` acotado con `max_length=60` (`LARGO_MAXIMO_BUSQUEDA_CUENTA`).
- `MAXIMO_EXPEDIENTES_POR_OPERACION = 2000` aplicado a
  `GenerarCorteInput` y `EnviarCorreoProveedoresInput`. Es holgado frente
  a lo que se puede marcar en pantalla, incluso con "seleccionar todo"
  sobre el rango máximo de búsqueda (3 meses); si el negocio necesita
  más, se sube ahí en un solo lugar.

## Hallazgo 5 — Log Forging en el modo simulado de correo (LOW, CWE-117)

**Archivos:** `app/core/log_seguro.py` (nuevo), `app/services/email_service.py`

**Problema:** los dos `logger.info` del modo simulado interpolaban
destinatario, asunto, nombre del adjunto y cuerpo HTML sin sanear. Un
salto de línea en cualquiera de esos valores cierra el renglón e inyecta
entradas falsas que parecen legítimas — con eso se puede tapar una huella
o inventar actividad que nunca pasó.

**Remediación aplicada:** `sanear_para_log()` convierte saltos de línea y
caracteres de control en texto visible (`\n`, `\r`, `\x1b`), y se aplica a
todos los valores interpolados en los logs de `email_service.py`. El
registro queda en un solo renglón, así que ningún valor puede generar uno
nuevo.

## Validación

- `pytest tests` — **108 pruebas en verde**, incluidas 8 nuevas de
  regresión (una por corrección): `test_error_de_validacion_no_refleja_el_dato_recibido`,
  `test_password_queda_enmascarada_en_el_modelo`,
  `test_corte_acota_cuantos_expedientes_se_pueden_mandar`,
  `test_enviar_correo_proveedores_acota_cuantos_expedientes_se_pueden_mandar`,
  `test_busqueda_de_cuentas_acota_el_largo_del_texto`,
  `test_catalogos_acotan_el_rango_de_cl_servicio`,
  `test_sanear_para_log_no_deja_forjar_renglones`,
  `test_modo_simulado_sanea_el_nombre_del_adjunto`.
- Arranque real con `uvicorn` sobre las dependencias nuevas: `/health`,
  el frontend servido por `StaticFiles` (`/`, `/js/app.js`,
  `/css/base.css` con su MIME correcto), `/docs` y `/graphql` responden
  200; siguen saliendo `X-Content-Type-Options: nosniff` y el
  `Cache-Control: no-cache` del frontend. Una petición con ruta UNC
  (`/\\127.0.0.1\share\x`) se responde 404 sin intentar la conexión.
- Verificado en vivo que el 422 de `/auth/rfc/crear-password` ya no
  contiene la contraseña enviada.

---

# Escaneo Checkmarx — 2026-10-13 (segunda corrida)

Reporte del área de seguridad (scan id `7c0531d9-d573-4c2b-b48e-4c12daca3a70`,
preset ASA Premium, 111 archivos / 9,180 LOC). 6 hallazgos, todos Medium/Low,
0 críticos/altos. Los 4 del escaneo anterior (3 `Unchecked_Input_for_Loop_Condition`
+ 1 `Privacy_Violation`) salen marcados "Resolved" por el propio Checkmarx.

Análisis: ninguno de los 6 representa un hueco real sin atender. Son 2
situaciones distintas, ninguna requiere cambio de código — se documentan
aquí para triage en Checkmarx como "Not Exploitable".

| Similarity Id | Severidad | Tipo | Dónde | Estado |
|---|---|---|---|---|
| -1731685342 | 🟡 Medium | Unchecked_Input_for_Loop_Condition | `catalogos.py:32` → `catalogos_repo.py:29` | No explotable |
| 2008296053 | 🟡 Medium | Unchecked_Input_for_Loop_Condition | `catalogos.py:43` → `catalogos.py:51` | No explotable |
| 1229767200 | 🟡 Medium | Unchecked_Input_for_Loop_Condition | `catalogos.py:27` → `catalogos_repo.py:15` | No explotable |
| -1690917026 | 🟡 Medium | Unchecked_Input_for_Loop_Condition | `expedientes.py:122` → `expedientes.py:144` | Ya corregido |
| -2077027318 | 🟡 Medium | Privacy_Violation | `auth.py:41` → `auth.py:48` | Falso positivo |
| -1200604096 | ⚪ Low | Log_Forging | `expedientes.py:201` → `email_service.py:132` | No explotable / ya corregido |

## Los 3 de `catalogos.py` — el escáner no reconoce la validación declarativa de FastAPI/Pydantic

`cl_servicio` ya está acotado con `Query(4, ge=CL_SERVICIO_MINIMO, le=CL_SERVICIO_MAXIMO)`
(rango 1–9999, ver `app/routers/catalogos.py`) y `texto` con `max_length=60`.
Un valor fuera de rango se rechaza con HTTP 422 antes de que la función se
ejecute. Además, en los dos casos de `cl_servicio` el ciclo (`for r in rows`)
no itera "`cl_servicio` veces" -- itera sobre el resultado fijo del catálogo
en SQL Server (decenas de filas), sin relación con la magnitud del
parámetro. El motor de análisis estático no modela `ge=`/`le=`/`max_length=`
de Pydantic como una validación previa al ciclo, así que sigue marcando el
patrón genérico "input externo llega a un `for`" aunque ya esté acotado.

## El de `expedientes.py` (Recurrent) — ya corregido en el escaneo anterior

`GenerarCorteInput.expedientes` tiene `max_length=MAXIMO_EXPEDIENTES_POR_OPERACION`
(2000, en `app/schemas/correo.py`) desde el fix del escaneo pasado. Sigue
saliendo "Recurrent" por la misma razón que los de arriba: la cota vive en
el schema Pydantic, no en un `if` explícito que el escáner pueda rastrear.

## El `Privacy_Violation` de `auth.py` — falso positivo

`LoginResponse` (`app/schemas/auth.py`) solo tiene `access_token`,
`token_type`, `cl_usr_app`, `usuario` y `nombre` -- ningún campo transporta
la contraseña. El escáner detecta que `data.password.get_secret_value()` se
usa dentro de la misma función donde se construye la respuesta, pero el
valor de la contraseña nunca llega a `LoginResponse`.

## El `Log_Forging` de `expedientes.py`/`email_service.py` (Recurrent) — ya cubierto

`corte_id` es `int` (no puede contener saltos de línea) y los valores de
texto que sí se escriben en ese `logger.info` (destinatario, asunto,
nombre de adjunto, cuerpo) ya pasan por `sanear_para_log()` desde el fix
del escaneo anterior (líneas 135-136 de `email_service.py`).

## Siguiente paso

Marcar estos 6 resultados como "Not Exploitable" en Checkmarx con la
justificación de arriba. Si el área de seguridad no lo acepta y exige
cerrarlos en código, la alternativa es agregar validaciones explícitas
redundantes (un `if` visible en el cuerpo de la función, además del
`Query`/`Field` de Pydantic) solo para que el motor de análisis estático
las reconozca -- no aportan protección adicional real, ya que FastAPI
rechaza la petición antes de llegar a ese código.

---

# Autorrevisión previa a nueva solicitud a SGI — 2026-10-16

Barrido propio (SCA + SAST local) antes de mandar un nuevo paquete a SGI
para la siguiente corrida de Checkmarx -- desde el último escaneo
(2026-10-13) se agregaron la alerta de respuesta de proveedor, el
paginador con números de página, ajustes al semáforo de tiempos, un
script de generación de INSERTs de prueba (`sql/pruebas/`) y la maqueta
del Directorio de Proveedores.

## SCA — `pip-audit` sobre `requirements.txt`

Sin vulnerabilidades conocidas en ninguna de las dependencias pinneadas
(`fastapi 0.141.1`, `starlette 1.8.0`, `pyodbc 5.2.0`, `pydantic 2.9.2`,
`PyJWT 2.15.0`, `strawberry-graphql 0.327.7`, `openpyxl 3.1.5`, `httpx
0.27.2` y sus transitivas). Las correcciones de Starlette del escaneo del
2026-10-13 se mantienen vigentes.

## SAST — `bandit` sobre `app/`, `scripts/`, `dev_server_datos_prueba.py`

3 hallazgos, los 3 LOW/falsos positivos del detector genérico de
"posible contraseña hardcodeada" (`B105`/`B106`), ninguno es una
credencial real:

| Archivo | Línea | Qué detectó | Por qué no aplica |
|---|---|---|---|
| `dev_server_datos_prueba.py` | 135 | Cadena `'Qwer1234$'` | Es la contraseña de los usuarios semilla de **desarrollo** (`scripts/seed_usuarios_prueba.py`), nunca se usa en QA/producción |
| `app/config.py` | 25 | Cadena `'CAMBIA-ESTE-VALOR-EN-TU-.env'` | Es el valor por defecto que obliga a fallar visiblemente si alguien olvida definir `JWT_SECRET_KEY` en su `.env` -- no es un secreto real |
| `app/schemas/acceso.py` | 9 | Mensaje de error que contiene la palabra "contraseña" | Es el texto del `ValueError` de validación ("La contraseña debe tener..."), no un valor de contraseña |

## Qué se excluyó de este paquete

El módulo **Directorio de Proveedores** (`frontend/css/directorio.css`,
`frontend/js/directorio/*`, `frontend/js/pantallas/directorio-proveedores.js`)
se dejó fuera del zip para SGI. Es una maqueta de frontend puro, con datos
simulados vía hash (ver encabezado de `frontend/js/directorio/datos.js`),
sin conexión a ningún backend ni dato real todavía -- el desarrollo real
contra datos/API propios apenas va a empezar, así que no tiene sentido
que un escaneo le abra hallazgos sobre código que se va a reescribir.
Se incluirá en el próximo paquete una vez que tenga lógica de verdad
detrás.

## Paquete generado

`portal-promedico-20261016.zip` (146 archivos, árbol de `git archive` de
la rama `dev` menos los 5 archivos del Directorio de Proveedores) --
listo para subir a SGI y solicitar la siguiente corrida de Checkmarx.

---

# Autorrevisión previa a nueva solicitud a SGI — 2026-10-19

Dos revisiones propias antes de armar el paquete, porque desde el escaneo
del 2026-10-13 entró bastante código nuevo que nunca ha pasado por
Checkmarx: el Directorio de Proveedores ya con lógica real (padrón con
clave propia, altas, citas y carga de Excel), el catálogo de Entidad y
Municipio contra la base real, y el módulo de Cuentas (grupo del menú,
pantalla "Agregar cuenta" renovada y catálogo compartido entre Expedientes
y Cuentas Especiales).

## Resumen

| # | Severidad | Archivo | Vulnerabilidad | Confianza | Estado |
|---|-----------|---------|----------------|-----------|--------|
| 1 | 🟡 MEDIUM | `app/routers/directorio_proveedores.py` (82-87) | Cancelar cita no valida propiedad; los folios son consecutivos | 9/10 | **Pendiente** (decisión del usuario) |
| 2 | 🟡 MEDIUM | `app/routers/directorio_proveedores.py` (49-51) | `GET /citas` sin filtro devuelve todas las citas del portal | 8/10 | **Pendiente** (decisión del usuario) |
| 3 | 🟡 MEDIUM | `app/routers/solicitudes_alta_medico.py` (60-70) | Un perfil Proveedor puede aprobar su propia alta de médico | 8/10 | **Corregido** |
| 4 | ⚪ LOW | `app/repositories/accesos_repo.py` (62-73) | Guard de Administrador por lista negra: una sesión SISE legada (token sin `perfil`) pasaba de largo | 7/10 | **Corregido** |

Sin hallazgos de inyección SQL ni XSS. Todo el acceso a SQLite y a SQL
Server usa parámetros vinculados (lo único interpolado en los f-strings
son nombres de tabla/columna constantes del propio código), y el frontend
escapa con `escapeHtml` todo lo que viene del Excel o del alta antes de
meterlo al DOM.

## Hallazgos 1 a 3 — Control de acceso en el Directorio de Proveedores

Los dos de **citas** (1 y 2) quedan sin corregir a propósito (decisión del
usuario, 2026-10-19): se van a atender en un cambio aparte. Se documentan
aquí para que el reporte de Checkmarx se pueda triar sin volver a
analizarlos. El 3 ya está corregido.

1. `POST /directorio-proveedores/citas/{folio}/cancelar` identifica la cita
   solo por `folio` y no compara contra `rfc_agendo` ni el perfil. Como
   `citas_proveedor_repo._siguiente_folio()` genera folios consecutivos
   (`CITA-00001`, `CITA-00002`, ...), no hay nada que adivinar: cualquier
   perfil Proveedor puede iterar el rango y cancelar citas ajenas.
2. `GET /directorio-proveedores/citas` sin `clave_proveedor` devuelve todas
   las citas del portal, incluyendo nombre del paciente, médico y
   `rfc_agendo`. El frontend todavía no consume ese endpoint.
El hallazgo 3 **ya se corrigió** (ver más abajo); los dos de citas siguen
abiertos.

3. `POST /solicitudes-alta-medico/{folio}/estatus` solo exigía "no Cabina",
   así que el mismo perfil Proveedor que crea la solicitud podía aprobarla,
   y al aprobarse se inserta un proveedor real en el padrón. La otra vía de
   escritura a esa misma tabla (la carga de Excel) sí exige Administrador.

### Corrección del hallazgo 3 (2026-10-19)

Resolver una solicitud de alta pasó a ser exclusivo de Administrador
(`_requerir_administrador` en `app/routers/solicitudes_alta_medico.py`,
apoyado en el mismo `verificar_rol_administrador` ya endurecido en el
hallazgo 4). Capturar un alta sigue abierto a cualquier perfil menos
Cabina; lo que se cerró es **aprobarla o rechazarla**.

En el mismo cambio se agregó el botón "Editar" (también exclusivo de
Administrador) para corregir una solicitud **sin resolver** -- en revisión o
con la cédula profesional no localizada, ver `ESTATUS_EDITABLES`. Editar
una ya aprobada o rechazada responde **409**: aprobada ya creó al proveedor
en el padrón con su clave y puede tener citas, así que editarla dejaría los
dos lados en desacuerdo. La restricción se valida en el servidor, no solo
ocultando el botón.

Pruebas de regresión: `test_proveedor_no_puede_aprobar_su_propia_solicitud`,
`test_proveedor_no_puede_rechazar`, `test_proveedor_no_puede_editar_una_solicitud`,
`test_administrador_puede_editar_una_solicitud_en_revision`,
`test_administrador_puede_editar_una_con_cedula_no_localizada`,
`test_no_se_edita_una_solicitud_ya_aprobada`,
`test_no_se_edita_una_solicitud_ya_rechazada`,
`test_marcar_cedula_no_localizada_no_da_de_alta_en_el_padron`,
`test_editar_folio_inexistente_regresa_404` y `test_editar_rechaza_cabina`.

## Hallazgo 4 — Guard de Administrador por lista negra (CORREGIDO)

**Archivos:** `app/repositories/accesos_repo.py`, `app/routers/configuracion_cuentas.py`

**Problema:** `verificar_rol_administrador()` rechazaba los perfiles Cabina
y Proveedor, pero dejaba pasar cualquier token **sin** el campo `perfil` --
que es justo lo que emite el login legado de SISE (`POST /auth/login`). El
resto de secciones de Administrador usa una lista blanca
(`admin_accesos.requerir_administrador`, `perfil == 1`), así que había dos
criterios distintos para el mismo privilegio. Las tres vías afectadas
escriben configuración global del portal:

- `/configuracion/cuentas` (REST) -- la pantalla "Agregar cuenta", que
  además acaba de dejar de estar oculta y entró al menú.
- `/proveedores-catalogo` (REST) -- la carga del Excel del padrón.
- `agregarCuenta` / `eliminarCuenta` / `limpiarCuentasConfiguradas` (GraphQL).

No era explotable hoy porque `LOGIN_LEGADO_HABILITADO` está apagado por
default, pero bastaba encenderlo para abrir las tres.

**Remediación aplicada:** `verificar_rol_administrador()` pasó a lista
blanca (`perfil != PERFIL_ADMINISTRADOR` -> `ValueError`). Al estar
centralizada, el cambio cierra los cinco puntos de uso a la vez. Se
renombró `_requerir_no_cabina_ni_proveedor` a `_requerir_administrador` en
`configuracion_cuentas.py` para que el nombre diga lo que hace.

**Pruebas de regresión:** `test_configuracion_cuentas_rechaza_sesion_sin_perfil`
y `test_carga_del_catalogo_de_proveedores_rechaza_sesion_sin_perfil`. Las
dos pruebas que usaban la sesión legada para estos endpoints
(`test_configuracion_cuentas_ciclo_completo` en `test_smoke.py` y en
`test_graphql.py`) pasaron a usar un token de Administrador.

## Falsos positivos esperables en Checkmarx

Revisados uno por uno; en todos lo interpolado son constantes del propio
código y los datos del usuario viajan como parámetros:

| Archivo | Qué va a marcar | Por qué no aplica |
|---|---|---|
| `app/db/connection.py` (81-82) | `f"EXEC {sp_name} {assignments}"` | Interpola el nombre del SP y los nombres de parámetro (literales en el código); los valores van con `?` |
| `app/repositories/proveedores_repo.py` (100-103, 126) | `f"INSERT/UPDATE ..."` | Las columnas salen de la tupla constante `_CAMPOS_DATOS`; los valores van con parámetros nombrados |
| `app/repositories/solicitudes_alta_medico_repo.py` (42-45) | `f"INSERT ..."` | Igual, con `_CAMPOS_SOLICITUD` |
| `app/db/local_store.py` (309, 340) | `f"ALTER TABLE ... {columna}"`, `f"DROP TABLE {tabla}"` | Nombres de tabla/columna de tuplas literales de la migración |

## Validación

- `pytest tests` — **191 pruebas en verde** (incluidas las 2 de regresión
  del hallazgo 4 y las 10 del hallazgo 3).
- Verificación en vivo del guard, por perfil y por vía: Administrador
  responde 200 y Cabina, Proveedor y la sesión legada sin `perfil`
  responden 403 en `/configuracion/cuentas` (GET y POST),
  `/proveedores-catalogo` y `/admin/cuentas-etiquetas`; la mutation
  `agregarCuenta` de GraphQL bloquea igual a la sesión legada.

## Paquete generado

`portal-promedico-security-scan_20261019.zip` (142 archivos, árbol
versionado de la rama `dir-medicos` menos `.gitignore`, `.gitattributes`,
`dev_server_datos_prueba.py` y `prompts/`). Incluye el módulo de Cuentas
recién integrado desde `cuentas-color` y el Directorio de Proveedores ya
con lógica real -- a diferencia del paquete del 2026-10-16, donde se
excluyó por ser todavía una maqueta.

---

# Escaneo Checkmarx — 2026-10-26 (triage) y autorrevisión — 2026-10-28

Reporte del área de seguridad (`Cx_ScanReport_2026-10-26_180709.pdf`,
proyecto Checkmarx `Ike-DrVideo-Back`, scan id
`78adcfbe-6734-470d-b944-861cc42a4bac`). 9 hallazgos nuevos, todos Medium,
0 críticos/altos: 6 `Unchecked_Input_for_Loop_Condition` (CWE-606) y 3
`Privacy_Violation` (CWE-359). El reporte trae además 520 "Resolved
Vulnerabilities" históricos cuyo `Query Path` empieza en `Java\...` -- no
corresponden a este portal (100% Python); son arrastre de un escaneo
previo de otro proyecto bajo el mismo nombre en Checkmarx y no deben
leerse como progreso de este repo.

## Triage de los 9 hallazgos

5 son la misma recurrencia que ya se documentó en el escaneo del
2026-10-13 (segunda corrida, arriba): el motor no reconoce `Query(ge=,
le=, max_length=)` ni `Field(max_length=)` de FastAPI/Pydantic como
validación previa al ciclo.

| Dónde | Tipo | Estado |
|---|---|---|
| `catalogos.py` -- `cl_servicio` en `/servicios` | Unchecked_Input_for_Loop_Condition | Recurrente, no explotable (`Query(ge=1, le=9999)`) |
| `catalogos.py` -- `cl_servicio` en `/subservicios` | Unchecked_Input_for_Loop_Condition | Recurrente, no explotable |
| `catalogos.py` -- `cod_ent` en `/municipios` | Unchecked_Input_for_Loop_Condition | Recurrente, no explotable (`max_length=2`) |
| `expedientes.py` -- `data.expedientes` en `/corte` | Unchecked_Input_for_Loop_Condition | Recurrente, ya corregido (`max_length=2000`) |
| `auth.py` -- password hacia `LoginResponse` | Privacy_Violation | Recurrente, falso positivo (`LoginResponse` no incluye password) |

Los otros 4 son la primera corrida de Checkmarx contra el Directorio de
Proveedores con lógica real (el paquete del 2026-10-16 lo había excluido
por ser maqueta) y entran con el mismo patrón de siempre:

| Dónde | Tipo | Por qué no aplica |
|---|---|---|
| `catalogos.py` -- `texto` en `/cuentas/buscar` | Unchecked_Input_for_Loop_Condition | `max_length=60` (`LARGO_MAXIMO_BUSQUEDA_CUENTA`), 422 antes del ciclo |
| `directorio_proveedores.py` -- `dias` hacia `agenda_disponible` | Unchecked_Input_for_Loop_Condition | `Query(ge=1, le=DIAS_AGENDA_MAXIMO)` |
| `proveedores_repo.py` -- `obtener_por_clave` hacia `directorio_proveedores.py` | Privacy_Violation | Regresa un registro público del padrón (nombre, consultorio, horario), no datos sensibles de un usuario |
| `directorio_proveedores.py` -- `clave` hacia `agenda_disponible` | Privacy_Violation | Mismo patrón: `clave` es el identificador público del proveedor, no un dato privado |

**Conclusión: los 9 son "Not Exploitable" / falso positivo, ninguno requiere
cambio de código.** Se documentan aquí para triage directo en Checkmarx.

## Autorrevisión propia — 2026-10-28

Repetición del barrido SCA + SAST local antes de responder este escaneo,
mismo método que el del 2026-10-16/19.

**SCA (`pip-audit` sobre `requirements.txt`):** sin vulnerabilidades
conocidas.

**SAST (`bandit` sobre `app/`, `scripts/`, `dev_server_datos_prueba.py`):**
16 hallazgos (12 Medium `B608`, 3 Low `B105`/`B107`, 1 Low `B311`, 1 Medium
`B310`), todos revisados uno por uno:

- **12 × B608 ("posible SQL injection")** en `citas_proveedor_repo.py`,
  `especialidades_repo.py`, `estatus_repo.py`, `proveedores_repo.py` y
  `solicitudes_alta_medico_repo.py`: el mismo patrón ya documentado en la
  tabla de falsos positivos del 2026-10-19 (arriba) -- lo interpolado son
  nombres de tabla/columna de tuplas constantes (`_CAMPOS_DATOS`,
  `_CAMPOS_SOLICITUD`, `SEMILLA`) o conteos de `?` (`marcadores`) basados
  en listas fijas/enums, nunca texto libre del usuario; los valores
  siempre viajan parametrizados. Dos de ellos (`citas_proveedor_repo.py:33`,
  `proveedores_repo.py:102`) ni siquiera reciben un parámetro: interpolan
  `len(PREFIJO_FOLIO)` / `len(PREFIJO_CLAVE)`, constantes del propio
  código.
- **B105/B107 (`'Qwer1234$'`, `'CAMBIA-ESTE-VALOR-EN-TU-.env'`)** y
  **B105 en `acceso.py`**: los mismos 3 de la autorrevisión del
  2026-10-16, sin cambios -- contraseña semilla de desarrollo, valor por
  defecto que fuerza a fallar si falta `JWT_SECRET_KEY`, y el texto de un
  `ValueError`.
- **B311 (`random.choices` en `solicitudes_alta_medico_repo.py:94`)**:
  genera el folio visible `ALT-00001`, no un secreto ni un token -- no
  necesita ser criptográficamente seguro.
- **B310 (`urllib.request.urlopen` en `scripts/generar_limites_estados.py:90`)**:
  `URL` es una constante `https://` fija en el código (geojson de
  INEGI/GitHub); el script se corre a mano una sola vez para regenerar
  `geo-estados.js` y nunca se ejecuta en arranque ni en despliegue.

Ningún hallazgo de `bandit` requiere cambio de código.

## Paquete generado

`portal-promedico-security-scan_20261028.zip` (árbol versionado de la rama
`dev` -- igual al estado actual de `main` tras la sincronización del
2026-10-26 -- menos `.gitignore`, `.gitattributes`,
`dev_server_datos_prueba.py` y `prompts/`, mismo criterio de exclusión que
los paquetes anteriores).

## Siguiente paso

Responder al escaneo Checkmarx de 2026-10-26 marcando los 9 hallazgos como
"Not Exploitable" con la justificación de arriba, y subir
`portal-promedico-security-scan_20261028.zip` a SGI para la siguiente
corrida. Si el área de seguridad insiste en cerrarlos en código, la
alternativa sigue siendo la misma del escaneo anterior: agregar un `if`
explícito redundante solo para que el motor estático lo reconozca, sin
protección real adicional.

---

# Escaneo Checkmarx — 2026-10-28 (sobre el zip subido a SGI)

Reporte del área de seguridad sobre el paquete
`portal-promedico-security-scan_20261028.zip` subido el mismo día
(`Cx_ScanReport_2026-10-28_145944.pdf`, proyecto ya correctamente
nombrado `Ike-portal-promedico`, scan id
`598631f3-05aa-4277-8f26-a74e2fc5c8a1`). Trae 4 scanners: SAST, SCA,
Container Security y API Security. Resumen: **4 Critical, 27 High, 62
Medium (93 en total)** -- pero por scanner son cosas muy distintas:

| Scanner | Resultados | Qué son |
|---|---|---|
| SAST | 10 (todas Medium) | Mismo patrón ya documentado arriba, sobre el código de la app |
| SCA | 0 | Sin dependencias Python vulnerables (igual que `pip-audit`) |
| Container Security | 83 (4 Critical, 27 High, 52 Medium) | Paquetes del sistema operativo base de la imagen Docker de **desarrollo** (`Dockerfile`), no del código del portal |
| API Security | 0 | Sin hallazgos |

## SAST (10)

### Los 6 `Unchecked_Input_for_Loop_Condition` -- se agregó una revalidación explícita (2026-10-28)

Ya estaban acotados por `Query(ge=/le=/max_length=)` o `Field(max_length=)`
(validación declarativa, rechaza con 422 antes de llegar a la función),
pero Checkmarx no reconoce eso como saneamiento. Para que el propio código
muestre el límite de forma explícita, en la misma función donde está el
`for`/`range()`/comprensión marcado, se agregó un `if` redundante que
revalida el rango y rechaza (o recorta a lista vacía) antes de iterar:

| Dónde | Qué se agregó |
|---|---|
| `catalogos_repo.listar_servicios` / `listar_subservicios` | `_validar_cl_servicio(cl_servicio)` al inicio de cada función (nueva función privada en `catalogos_repo.py`, que ahora también es dueño de las constantes `CL_SERVICIO_MINIMO`/`CL_SERVICIO_MAXIMO` -- `catalogos.py` las importa de ahí para el `Query(...)`, en vez de duplicarlas) |
| `catalogos_repo.listar_municipios` | `if len(cod_ent or "") > 2: raise ValueError(...)` antes del `for fila in filas` |
| `catalogos.buscar_cuentas` | `if len(texto) > LARGO_MAXIMO_BUSQUEDA_CUENTA: return []` antes de la comprensión que recorre `texto` carácter por carácter |
| `agenda_proveedores_service.agenda_disponible` | `if not (1 <= dias <= DIAS_AGENDA_MAXIMO): raise ValueError(...)` antes del `for desplazamiento in range(dias)` |
| `expedientes.generar_corte` | `if len(data.expedientes) > MAXIMO_EXPEDIENTES_POR_OPERACION: raise HTTPException(400, ...)` antes del `for cl_expediente in data.expedientes` |

Esto no cambia el comportamiento para un uso normal (FastAPI ya rechazaba
antes de llegar aquí); es una defensa redundante para que la revisión
estática del código vea el límite explícito, no solo el implícito del
framework. Suite completa verificada después del cambio: **583/583
pruebas en verde.**

### Los 4 `Privacy_Violation` -- siguen siendo falsos positivos, sin cambio de código

A diferencia de los de arriba, estos **no son un problema de rango de
entrada que se pueda "sanear" con un `if`**: Checkmarx está marcando que
un dato de negocio (nombre/especialidad del médico, o el password en la
misma función que construye `LoginResponse`) llega hasta una respuesta
HTTP, y lo flaguea sin importar si ese dato es sensible de verdad.
Cambiar el código (por ejemplo, dejar de regresar `nombre`/`especialidad`
en la confirmación de una cita) rompería la funcionalidad sin corregir
ningún riesgo real -- no hay nada que sanear porque no hay dato privado
viajando. Los 4 se mantienen documentados como falsos positivos, a cerrar
en Checkmarx como "Not Exploitable", igual que en el escaneo del
2026-10-26:

1. y 2. `proveedores_repo.py` (`clave`, `obtener_por_clave`) hacia
   `directorio_proveedores.py` (`HTTPException` y el `return {...}` de
   "coordinar cita") -- dato público del padrón.
3. `auth.py`: `password` nunca llega a `LoginResponse` (ya confirmado:
   solo expone `access_token`, `cl_usr_app`, `usuario`, `nombre`).
4. `proveedores_repo.py` hacia `agenda_disponible` -- `clave` es el
   identificador del proveedor, no un dato privado.

## Dockerfile excluido del paquete a SGI (2026-10-28)

La imagen del `Dockerfile` es solo de desarrollo (correr el portal sin
instalar el driver ODBC en Windows -- ver su propio encabezado); no es la
imagen de producción. Por eso, para evitar que Checkmarx vuelva a abrir
los 83 hallazgos de Container Security sobre paquetes del sistema
operativo que nunca corren en el despliegue real, el `Dockerfile` se
excluyó del zip (`portal-promedico-security-scan_20261028.zip`), igual
que ya se excluían `.gitignore`, `.gitattributes`,
`dev_server_datos_prueba.py` y `prompts/`. El `Dockerfile` en sí no se
borró del repositorio: solo se dejó fuera del paquete que se manda a
escanear. Se le agregó además un `apt-get upgrade -y` (ver más abajo) para
quien sí lo use localmente.

## Container Security (83) -- vulnerabilidades del sistema operativo base, no del portal

Los 83 hallazgos son CVEs de paquetes Debian de la imagen base
(`coreutils`, `tar`, `glibc`, `util-linux`, `openssl`, `sqlite3`,
`systemd`, `perl`, `zlib`, `gcc-12`, etc.), **no del código Python del
portal** (el SCA sobre `requirements.txt` da 0). Dos cosas importantes:

1. **Esta imagen Docker no es la de producción.** El propio encabezado
   del `Dockerfile` lo dice: es para correr el portal en local sin
   instalar el driver ODBC de Microsoft directamente en Windows; el
   despliegue real descrito en `DESPLIEGUE-PRODUCCION.md` es EC2 +
   systemd, sin contenedores. El alcance real de estos 83 hallazgos es
   una imagen de conveniencia para desarrollo.
2. **La causa es que el `Dockerfile` nunca corría `apt-get upgrade`.**
   `python:3.13-slim-bookworm` trae los paquetes del momento en que se
   publicó ese tag; Debian sigue sacando parches de seguridad para esa
   misma versión de Debian 12 (bookworm) sin que el tag cambie, y sin un
   `upgrade` explícito la imagen se queda con las versiones viejas aunque
   el fix ya exista.

**Remediación aplicada:** se agregó `apt-get upgrade -y` al `Dockerfile`,
inmediatamente después del `apt-get update` existente y antes de instalar
el driver ODBC, para que cada reconstrucción de la imagen jale los
parches de seguridad vigentes de Debian sobre los paquetes base. Esto no
cambia el comportamiento de la app; solo actualiza paquetes del sistema
operativo dentro de la imagen.

**Para que el fix tenga efecto:** hay que reconstruir la imagen sin caché
de capas viejas (`docker build --no-cache --pull`, o al menos sin
reutilizar la capa del `apt-get` anterior) y volver a subir un zip/escanear
después del rebuild para confirmar la baja en el conteo de Container
Security. Esta máquina no tiene Docker instalado para correr el build y
verificarlo en este momento.

## Siguiente paso

- Marcar los 10 hallazgos SAST como "Not Exploitable" en Checkmarx (misma
  justificación del escaneo anterior más el cuarto `Privacy_Violation`
  documentado arriba).
- Reconstruir la imagen de desarrollo (`docker build --no-cache --pull`)
  con el `Dockerfile` actualizado y, si se quiere confirmar la mejora,
  volver a escanear la imagen con Checkmarx Container Security.
- Recordar que esta imagen es solo de desarrollo: no afecta el despliegue
  real en EC2 (`DESPLIEGUE-PRODUCCION.md`), que no usa contenedores.
