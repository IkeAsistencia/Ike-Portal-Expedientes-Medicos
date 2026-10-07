# Revisión de seguridad — Portal Expedientes Médicos

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
