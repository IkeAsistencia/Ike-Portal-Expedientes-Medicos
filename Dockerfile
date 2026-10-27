# Imagen de desarrollo/local para correr el portal SIN instalar el driver
# ODBC de Microsoft en la máquina anfitriona (Windows) -- útil cuando
# soporte técnico todavía no lo instala ahí. El driver se instala aquí
# adentro, en Linux, siguiendo el procedimiento oficial de Microsoft:
# https://learn.microsoft.com/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server
#
# NO es (todavía) la imagen de producción: para eso, ver
# DESPLIEGUE-PRODUCCION.md, que hoy describe un despliegue sin contenedores
# (EC2 + systemd). Si más adelante se usa esta imagen en producción, hay
# que revisar ese documento para que ambos caminos queden consistentes.
FROM python:3.13-slim-bookworm

# Hora local de México: las fechas que guarda la app (estatus, comentarios,
# cortes) usan la hora del servidor, no UTC (ver README.md y
# DESPLIEGUE-PRODUCCION.md).
ENV TZ=America/Mexico_City
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo "$TZ" > /etc/timezone

# Driver ODBC 18 de Microsoft para SQL Server, vía el repositorio oficial
# de paquetes de Microsoft para Debian 12 (bookworm, la base de esta
# imagen). libgssapi-krb5-2 es un requisito no declarado del paquete
# (el driver lo enlaza en tiempo de ejecución) -- confirmado en la guía de
# instalación oficial.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gnupg ca-certificates \
    && curl -sSL -O https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb \
    && dpkg -i packages-microsoft-prod.deb \
    && rm packages-microsoft-prod.deb \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends \
        msodbcsql18 unixodbc-dev libgssapi-krb5-2 \
    && apt-get purge -y --auto-remove curl gnupg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Capa de dependencias aparte del código: cambiar un .py no reconstruye
# pip install, solo cambiar requirements.txt lo hace.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Sin --reload a propósito (igual que producción, ver DESPLIEGUE-PRODUCCION.md):
# para desarrollo con autorecarga, docker-compose.yml monta el código como
# volumen y sobreescribe este comando con --reload.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
