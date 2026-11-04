# Base de datos local (SQLite) — Portal Promédico

Esquema completo en `app/db/local_store.py` (constante `_SCHEMA` +
migraciones). Vive en un único archivo (`LOCAL_DB_PATH` en `.env`, default
`data/app_local.db`), **no está versionado en git** y se crea/actualiza
solo con `init_local_db()`, que corre en cada arranque del portal
(`CREATE TABLE IF NOT EXISTS` + `ALTER TABLE` para columnas agregadas
después).

Esta base existe por una razón puntual: hay datos que, por decisión del
usuario, **no se guardan en SQL Server** (ver `sql/README.md` para lo que
sí vive ahí) — porque son exclusivos de esta aplicación, porque el acceso
de escritura a SQL Server no estaba disponible, o porque el dato nunca
debió estar en el sistema central (bitácoras propias, archivos). El
acceso a todas las tablas de aquí es por SQLite parametrizado
(`sqlite3`), sin Stored Procedures.

## Tablas por área funcional

### Expedientes / Seguimiento

| Tabla | Para qué sirve |
|---|---|
| `estatus_expediente` | Estatus de negocio del expediente (Abierto, En Espera de Respuesta, Seguimiento Proveedor, Finalizado) — dato que no existe en SQL Server, se calcula/guarda aquí (`app/schemas/expediente.py`). PK `cl_expediente`. |
| `comentarios_seguimiento` | Copia local de los comentarios de Proveedor ("Actualizar Bitácora") y de Cabina ("Regresar a Proveedor"). `origen` distingue de quién es cada uno para mostrarlos en secciones separadas. |
| `seguimiento_fallidos` | Bitácora propia para cuando el INSERT hacia `dbo.Seguimiento` (SQL Server, vía `ST_CP_RegistrarSeguimiento`) falla por un error de base de datos — así no se pierde lo capturado y se puede revisar/reintentar. |
| `expediente_pago_anticipado` | Si un expediente es "pago anticipado" (solo el Proveedor lo sabe, lo marca él mismo). `bloqueado` se activa solo (no se puede desmarcar) en cuanto Proveedor manda su primer comentario, para que no cambie una vez que Cabina ya lo está revisando con ese valor. PK `cl_expediente`. |
| `alertas_proveedor_enviadas` | Qué alertas del cron (`jobs/validar_estatus_proveedor.py`) ya se mandaron (nivel `naranja` ≥8h / `rojo` ≥24h), para no reenviar la misma. PK compuesta `(cl_expediente, nivel)`. |
| `comprobantes_pago` | Archivo del comprobante de pago (expedientes Pago Anticipado) — el archivo completo en `BLOB`, máximo 5 MB validado en el router; no hay almacenamiento de archivos aparte. |
| `cortes_generados` | Cada "corte" en Excel de expedientes enviados a proveedores (botones "Generar corte" / "Confirmar y enviar"). Guarda el binario generado para que descargar y confirmar-y-enviar usen exactamente el mismo archivo, y deja evidencia de qué se generó/envió y cuándo. `expedientes` es un JSON con la lista de `cl_expediente` incluidos. |
| `correos_enviados` | Historial de "Enviar correo a proveedores": a quién, cuándo, con qué expedientes. `simulado=1` cuando no había SMTP configurado (quedó solo en el log de la app, no se mandó un correo real). `motivo_sin_correo` dice por qué no salió correo (tope diario o sin proveedor). |
| `correos_salientes` | Cada correo que sale del portal (a proveedores o el corte), para el tope diario de correos. |

### Acceso / cuentas

| Tabla | Para qué sirve |
|---|---|
| `usuarios_acceso` | Acceso por RFC, independiente de SISE. `perfil`: 1=Administrador, 2=Cabina, 3=Proveedor. `password_hash` queda `NULL` hasta que la persona crea su contraseña la primera vez. `activo` es baja lógica (1/0) — el registro nunca se borra. PK `rfc`. |
| `cuentas_configuradas` | Grid de la pantalla "Configuración Cuentas" (qué cuentas puede ver cada perfil no-Administrador). PK `cl_cuenta`. |
| `cuentas_etiqueta` | Color y prefijo por cuenta, módulo "Colores de Cuentas" (solo Administrador). PK `cl_cuenta`. |

