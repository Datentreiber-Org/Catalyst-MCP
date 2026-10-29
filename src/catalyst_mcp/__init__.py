"""Catalyst package and its local development server command."""


def main() -> None:
    """Select explicit live or scripted analysis and run the stdio MCP server."""
    import argparse
    import asyncio
    import logging
    import sqlite3
    import sys
    from pathlib import Path

    from catalyst_mcp.llm_client import (
        AnalysisProvider, FakeAnalysisProvider, FakeIdeationProvider,
        LLMAnalysisProvider, create_json_client,
    )
    from catalyst_mcp.repository import SQLiteRepository
    from catalyst_mcp.server import create_server, run_stdio
    from catalyst_mcp.settings import LLMSettings

    parser = argparse.ArgumentParser(
        description="Run Catalyst over stdio with optional live analysis and scripted fake responses."
    )
    parser.add_argument("--database", type=Path, required=True, help="Persistent SQLite file.")
    analysis_mode = parser.add_mutually_exclusive_group()
    analysis_mode.add_argument(
        "--live-analysis", action="store_true",
        help="Use the configured LLM provider/model for analysis; read LLM environment settings.",
    )
    analysis_mode.add_argument(
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
    analysis_provider: AnalysisProvider
    try:
        if args.live_analysis:
            settings = LLMSettings.from_env()
            analysis_provider = LLMAnalysisProvider(create_json_client(settings))
        else:
            analysis_provider = FakeAnalysisProvider(*responses)
    except (OSError, UnicodeError, ValueError):
        parser.error("Could not configure live analysis. Check LLM environment settings and the packaged prompt.")
    try:
        repository = SQLiteRepository(args.database)
    except (OSError, ValueError, sqlite3.Error):
        parser.error("Could not open the SQLite database.")

    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    if args.live_analysis:
        logging.getLogger(__name__).warning(
            "Starting Catalyst with live analysis provider=%s and %d ideation scripted fake responses.",
            settings.provider, len(ideation_responses),
        )
    else:
        logging.getLogger(__name__).warning(
            "Starting Catalyst with %d analysis and %d ideation scripted fake responses; no LLM is connected.",
            len(responses), len(ideation_responses),
        )
    server = create_server(
        provider=analysis_provider,
        ideation_provider=FakeIdeationProvider(*ideation_responses),
        repository=repository,
    )
    asyncio.run(run_stdio(server))
