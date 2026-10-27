"""Catalyst package and its local development server command."""


def main() -> None:
    """Load an explicit fake response script and run the stdio MCP server."""
    import argparse
    import asyncio
    import logging
    import sqlite3
    import sys
    from pathlib import Path

    from catalyst_mcp.llm_client import FakeAnalysisProvider
    from catalyst_mcp.repository import SQLiteRepository
    from catalyst_mcp.server import create_server, run_stdio

    parser = argparse.ArgumentParser(
        description="Run Catalyst over stdio with scripted fake analysis responses."
    )
    parser.add_argument("--database", type=Path, required=True, help="Persistent SQLite file.")
    parser.add_argument(
        "--fake-response", type=Path, action="append", required=True,
        help="UTF-8 provider response file; repeat for calls and correction attempts.",
    )
    args = parser.parse_args()
    try:
        responses = [path.read_text(encoding="utf-8") for path in args.fake_response]
    except (OSError, UnicodeError):
        parser.error("Could not read a fake-response file.")
    try:
        repository = SQLiteRepository(args.database)
    except (OSError, ValueError, sqlite3.Error):
        parser.error("Could not open the SQLite database.")

    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    logging.getLogger(__name__).warning(
        "Starting Catalyst with %d scripted fake responses; no LLM is connected.",
        len(responses),
    )
    server = create_server(
        provider=FakeAnalysisProvider(*responses), repository=repository
    )
    asyncio.run(run_stdio(server))