### Directorio de Proveedores

| Tabla | Para qué sirve |
|---|---|
| `proveedores` | Padrón **único** del Directorio: conviven los dos orígenes (`origen='catalogo'` = llegó en la carga de Excel, "Dentro de la red"; `origen='portal'` = se dio de alta en el portal, "Fuera de la red"). `clave` (`PRV-000001`) la genera este portal y no cambia nunca, es lo que usan las citas. `llave_identidad` (`UNIQUE`) es con qué se reconoce al mismo médico entre una carga y otra (incluye especialidad a propósito: un médico con varias especialidades es un renglón por cada una). `cl_especialidad` lo amarra a `especialidades_catalogo` para que cuente en los KPI. `origen_coordenadas` distingue si `latitud`/`longitud` vinieron en el Excel (`NULL`/`'carga'`, fuente autorizada) o del enriquecimiento con el Catálogo CLUES (`'clues'`) — para no pisar el dato bueno. La carga es incremental: nunca borra, solo agrega/actualiza. |
| `proveedores_cargas` | Bitácora de cada carga del Excel del padrón: total de filas, nuevos, actualizados y "absorbidos" (ya estaban dados de alta en el portal y la carga los pasó a `origen='catalogo'`). |
| `especialidades_catalogo` | Catálogo de especialidades médicas, copiado del sistema central (`CatEspecialidadesMedicas.txt`). Lo resiembra `especialidades_repo.sembrar()` en cada arranque — la fuente de verdad es el código, no esta tabla. `orden_kpi` decide qué especialidades salen como tarjeta y en qué orden; `activo=0` marca las que ya no vienen en el catálogo (no se borran, para no dejar proveedores apuntando a una especialidad inexistente). |
| `citas_proveedor` | Citas agendadas desde el Directorio. Amarradas a `proveedores.clave` (no al `id` interno ni a `cl_proveedor`) para que una carga de Excel no las deje huérfanas. `UNIQUE (clave_proveedor, fecha, hora)` evita que dos personas tomen el mismo horario del mismo médico; un índice único parcial (`ux_cita_activa_por_expediente`, solo sobre citas con `estatus='Agendada'`) garantiza que un expediente tenga una sola cita activa a la vez, a nivel de base de datos. |
| `solicitudes_alta_medico` | Solicitudes de "Alta de médico" (pantalla "Proveedores"). Vive solo aquí, nunca se manda al sistema central. Al aprobarse, el médico entra a `proveedores` con `origen='portal'` y `clave_proveedor` guarda qué clave le tocó. |
| `solicitudes_alta_documentos` | Archivos opcionales de una solicitud (constancia de situación fiscal, cédula profesional). `UNIQUE (folio, tipo)`: subir uno nuevo del mismo tipo reemplaza al anterior. |

## Detalle de columnas por tabla

Nota sobre "Longitud": SQLite no impone un tamaño máximo por tipo (type
affinity, no `VARCHAR(n)` real) — un campo `TEXT` acepta cualquier largo
aunque el esquema no lo declare. Donde el campo sigue un formato o un
límite fijado por la aplicación (no por la base), se anota ese formato;
donde es texto libre sin límite conocido, se marca "Libre".

### `estatus_expediente`

| Columna | Tipo | Longitud / Formato | Obligatorio | Para qué se creó |
|---|---|---|---|---|
| `cl_expediente` | INTEGER | — (PK) | Sí | Identifica el expediente (mismo `clExpediente` de SQL Server); es la llave para amarrar el estatus de negocio, exclusivo de este portal, al expediente real. |
| `estatus` | TEXT | Uno de: Abierto, En Espera de Respuesta, Seguimiento Proveedor, Finalizado | Sí (`DEFAULT 'Abierto'`) | Guarda el estatus de negocio del expediente, que no existe como tal en SQL Server. |
| `fecha_cambio` | TEXT | `YYYY-MM-DD HH:MM:SS` | Sí (`DEFAULT datetime('now','localtime')`) | Cuándo se hizo el último cambio de estatus, para trazabilidad. |
| `rfc_cambio` | TEXT | RFC (libre) | No | Quién hizo el último cambio de estatus (columna agregada después por migración). |

