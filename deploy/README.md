# Plantillas de despliegue

> **El procedimiento completo está en
> [`DESPLIEGUE-PRODUCCION.md`](../DESPLIEGUE-PRODUCCION.md)**, en la raíz del
> proyecto: requerimientos por área, pasos, verificación y operación.
> Esta carpeta solo guarda los archivos que ese documento manda copiar.

| Archivo | Para qué | Dónde se usa |
|---|---|---|
| `portal-expedientes.service` | Servicio systemd que mantiene el portal arriba (un solo proceso) | Paso 5 |
| `desplegar.sh` | Actualiza el código a una etiqueta, instala dependencias, reinicia y verifica `/health` | Sección 6 |
| `github-actions-deploy.yml.ejemplo` | Workflow de ejemplo: etiqueta `v*` → producción. **No está activo** | Sección 6 |

Si cambia algo del procedimiento (un puerto, una variable del `.env`, un
paso), **se actualiza el documento de la raíz, no este archivo**: aquí solo
va lo que describe a las tres plantillas. Así no hay dos versiones del
procedimiento diciendo cosas distintas.
