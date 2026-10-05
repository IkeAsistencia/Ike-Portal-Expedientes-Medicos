# Jobs programados

## validar_estatus_proveedor.py

Revisa expedientes con proveedor asignado sin respuesta y manda alertas
por correo (naranja a las 8h, rojo a las 24h). Ver el docstring del
archivo para el detalle completo de las reglas y los supuestos.

### Probarlo manualmente

```bash
python -m jobs.validar_estatus_proveedor
```

Corre igual que cualquier script de este proyecto: usa el mismo `.env`
(conexión a SQL Server) y la misma base local SQLite.

### Programarlo en Windows (Programador de tareas)

Este script **no debe quedarse corriendo indefinidamente** — está hecho
para ejecutarse, hacer su revisión, y terminar. Prográmalo para que
corra cada hora (o el intervalo que prefieran):

1. Abre **Programador de tareas** (`taskschd.msc`).
2. **Crear tarea básica...** → nómbrala, por ejemplo, `Validar estatus proveedor`.
3. Desencadenador: **Diariamente**, repetir cada 1 hora, durante todo el día
   (en la pestaña "Opciones avanzadas" de un desencadenador diario puedes
   marcar "Repetir la tarea cada:" 1 hora, "durante:" 1 día).
4. Acción: **Iniciar un programa**.
   - Programa/script: la ruta completa a `python.exe` **dentro de tu
     entorno virtual**, ej. `C:\ruta\al\proyecto\.venv\Scripts\python.exe`
   - Agregar argumentos: `-m jobs.validar_estatus_proveedor`
   - Iniciar en: la carpeta raíz del proyecto, ej. `C:\ruta\al\proyecto`
     (importante — si no, no va a encontrar el `.env` ni el paquete `app`)
5. Guarda la tarea. Puedes probarla con clic derecho → **Ejecutar**, y
   revisar el log que imprime en consola (o redirigir la salida a un
   archivo agregando `> log.txt 2>&1` si programas la tarea con un `.bat`
   intermedio en vez de invocar python.exe directo).

### Por qué un script aparte y no un scheduler dentro de la API

Se recomienda esto (en vez de, por ejemplo, `APScheduler` corriendo
dentro del proceso de `uvicorn`) porque:

- Si la API se reinicia o se cae, el cron no depende de que siga viva.
- Si en algún momento la API corre con más de un worker/proceso, un
  scheduler embebido correría el riesgo de duplicar el envío de
  alertas; un script externo programado una sola vez no tiene ese
  problema.
- Es más fácil de monitorear/reintentar desde las herramientas propias
  de Windows que ya usa el equipo.

### Pendiente de confirmar

- Los datos reales de SMTP (host, puerto, usuario, contraseña,
  remitente) en el `.env` — mientras no estén, el envío queda
  "simulado" (se registra en el log, no se manda un correo real).
- El correo real al que hay que escribirle (el del proveedor, no el del
  paciente/usuario) — ver el aviso al inicio de
  `app/services/email_service.py`.
- Si "8 horas" y "más de 24 horas" son un corte escalonado (como se
  implementó: 8-24h naranja, 24h+ rojo) o si ambos umbrales deben
  evaluarse de forma independiente.