### `cuentas_configuradas`

| Columna | Tipo | Longitud / Formato | Obligatorio | Para qué se creó |
|---|---|---|---|---|
| `cl_cuenta` | INTEGER | — (PK) | Sí | Identificador de la cuenta (viene de `cCuenta` en SQL Server). |
| `nombre` | TEXT | Libre | Sí | Nombre de la cuenta, para mostrarlo en el grid de "Configuración Cuentas" sin tener que consultarlo cada vez. |

### `cuentas_etiqueta`

| Columna | Tipo | Longitud / Formato | Obligatorio | Para qué se creó |
|---|---|---|---|---|
| `cl_cuenta` | INTEGER | — (PK) | Sí | Identificador de la cuenta a la que aplica el color/prefijo. |
| `nombre` | TEXT | Libre | Sí | Nombre de la cuenta, para mostrarlo junto al color sin otra consulta. |
| `prefijo` | TEXT | Libre | Sí (`DEFAULT ''`) | Prefijo corto que distingue la cuenta en folios/listados del módulo "Colores de Cuentas". |
| `color` | TEXT | Código de color (ej. hex) | Sí | Color asignado a la cuenta, para pintarla igual en toda la interfaz. |
| `actualizado` | TEXT | `YYYY-MM-DD HH:MM:SS` | No | Fecha del último cambio de color/prefijo. |
| `actualizado_por` | TEXT | RFC o usuario (libre) | No | Quién hizo el último cambio, para auditoría. |

### `alertas_proveedor_enviadas`

| Columna | Tipo | Longitud / Formato | Obligatorio | Para qué se creó |
|---|---|---|---|---|
| `cl_expediente` | INTEGER | — (parte de la PK compuesta) | Sí | Expediente al que corresponde la alerta. |
| `nivel` | TEXT | `'naranja'` o `'rojo'` (parte de la PK compuesta) | Sí | Qué tan grave es la alerta (≥8h = naranja, ≥24h = rojo), para no reenviar el mismo nivel dos veces. |
| `fecha_envio` | TEXT | `YYYY-MM-DD HH:MM:SS` | Sí (`DEFAULT datetime('now','localtime')`) | Cuándo se mandó esa alerta. |

### `usuarios_acceso`

| Columna | Tipo | Longitud / Formato | Obligatorio | Para qué se creó |
|---|---|---|---|---|
| `rfc` | TEXT | RFC, 13 caracteres (PK) | Sí | Identifica a la persona que inicia sesión, independiente de SISE. |
| `nombre` | TEXT | Libre | Sí | Nombre para mostrar en la sesión y en bitácoras. |
| `perfil` | INTEGER | 1, 2 ó 3 | Sí | Rol de acceso: 1=Administrador, 2=Cabina, 3=Proveedor — controla qué puede ver/hacer cada quien. |
| `password_hash` | TEXT | Hash PBKDF2-SHA256 (libre) | No | Contraseña ya hasheada; queda `NULL` hasta que la persona la crea la primera vez. |
| `fecha_alta` | TEXT | `YYYY-MM-DD HH:MM:SS` | Sí (`DEFAULT datetime('now','localtime')`) | Cuándo se dio de alta el acceso. |
| `entidad` | TEXT | Libre | No | Entidad federativa asociada a la persona (agregada por migración). |
| `correo` | TEXT | Correo electrónico (libre) | No | Correo de contacto de la persona (agregada por migración). |
| `activo` | INTEGER | 0 ó 1 | Sí (`DEFAULT 1`, agregada por migración) | Baja lógica: 1=activo, 0=inactivado; el registro nunca se borra para no perder el historial. |

### `comentarios_seguimiento`

