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
