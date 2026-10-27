"""Catalyst package and its local development server command."""


def main() -> None:
    """Load independent fake response scripts and run the stdio MCP server."""
    import argparse
    import asyncio
    import logging
    import sqlite3
    import sys
    from pathlib import Path

    from catalyst_mcp.llm_client import FakeAnalysisProvider, FakeIdeationProvider
    from catalyst_mcp.repository import SQLiteRepository
    from catalyst_mcp.server import create_server, run_stdio

    parser = argparse.ArgumentParser(
        description="Run Catalyst over stdio with scripted fake analysis and ideation responses."
    )
    parser.add_argument("--database", type=Path, required=True, help="Persistent SQLite file.")
    parser.add_argument(
        "--fake-response", type=Path, action="append", default=[],
        help="UTF-8 analysis response file; repeat for calls and correction attempts.",
    )
    parser.add_argument(
        "--fake-ideation-response", type=Path, action="append", default=[],
        help="UTF-8 ideation response file; repeat for calls and correction attempts.",
    )
    args = parser.parse_args()
    try:
        responses = [path.read_text(encoding="utf-8") for path in args.fake_response]
        ideation_responses = [
            path.read_text(encoding="utf-8") for path in args.fake_ideation_response
        ]
    except (OSError, UnicodeError):
        parser.error("Could not read a fake-response file.")
    try:
        repository = SQLiteRepository(args.database)
    except (OSError, ValueError, sqlite3.Error):
        parser.error("Could not open the SQLite database.")

    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    logging.getLogger(__name__).warning(
        "Starting Catalyst with %d analysis and %d ideation scripted fake responses; no LLM is connected.",
        len(responses), len(ideation_responses),
    )
    server = create_server(
        provider=FakeAnalysisProvider(*responses),
        ideation_provider=FakeIdeationProvider(*ideation_responses),
        repository=repository,
    )
    asyncio.run(run_stdio(server))