| Columna | Tipo | Longitud / Formato | Obligatorio | Para qué se creó |
|---|---|---|---|---|
| `id` | INTEGER | — (PK autoincremental) | Sí | Identificador propio del comentario. |
| `cl_expediente` | INTEGER | — | Sí | Expediente al que pertenece el comentario. |
| `rfc` | TEXT | RFC (libre) | Sí | Quién escribió el comentario. |
| `comentario` | TEXT | Libre | Sí | Texto del comentario capturado. |
| `origen` | TEXT | `'proveedor'` o `'cabina'` | Sí (`DEFAULT 'proveedor'`) | Distingue si vino de "Actualizar Bitácora" (Proveedor) o "Regresar a Proveedor" (Cabina), para mostrarlos en secciones separadas. |
| `fecha` | TEXT | `YYYY-MM-DD HH:MM:SS` | Sí (`DEFAULT datetime('now','localtime')`) | Cuándo se capturó el comentario. |

### `comprobantes_pago`

| Columna | Tipo | Longitud / Formato | Obligatorio | Para qué se creó |
|---|---|---|---|---|
| `id` | INTEGER | — (PK autoincremental) | Sí | Identificador propio del comprobante. |
| `cl_expediente` | INTEGER | — | Sí | Expediente de Pago Anticipado al que pertenece el comprobante. |
| `rfc` | TEXT | RFC (libre) | Sí | Quién subió el comprobante. |
| `nombre_archivo` | TEXT | Libre | Sí | Nombre original del archivo, para mostrarlo/descargarlo igual que se subió. |
| `tipo_mime` | TEXT | Libre (ej. `application/pdf`) | Sí | Tipo de archivo, validado contra el contenido real ("magic bytes") antes de guardarse. |
| `contenido` | BLOB | Máximo 5 MB (validado en el router, no en la base) | Sí | El archivo completo; no hay almacenamiento de archivos aparte del portal. |
| `fecha` | TEXT | `YYYY-MM-DD HH:MM:SS` | Sí (`DEFAULT datetime('now','localtime')`) | Cuándo se subió el comprobante. |

### `seguimiento_fallidos`

| Columna | Tipo | Longitud / Formato | Obligatorio | Para qué se creó |
|---|---|---|---|---|
| `id` | INTEGER | — (PK autoincremental) | Sí | Identificador propio del intento fallido. |
| `cl_expediente` | INTEGER | — | Sí | Expediente sobre el que se intentó actualizar seguimiento. |
| `observaciones` | TEXT | Libre | Sí | El comentario que la persona capturó y que no se pudo insertar en `dbo.Seguimiento`. |
| `cl_usr_app` | INTEGER | — | No | Usuario del sistema central que intentó la operación, si se conocía. |
| `nombre` | TEXT | Libre | No | Nombre de quien inició sesión en el portal (no RFC, no `clUsrApp`). |
| `error` | TEXT | Libre | No | Detalle del error de base de datos recibido, para diagnóstico. |
| `fecha` | TEXT | `YYYY-MM-DD HH:MM:SS` | Sí (`DEFAULT datetime('now','localtime')`) | Cuándo ocurrió el intento fallido. |

### `cortes_generados`

| Columna | Tipo | Longitud / Formato | Obligatorio | Para qué se creó |
|---|---|---|---|---|
| `id` | INTEGER | — (PK autoincremental) | Sí | Identificador propio del corte. |
| `rfc` | TEXT | RFC (libre) | Sí | Quién generó el corte. |
| `tipo_expediente` | TEXT | `'normal'` o `'anticipado'` | Sí | De qué pantalla salió el corte (Expedientes o Expedientes PA). |
| `expedientes` | TEXT | JSON (lista de enteros) | Sí | Lista de `cl_expediente` incluidos en el corte, para saber exactamente qué se mandó. |
| `nombre_archivo` | TEXT | Libre | Sí | Nombre del archivo Excel generado. |
| `contenido` | BLOB | Sin límite declarado | Sí | El archivo Excel ya generado, para que "descargar" y "confirmar y enviar" usen exactamente el mismo binario. |
| `fecha_generado` | TEXT | `YYYY-MM-DD HH:MM:SS` | Sí (`DEFAULT datetime('now','localtime')`) | Cuándo se generó el corte. |
| `enviado` | INTEGER | 0 ó 1 | Sí (`DEFAULT 0`) | Si ya se confirmó su envío al proveedor. |
| `destinatario` | TEXT | Correo electrónico (libre) | No | A quién se envió el corte. |
| `fecha_enviado` | TEXT | `YYYY-MM-DD HH:MM:SS` | No | Cuándo se confirmó el envío. |

