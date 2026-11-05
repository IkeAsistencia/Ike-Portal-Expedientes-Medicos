"""
Paquete de repositorios: capa de acceso a datos del portal, separada en dos
fuentes según el módulo. SQL Server (SISE/sistema central) se consulta solo
vía Stored Procedures de solo lectura (ver app/db/connection.py); la base
SQLite propia de la app (app/db/local_store.py) guarda lo que no vive en
SISE (estatus, configuración, bitácoras, accesos). Revisar cada módulo para
saber cuál de las dos usa.
"""
