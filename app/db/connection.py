"""
Capa de acceso a SQL Server vía pyodbc, exclusivamente a través de
Stored Procedures (nunca se arma SQL dinámico contra tablas desde Python).

Se usa sintaxis "EXEC sp @param=?, ..." (parámetros con nombre) en vez de
la sintaxis ODBC "{CALL sp(?,?)}", porque esta última tiene problemas
conocidos en pyodbc al combinar Table-Valued Parameters (TVP) con
parámetros escalares en la misma llamada.
Ref: https://github.com/mkleehammer/pyodbc/issues/732

Para SPs de los que no conocemos el nombre exacto de sus parámetros
(ej. un SP legado ya existente), call_procedure/_write también aceptan
una tupla/lista posicional y arman "{CALL sp(?,?)}" en su lugar.
"""

from contextlib import contextmanager
from typing import Any, Optional, Union

import pyodbc

from app.config import get_settings

ParamsType = Union[dict[str, Any], tuple, list, None]


@contextmanager
def get_connection():
    settings = get_settings()
    conn = pyodbc.connect(settings.connection_string)
    try:
        yield conn
    finally:
        conn.close()


def _build_call(sp_name: str, params: ParamsType) -> tuple[str, list[Any]]:
    if params is None:
        return f"{{CALL {sp_name}}}", []

    if isinstance(params, dict):
        if not params:
            return f"EXEC {sp_name}", []
        assignments = ", ".join(f"@{name}=?" for name in params)
        return f"EXEC {sp_name} {assignments}", list(params.values())

    # Posicional (tupla/lista) — para SPs cuyo nombre de parámetro no
    # conocemos con certeza.
    placeholders = ",".join("?" for _ in params)
    query = f"{{CALL {sp_name} ({placeholders})}}" if params else f"{{CALL {sp_name}}}"
    return query, list(params)


def _fetch_first_resultset(cursor) -> tuple[list[str], list[tuple]]:
    """
    Devuelve (columnas, filas) del primer result set que sí trae datos.

    Algunos SPs (sobre todo legados) no siempre regresan un SELECT — por
    ejemplo, pueden no producir ningún result set cuando no hay nada que
    devolver (login con usuario inexistente), o intercalar mensajes de
    "filas afectadas" antes del SELECT real. Llamar fetchall() cuando
    cursor.description es None truena con
    "pyodbc.ProgrammingError: No results. Previous SQL was not a query.",
    así que hay que revisar cursor.description antes de leer, y avanzar
    con nextset() hasta encontrar un result set real (o quedarnos sin
    ninguno, lo cual es una respuesta válida: "no hay filas").
    """
    while cursor.description is None:
        if not cursor.nextset():
            return [], []
    columns = [col[0] for col in cursor.description]
    return columns, cursor.fetchall()


def call_procedure(sp_name: str, params: ParamsType = None) -> list[dict[str, Any]]:
    """Ejecuta un SP de solo lectura y regresa su primer result set."""
    query, values = _build_call(sp_name, params)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, values)
        columns, rows = _fetch_first_resultset(cursor)
        return [dict(zip(columns, row)) for row in rows]


def call_procedure_write(sp_name: str, params: ParamsType = None) -> list[dict[str, Any]]:
    """Igual que call_procedure, pero hace commit (SPs de inserción/actualización)."""
    query, values = _build_call(sp_name, params)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, values)
        columns, rows = _fetch_first_resultset(cursor)
        conn.commit()
        return [dict(zip(columns, row)) for row in rows]


def as_tvp_rows(values: list[int]) -> list[tuple[int]]:
    """Convierte una lista de enteros en filas para un TVP de una sola columna (dbo.IntList)."""
    return [(v,) for v in values]