### `expediente_pago_anticipado`

| Columna | Tipo | Longitud / Formato | Obligatorio | Para qué se creó |
|---|---|---|---|---|
| `cl_expediente` | INTEGER | — (PK) | Sí | Expediente marcado como pago anticipado. |
| `es_anticipado` | INTEGER | 0 ó 1 | Sí (`DEFAULT 0`) | Si el expediente es de pago anticipado; solo el Proveedor lo sabe y lo marca. |
| `bloqueado` | INTEGER | 0 ó 1 | Sí (`DEFAULT 0`) | Se activa solo (no se puede desmarcar) al primer comentario de Proveedor, para que el valor no cambie mientras Cabina ya lo está revisando. |
| `rfc` | TEXT | RFC (libre) | No | Quién hizo la marca. |
| `fecha` | TEXT | `YYYY-MM-DD HH:MM:SS` | Sí (`DEFAULT datetime('now','localtime')`) | Cuándo se marcó. |

### `correos_enviados`

| Columna | Tipo | Longitud / Formato | Obligatorio | Para qué se creó |
|---|---|---|---|---|
| `id` | INTEGER | — (PK autoincremental) | Sí | Identificador propio del envío. |
| `tipo` | TEXT | `'nuevo'` o `'recordatorio'` | Sí | Qué clase de correo fue. |
| `destinatario` | TEXT | Correos separados por coma (libre) | Sí | A quién se envió: los proveedores de las entidades de la selección. Vacío cuando no salió correo. |
| `expedientes` | TEXT | JSON (lista de enteros) | Sí | Qué expedientes incluía el correo. |
| `rfc_envio` | TEXT | RFC (libre) | Sí | Quién lo mandó. |
| `simulado` | INTEGER | 0 ó 1 | Sí (`DEFAULT 0`) | 1 cuando no había SMTP configurado: no se mandó un correo real, solo quedó el registro. |
| `fecha` | TEXT | `YYYY-MM-DD HH:MM:SS` | Sí (`DEFAULT datetime('now','localtime')`) | Cuándo se mandó/simuló. También la usa el freno de reenvío (`CORREO_REENVIO_HORAS`). |
| `motivo_sin_correo` | TEXT | `'limite'`, `'sin_proveedores'` o NULL | No | Por qué no salió correo aunque los expedientes pasaron a "En Espera de Respuesta": se llegó al tope diario, o ninguna entidad de la selección tiene proveedor. NULL = sí salió. |

### `correos_salientes`

Cada correo que sale del portal (a proveedores o el corte), para llevar el tope diario de la cuenta de correo (`SMTP_LIMITE_DIARIO`, ver `app/services/cuota_correos_service.py`).

| Columna | Tipo | Longitud / Formato | Obligatorio | Para qué se creó |
|---|---|---|---|---|
| `id` | INTEGER | — (PK autoincremental) | Sí | Identificador propio. |
| `dia` | TEXT | `YYYY-MM-DD` (hora del centro de México) | Sí | Día del tope al que cuenta. Indexado. |
| `origen` | TEXT | `'proveedores'` o `'corte'` | Sí | Qué envío fue. |
| `unidades` | INTEGER | Entero | Sí | Cuánto cuenta contra el tope: 1 por destinatario o 1 por mensaje (`SMTP_CUENTA_POR_DESTINATARIO`). |
| `simulado` | INTEGER | 0 ó 1 | Sí (`DEFAULT 0`) | 1 cuando no había SMTP configurado (en local también cuenta, para poder probar el contador). |
| `fecha` | TEXT | `YYYY-MM-DD HH:MM:SS` | Sí | Cuándo salió. |

### `proveedores`

