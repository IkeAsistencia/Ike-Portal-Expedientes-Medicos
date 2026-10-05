"""
Ensamblado del schema GraphQL y el router para montarlo en FastAPI
(ver app/main.py: app.include_router(graphql_router, prefix="/graphql")).
"""

import strawberry
from strawberry.fastapi import GraphQLRouter

from app.graphql.context import get_context
from app.graphql.mutation import Mutation
from app.graphql.query import Query

schema = strawberry.Schema(query=Query, mutation=Mutation)

graphql_router = GraphQLRouter(
    schema,
    context_getter=get_context,
    # GraphiQL (explorador visual) viene activado por default en GET /graphql
)
