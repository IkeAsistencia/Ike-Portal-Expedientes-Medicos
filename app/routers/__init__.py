"""
Routers REST (FastAPI) del Portal Promédico, uno por pantalla/área de
negocio (expedientes, seguimiento, directorio de proveedores, accesos,
etc.). Se registran en app/main.py; la vía alterna GraphQL vive en
app/graphql/ y comparte reglas de negocio con varios de estos routers
a través de app/services y app/repositories.
"""