| Columna | Tipo | Longitud / Formato | Obligatorio | Para qué se creó |
|---|---|---|---|---|
| `id` | INTEGER | — (PK autoincremental) | Sí | Identificador interno de la base (no se expone). |
| `clave` | TEXT | `PRV-000001` (único) | Sí | Identificador propio del portal; no cambia nunca, es lo que amarra las citas al médico. |
| `llave_identidad` | TEXT | Libre, compuesta (único) | Sí | Con qué se reconoce al mismo médico entre una carga y otra (nombre + especialidad + domicilio + teléfono); incluye la especialidad a propósito, para que cada una sea un renglón distinto. |
| `origen` | TEXT | `'catalogo'` o `'portal'` | Sí (`DEFAULT 'catalogo'`) | De dónde llegó el proveedor: Excel ("Dentro de la red") o alta en el portal ("Fuera de la red"). |
| `cl_proveedor` | INTEGER | — | No | Referencia opcional al proveedor del sistema central (ya no obligatoria). |
| `nombre` | TEXT | Libre | Sí | Nombre del médico. |
| `especialidad` | TEXT | Libre | No | Especialidad tal como vino en el Excel o en el alta (texto original). |
| `cl_especialidad` | INTEGER | — | No (agregada por migración) | A qué especialidad de `especialidades_catalogo` corresponde ese texto; queda `NULL` si no empató, para no rechazar el renglón pero sí excluirlo de los KPI. |
| `cedula` | TEXT | Libre | No | Cédula profesional del médico. |
| `rfc` | TEXT | RFC (libre) | No | RFC del médico, si se tiene. |
| `estado` | TEXT | Libre | No | Entidad federativa del consultorio. |
| `municipio` | TEXT | Libre | No | Municipio del consultorio. |
| `calle_num_ext_int` | TEXT | Libre | No | Calle y número del consultorio (domicilio donde atiende, no el fiscal). |
| `colonia` | TEXT | Libre | No | Colonia del consultorio. |
| `codigo_postal` | TEXT | Libre (convención: 5 dígitos) | No | Código postal del consultorio. |
| `consultorio` | TEXT | Libre | No | Nombre o referencia del consultorio/clínica. |
| `telefono` | TEXT | Libre | No | Teléfono de contacto. |
| `email` | TEXT | Correo electrónico (libre) | No | Correo de contacto. |
| `horario` | TEXT | Libre | No | Horario de atención. |
| `costo_consulta` | TEXT | Libre | No | Costo de consulta tal como se capturó. |
| `convenio` | TEXT | Libre | No | Datos de convenio (solo aplica a `origen='catalogo'`). |
| `teleconsulta` | INTEGER | 0 ó 1 | Sí (`DEFAULT 0`) | Si el médico ofrece teleconsulta. |
| `latitud` | REAL | Coordenada decimal | No | Ubicación del consultorio para el mapa. |
| `longitud` | REAL | Coordenada decimal | No | Ubicación del consultorio para el mapa. |
| `origen_coordenadas` | TEXT | `NULL`/`'carga'` o `'clues'` | No (agregada por migración) | De dónde salieron `latitud`/`longitud`: del Excel del área (fuente autorizada) o del enriquecimiento con el Catálogo CLUES — para no pisar el dato bueno y poder auditar. |
| `folio_alta` | TEXT | Formato `ALT-00001` | No | Folio de la solicitud de alta, si el proveedor nació en el portal. |
| `fecha_alta` | TEXT | `YYYY-MM-DD HH:MM:SS` | Sí | Cuándo entró el proveedor al padrón. |
| `fecha_actualizacion` | TEXT | `YYYY-MM-DD HH:MM:SS` | No | Cuándo se actualizó por última vez (ej. en una recarga de Excel). |

### `especialidades_catalogo`

| Columna | Tipo | Longitud / Formato | Obligatorio | Para qué se creó |
|---|---|---|---|---|
| `cl_especialidad` | INTEGER | — (PK) | Sí | Clave de la especialidad, copiada del catálogo central. |
| `descripcion` | TEXT | Libre | Sí | Nombre de la especialidad a mostrar. |
| `prioridad` | INTEGER | — | No | Orden de prioridad de negocio para la especialidad (viene del catálogo central, puede repetirse o venir vacío). |
| `orden_kpi` | INTEGER | — | No | En qué posición sale como tarjeta en el Directorio de Proveedores; si es `NULL`, la especialidad solo aparece en el combo, no como tarjeta. |
| `activo` | INTEGER | 0 ó 1 | Sí (`DEFAULT 1`) | 0 marca las que dejaron de venir en el catálogo central (no se borran, para no dejar proveedores huérfanos). |

