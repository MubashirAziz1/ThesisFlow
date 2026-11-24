""" PostgreSQL schema helpers. """

from __future__ import annotations

import re
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from ..config.postgres_schema import validate_postgres_schema


def build_psycopg_options(schema: str) -> str:
    """Return libpq options for a validated schema identifier."""
    validate_postgres_schema(schema)
    return f"-c search_path={schema}" if schema else ""


def _split_libpq_options(options: str) -> list[str]:
    """Split libpq options, where backslashes escape the next character."""
    tokens: list[str] = []
    token: list[str] = []
    escaped = False
    for char in options:
        if escaped:
            token.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char.isspace():
            if token:
                tokens.append("".join(token))
                token = []
        else:
            token.append(char)
    if escaped:
        token.append("\\")
    if token:
        tokens.append("".join(token))
    return tokens


def _join_libpq_options(tokens: list[str]) -> str:
    """Escape whitespace and backslashes when rebuilding libpq options."""
    return " ".join(re.sub(r"([\\\s])", r"\\\1", token) for token in tokens)

def build_asyncpg_connect_args(schema: str) -> dict:
    """ Return SQLAlchemy ``connect_args`` that pin asyncpg's search_path. """
    if not schema:
        return {}
    return {"server_settings": {"search_path": schema}}


def _merge_search_path_option(existing_options: str, schema: str) -> str:
    """Return libpq options with search_path replaced while preserving others."""
    new_option = build_psycopg_options(schema)
    if not new_option:
        return existing_options

    if not existing_options:
        return new_option

    tokens = _split_libpq_options(existing_options)

    merged: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "-c" and index + 1 < len(tokens):
            setting = tokens[index + 1]
            if setting.split("=", 1)[0] == "search_path":
                index += 2
                continue
            merged.extend([token, setting])
            index += 2
            continue
        if token.startswith("-csearch_path="):
            index += 1
            continue
        merged.append(token)
        index += 1

    merged.extend(_split_libpq_options(new_option))
    return _join_libpq_options(merged)


def create_schema_sql(schema: str) -> str | None:
    """Return a safe CREATE SCHEMA statement for a validated plain identifier.

    Defense-in-depth: the identifier is re-validated here rather than trusting
    the distant pydantic validator. ``create_schema_sql`` is publicly exported
    and psycopg accepts multiple ``;``-separated statements, so a future caller
    that bypasses ``DatabaseConfig``/``CheckpointerConfig`` (e.g. a test helper)
    must not be able to inject SQL through this f-string boundary.
    """
    if not schema:
        return None
    validate_postgres_schema(schema)
    return f'CREATE SCHEMA IF NOT EXISTS "{schema}"'


def normalize_libpq_dsn(dsn: str) -> str:
    """Return *dsn* with any SQLAlchemy ``+driver`` suffix dropped.
    """
    parts = urlsplit(dsn)
    if not parts.scheme:
        return dsn
    scheme_base = parts.scheme.split("+", 1)[0]
    if scheme_base not in {"postgres", "postgresql"}:
        raise ValueError(f"Unsupported PostgreSQL DSN scheme for schema injection: {parts.scheme!r}")
    if scheme_base == parts.scheme:
        return dsn
    return urlunsplit((scheme_base, parts.netloc, parts.path, parts.query, parts.fragment))


def dsn_with_search_path(dsn: str, schema: str) -> str:
    """Return *dsn* with an ``options=-c search_path=<schema>`` query param. 
       Used for psycopg ``from_conn_string`` call sites."""

    dsn = normalize_libpq_dsn(dsn)
    if not schema:
        return dsn
    parts = urlsplit(dsn)

    if not parts.scheme:
        from psycopg.conninfo import conninfo_to_dict, make_conninfo

        params = conninfo_to_dict(dsn)
        params["options"] = _merge_search_path_option(params.get("options", ""), schema)
        return make_conninfo(**params)

    options_values: list[str] = []
    preserved: list[str] = []
    for pair in parts.query.split("&"):
        if not pair:
            continue
        raw_key, _, raw_value = pair.partition("=")
        if unquote(raw_key) == "options":
            options_values.append(unquote(raw_value))
        else:
            preserved.append(pair)

    options = _merge_search_path_option(" ".join(options_values), schema)
    # quote() encodes space as %20 (libpq-safe) and a literal '+' as %2B, so the
    # merged value keeps both distinctions.
    query = "&".join([*preserved, f"options={quote(options, safe='')}"])
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))

