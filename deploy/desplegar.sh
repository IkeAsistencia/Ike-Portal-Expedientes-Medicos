#!/usr/bin/env bash
# Despliega en el servidor una rama o etiqueta del repo y verifica que el
# portal responda. Lo puede correr una persona por SSH o un workflow de
# GitHub Actions (ver github-actions-deploy.yml.ejemplo).
#
# Uso:  deploy/desplegar.sh <rama-o-etiqueta>
#   ej. deploy/desplegar.sh test      (QA)
#       deploy/desplegar.sh v1.0.0    (producción, siempre por etiqueta)
set -euo pipefail

REF="${1:?Indica la rama o etiqueta a desplegar, ej. test o v1.0.0}"
DIR="${PORTAL_DIR:-/opt/portal-expedientes}"
SERVICIO="${PORTAL_SERVICIO:-portal-expedientes}"
URL_SALUD="${PORTAL_URL_SALUD:-http://127.0.0.1:8000/health}"

cd "$DIR"
echo "==> Versión actual: $(git describe --tags --always)"
git fetch --tags origin
git checkout --force "$REF"
# Si es una rama, traer lo último; si es una etiqueta, no aplica.
if git show-ref --verify --quiet "refs/remotes/origin/$REF"; then
  git reset --hard "origin/$REF"
fi
echo "==> Desplegando: $(git describe --tags --always)"

.venv/bin/pip install --quiet -r requirements.txt
sudo systemctl restart "$SERVICIO"

for intento in $(seq 1 15); do
  if curl -fsS "$URL_SALUD" >/dev/null; then
    echo "==> OK: el portal responde en $URL_SALUD"
    exit 0
  fi
  sleep 2
done
echo "==> ERROR: el portal no respondió. Revisa: journalctl -u $SERVICIO -n 100" >&2
exit 1