### `proveedores_cargas`

| Columna | Tipo | Longitud / Formato | Obligatorio | Para qué se creó |
|---|---|---|---|---|
| `id` | INTEGER | — (PK autoincremental) | Sí | Identificador propio de la carga. |
| `rfc` | TEXT | RFC (libre) | Sí | Quién ejecutó la carga del Excel. |
| `total_filas` | INTEGER | — | Sí | Cuántas filas traía el Excel cargado. |
| `nuevos` | INTEGER | — | Sí (`DEFAULT 0`) | Cuántos proveedores se agregaron por primera vez. |
| `actualizados` | INTEGER | — | Sí (`DEFAULT 0`) | Cuántos ya existían y se actualizaron. |
| `absorbidos` | INTEGER | — | Sí (`DEFAULT 0`) | Cuántos ya estaban dados de alta en el portal (`origen='portal'`) y la carga los pasó a `'catalogo'`. |
| `fecha` | TEXT | `YYYY-MM-DD HH:MM:SS` | Sí (`DEFAULT datetime('now','localtime')`) | Cuándo se hizo la carga. |

### `citas_proveedor`

| Columna | Tipo | Longitud / Formato | Obligatorio | Para qué se creó |
|---|---|---|---|---|
| `id` | INTEGER | — (PK autoincremental) | Sí | Identificador interno de la base. |
| `folio` | TEXT | Formato `CITA-00001` (único) | Sí | Identificador visible de la cita, consecutivo. |
| `clave_proveedor` | TEXT | `PRV-000001` | Sí | A qué proveedor pertenece la cita (referencia a `proveedores.clave`, no al `id` interno, para no quedar huérfana si se recarga el Excel). |
| `fecha` | TEXT | `YYYY-MM-DD` | Sí | Fecha de la cita. |
| `hora` | TEXT | `HH:MM` | Sí | Hora de la cita. |
| `paciente` | TEXT | Libre | No | Nombre del paciente que agenda. |
| `cl_expediente` | INTEGER | — | No (agregada por migración) | Expediente de Seguimiento desde el que se coordinó la cita, si aplica. |
| `rfc_agendo` | TEXT | RFC (libre) | Sí | Quién agendó la cita. |
| `estatus` | TEXT | `'Agendada'`, cancelada, etc. | Sí (`DEFAULT 'Agendada'`) | Estado actual de la cita. |
| `fecha_registro` | TEXT | `YYYY-MM-DD HH:MM:SS` | Sí | Cuándo se registró la cita. |
| `motivo_cancelacion` | TEXT | Libre | No | Por qué se canceló, si aplica. |
| `rfc_cancelo` | TEXT | RFC (libre) | No | Quién canceló la cita. |
| `fecha_cancelacion` | TEXT | `YYYY-MM-DD HH:MM:SS` | No | Cuándo se canceló. |

`UNIQUE (clave_proveedor, fecha, hora)` evita que dos personas tomen el
mismo horario del mismo médico. Un índice único parcial adicional
(`ux_cita_activa_por_expediente`, solo sobre `estatus='Agendada'` y
`cl_expediente IS NOT NULL`) garantiza, a nivel de base de datos, que un
expediente tenga una sola cita activa a la vez.

### `solicitudes_alta_medico`

