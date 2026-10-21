# Despliegue en AWS (producción)

Plantillas para el servidor EC2 Linux donde corre el portal, siguiendo el
esquema de la empresa: **CloudFront + WAF → ALB → EC2 Linux** en subred
privada, con conexión al SQL Server de SISE por VPN o Direct Connect.

| Archivo | Para qué |
|---|---|
| `portal-expedientes.service` | Servicio systemd que mantiene el portal arriba (un solo proceso) |
| `desplegar.sh` | Actualiza el código a una etiqueta, instala dependencias, reinicia y verifica `/health` |
| `github-actions-deploy.yml.ejemplo` | Workflow de ejemplo: etiqueta `v*` → producción. **No está activo** |

## Qué se despliega

| | |
|---|---|
| Versión | Etiqueta `vX.Y.Z` hecha sobre `main`, **nunca una rama**: así se sabe exactamente qué está corriendo y se puede volver a la etiqueta anterior |
| Base de SISE | La productiva, con los scripts de `sql/` corridos |
| Dominio | `promedico.ikeasistencia.com` (propuesta) |

## Preparar el servidor (una sola vez)

1. Instalar Python 3.13, `git`, `unixODBC` y `msodbcsql18` (repositorio de
   Microsoft para la distribución). Zona horaria `America/Mexico_City`.
2. Crear el usuario del servicio y clonar el repo:
   ```bash
   sudo useradd --system --create-home portal
   sudo git clone https://github.com/IkeAsistencia/Ike-Portal-Expedientes-Medicos.git /opt/portal-expedientes
   sudo chown -R portal:portal /opt/portal-expedientes
   cd /opt/portal-expedientes
   sudo -u portal python3.13 -m venv .venv
   sudo -u portal .venv/bin/pip install -r requirements.txt
   ```
3. Crear el `.env` (ver la sección siguiente) con permisos `600` y dueño
   `portal`. La carpeta `data/` se crea sola al arrancar; **debe estar en un
   volumen persistente y respaldado**: ahí vive el SQLite con accesos,
   estatus, comentarios, comprobantes y cortes.
4. Instalar el servicio:
   ```bash
   sudo cp deploy/portal-expedientes.service /etc/systemd/system/
   sudo systemctl daemon-reload && sudo systemctl enable --now portal-expedientes
   ```
5. Permitir que el usuario `portal` reinicie solo su servicio (lo usa
   `desplegar.sh`), con `sudo visudo -f /etc/sudoers.d/portal`:
   ```
   portal ALL=(root) NOPASSWD: /usr/bin/systemctl restart portal-expedientes
   ```
6. Programar el job de alertas cada hora (`crontab -e` del usuario `portal`):
   ```
   TZ=America/Mexico_City
   0 * * * * cd /opt/portal-expedientes && .venv/bin/python -m jobs.validar_estatus_proveedor >> /var/log/portal-expedientes/job.log 2>&1
   ```
7. Dar de alta el primer **Administrador**; luego él da de alta a los demás
   desde el portal. Aquí **no** se corre `scripts/seed_usuarios_prueba.py`:
   ese script es de desarrollo y crea RFC de prueba con una contraseña
   conocida.
   ```bash
   cd /opt/portal-expedientes
   sudo -u portal .venv/bin/python -c "from app.db.local_store import init_local_db; from app.repositories import accesos_repo as a; init_local_db(); a.alta_acceso('ABCD123456', 'Nombre del administrador', a.PERFIL_ADMINISTRADOR)"
   ```

## `.env` de producción

Partir de `.env.example` y fijar, como mínimo:

| Variable | Valor en producción |
|---|---|
| `DB_AUTH_MODE` | `sql` (en Linux no hay autenticación de Windows) |
| `DB_SERVER`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | Los de la base productiva; el usuario solo con permisos de ejecución (ver `sql/README.md`) |
| `DB_DRIVER` | `ODBC Driver 18 for SQL Server` |
| `DB_TRUST_SERVER_CERTIFICATE` | `false` si el SQL Server tiene certificado válido; si no, `true` y documentarlo |
| `JWT_SECRET_KEY` | Uno **propio, que no se repita en ningún otro lado**: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `PROXIES_CONFIABLES` | `2` con CloudFront + ALB; `1` si solo hay ALB |
| `GRAPHQL_IDE_HABILITADO` | `false` |
| `CORS_ALLOWED_ORIGINS` | vacío |
| `LOGIN_LEGADO_HABILITADO` | `false` |
| `SMTP_*` | Datos del SMTP corporativo; sin ellos los correos solo se simulan |
| `CUENTAS_PERMITIDAS` | La lista acordada |
| `DENUE_TOKEN` | Token del API del DENUE (INEGI). **Sin él, la búsqueda fuera de la red del Directorio queda apagada**: el portal responde que no está configurada, sin romperse. Se tramita gratis en el INEGI |

`DENUE_TIMEOUT_SEGUNDOS` y `DENUE_MAXIMO_RESULTADOS` tienen un valor por
omisión razonable; solo hay que tocarlos si el INEGI responde lento.

## Requisitos del lado de AWS

- **Security group de la EC2:** puerto 8000 abierto **solo** desde el ALB
  (la app confía en `X-Forwarded-For`; nadie más debe llegarle directo).
  Salida a SQL Server (TCP 1533) y al SMTP (TCP 587).
- **Salida a internet por HTTPS (TCP 443), con NAT gateway.** La búsqueda
  fuera de la red consulta el API del DENUE (`www.inegi.org.mx`) **desde el
  servidor**, no desde el navegador del usuario. Al estar la EC2 en subred
  privada, sin NAT esa consulta falla por más que `DENUE_TOKEN` esté bien
  puesto. Es la única salida a internet que necesita el portal; si no se
  autoriza, el resto del portal funciona igual y solo esa búsqueda queda
  inhabilitada.
- **ALB:** health check en `GET /health`; límite de carga de al menos
  6 MB (comprobantes de hasta 5 MB).
- **CloudFront:** sin caché para la API y reenviando el encabezado
  `Authorization`; solo `/css/*`, `/js/*` e `/img/*` pueden cachearse.
  Publicar en la raíz del dominio, no en una subruta.
- **Una sola instancia**, sin Auto Scaling de varias réplicas.
- **Respaldo** del volumen donde está `data/`.

## Desplegar y regresar a la versión anterior

```bash
# Siempre por etiqueta, nunca por rama
sudo -u portal /opt/portal-expedientes/deploy/desplegar.sh v1.0.0

# Si algo falla: volver a la etiqueta anterior
sudo -u portal /opt/portal-expedientes/deploy/desplegar.sh v0.9.0
```

**Antes de regresar de versión, respalda `data/app_local.db`.** Si la
versión nueva cambió la estructura del SQLite, la anterior podría no
leerlo bien; con el respaldo se puede volver al estado previo.

## Verificación después de desplegar

1. `curl -fsS https://<dominio>/health` responde `{"status":"ok"}`.
2. Entrar con un RFC de cada perfil (Administrador, Cabina, Proveedor).
3. Cabina envía un correo a un proveedor de prueba y llega de verdad.
4. En el Directorio, una búsqueda **fuera de la red** devuelve resultados.
   Es lo que comprueba de una vez el `DENUE_TOKEN` y la salida a internet;
   si responde que no está configurada, falta el token, y si da error de
   conexión, falta el NAT.
5. `journalctl -u portal-expedientes -n 100` sin errores.
