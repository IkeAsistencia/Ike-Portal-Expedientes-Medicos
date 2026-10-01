"""
Ensamblado del schema GraphQL y el router para montarlo en FastAPI
(ver app/main.py: app.include_router(graphql_router, prefix="/graphql")).
"""

import strawberry
from strawberry.extensions import AddValidationRules
from strawberry.fastapi import GraphQLRouter
from graphql.validation import NoSchemaIntrospectionCustomRule

from app.config import get_arranque_settings
from app.graphql.context import get_context
from app.graphql.mutation import Mutation
from app.graphql.query import Query

_settings = get_arranque_settings()

# GraphiQL (explorador visual) e introspección: cómodos en desarrollo, pero
# exponen el schema completo (todas las queries/mutations/tipos) sin
# autenticación -- ver GRAPHQL_IDE_HABILITADO en .env. Ejecutar cada
# operación real sigue exigiendo el token correspondiente de todas formas.
_extensions = [] if _settings.graphql_ide_habilitado else [AddValidationRules([NoSchemaIntrospectionCustomRule])]

schema = strawberry.Schema(query=Query, mutation=Mutation, extensions=_extensions)

graphql_router = GraphQLRouter(
    schema,
    context_getter=get_context,
    graphql_ide="graphiql" if _settings.graphql_ide_habilitado else None,
)