| Columna | Tipo | Longitud / Formato | Obligatorio | Para qué se creó |
|---|---|---|---|---|
| `id` | INTEGER | — (PK autoincremental) | Sí | Identificador interno de la base. |
| `folio` | TEXT | Formato `ALT-00001` (único) | Sí | Identificador visible de la solicitud, consecutivo. |
| `nombre` | TEXT | Libre | Sí | Nombre del médico que solicita el alta. |
| `especialidad` | TEXT | Libre | Sí | Especialidad declarada. |
| `cedula` | TEXT | Libre | Sí | Cédula profesional a validar. |
| `rfc` | TEXT | RFC (libre) | No | RFC del solicitante. |
| `estado` | TEXT | Libre | No | Entidad federativa del consultorio propuesto. |
| `municipio` | TEXT | Libre | No | Municipio del consultorio propuesto. |
| `calle_num_ext_int` | TEXT | Libre | No (agregada por migración) | Calle y número del consultorio propuesto. |
| `colonia` | TEXT | Libre | No (agregada por migración) | Colonia del consultorio propuesto. |
| `codigo_postal` | TEXT | Libre | No (agregada por migración) | Código postal del consultorio propuesto. |
| `consultorio` | TEXT | Libre | No (agregada por migración) | Nombre/referencia del consultorio propuesto. |
| `horario` | TEXT | Libre | No (agregada por migración) | Horario propuesto. |
| `costo_consulta` | TEXT | Libre | No (agregada por migración) | Costo de consulta propuesto. |
| `telefono` | TEXT | Libre | No | Teléfono de contacto. |
| `email` | TEXT | Correo electrónico (libre) | No | Correo de contacto. |
| `estatus` | TEXT | En revisión, Aprobada, Rechazada, etc. | Sí (`DEFAULT 'En revisión'`) | Estado del trámite de alta. |
| `clave_proveedor` | TEXT | `PRV-000001` | No (agregada por migración) | Qué clave del padrón le tocó al aprobarse. |
| `rfc_solicito` | TEXT | RFC (libre) | Sí | Quién capturó la solicitud. |
| `fecha` | TEXT | `YYYY-MM-DD HH:MM:SS` | Sí (`DEFAULT datetime('now','localtime')`) | Cuándo se capturó la solicitud. |

### `solicitudes_alta_documentos`

| Columna | Tipo | Longitud / Formato | Obligatorio | Para qué se creó |
|---|---|---|---|---|
| `id` | INTEGER | — (PK autoincremental) | Sí | Identificador interno de la base. |
| `folio` | TEXT | Formato `ALT-00001` | Sí | A qué solicitud pertenece el documento (parte de `UNIQUE (folio, tipo)`). |
| `tipo` | TEXT | Libre (ej. `'constancia_fiscal'`, `'cedula'`) | Sí | Qué documento es (parte de `UNIQUE (folio, tipo)`): subir uno nuevo del mismo tipo reemplaza al anterior. |
| `nombre_archivo` | TEXT | Libre | Sí | Nombre original del archivo. |
| `tipo_mime` | TEXT | Libre | Sí | Tipo de archivo subido. |
| `contenido` | BLOB | Sin límite declarado | Sí | El archivo completo. |
| `rfc_subio` | TEXT | RFC (libre) | Sí | Quién subió el documento. |
| `fecha` | TEXT | `YYYY-MM-DD HH:MM:SS` | Sí | Cuándo se subió. |

## Decisiones de diseño que vale la pena tener presentes

- **`ahora_local()`** (`app/db/local_store.py`): cada INSERT/UPDATE pasa la
  fecha a mano en vez de depender de un `DEFAULT` de columna, porque
  `datetime('now')` de SQLite guarda en UTC (no hora local) y un
  `DEFAULT` de un `CREATE TABLE IF NOT EXISTS` no se aplica retroactivo a
  una tabla que ya existía.
- **Migraciones manuales** (`_migrar_columnas_faltantes`,
  `_migrar_tablas_renombradas`, `_migrar_llaves_de_identidad`): como no
  hay un framework de migraciones, cada columna agregada después del
  primer `CREATE TABLE` se añade a mano con `ALTER TABLE ... ADD COLUMN`
  dentro de estas funciones, guardado por `PRAGMA table_info` para no
  reintentar sobre una columna que ya existe. Corren en cada arranque,
  junto con el `CREATE TABLE IF NOT EXISTS` del esquema.
- **`especialidades_catalogo` se resiembra en cada arranque**: la fuente
  de verdad vive en el código (`especialidades_repo.py`), no en la tabla
  — así un ajuste de `orden_kpi` se refleja sin tocar la base a mano.
- **Claves propias en vez de IDs del sistema central**: tanto
  `proveedores.clave` como `citas_proveedor.folio` y
  `solicitudes_alta_medico.folio` son identificadores que genera este
  portal, no el sistema central — para que una recarga del Excel o un
  cambio del lado de SQL Server nunca invalide una referencia que ya
  tenían citas o solicitudes en curso.
