# Backend

Run these commands from the `backend` directory:

```powershell
uv sync
uv run python -m uvicorn app.gateway.app:app --host 127.0.0.1 --port 8000 --loop asyncio:SelectorEventLoop
```

The explicit selector event loop supports psycopg's asynchronous PostgreSQL
connections on Windows. It also works on Linux and macOS.

The application loads the repository's `.env` and `config.yaml`. With
`database.backend: postgres`, set `DATABASE_URL` in `.env` to a PostgreSQL
connection URL. Startup creates the configured schema and LangGraph checkpoint
tables. The database user needs permission to create the schema and tables.

Health check: <http://127.0.0.1:8000/health>

API documentation: <http://127.0.0.1:8000/docs>

Run the unit tests with `uv run python -m pytest -q`. To also verify checkpoint
persistence across application lifetimes against the configured PostgreSQL
database:

```powershell
$env:THESISFLOW_TEST_POSTGRES = '1'
uv run python -m pytest -q
```

The integration test uses a unique thread ID and removes its checkpoints after
verification. Agent conversation checkpoints persist in PostgreSQL; the run
registry and stream bridge remain in memory.
