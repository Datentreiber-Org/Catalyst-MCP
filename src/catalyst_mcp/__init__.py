"""Catalyst package and its local development server command."""


def main() -> None:
    """Select independent live or scripted generation and run the stdio MCP server."""
    import argparse
    import asyncio
    import logging
    import sqlite3
    import sys
    from pathlib import Path

    from catalyst_mcp.llm_client import (
        AnalysisProvider, FakeAnalysisProvider, FakeIdeationProvider, IdeationProvider,
        LLMAnalysisProvider, LLMIdeationProvider, create_json_client,
    )
    from catalyst_mcp.repository import SQLiteRepository
    from catalyst_mcp.server import create_server, run_stdio
    from catalyst_mcp.settings import LLMSettings

    parser = argparse.ArgumentParser(
        description="Run Catalyst over stdio with independently selected live or scripted generation."
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
    ideation_mode = parser.add_mutually_exclusive_group()
    ideation_mode.add_argument(
        "--live-ideation", action="store_true",
        help="Use the configured LLM provider/model for ideation from a saved artifact.",
    )
    ideation_mode.add_argument(
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
    analysis_provider: AnalysisProvider = FakeAnalysisProvider(*responses)
    ideation_provider: IdeationProvider = FakeIdeationProvider(*ideation_responses)
    try:
        if args.live_analysis or args.live_ideation:
            settings = LLMSettings.from_env()
            client = create_json_client(settings)
            if args.live_analysis:
                analysis_provider = LLMAnalysisProvider(client)
            if args.live_ideation:
                ideation_provider = LLMIdeationProvider(client)
    except (OSError, UnicodeError, ValueError):
        parser.error("Could not configure live generation. Check LLM environment settings and packaged prompts.")
    try:
        repository = SQLiteRepository(args.database)
    except (OSError, ValueError, sqlite3.Error):
        parser.error("Could not open the SQLite database.")

    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    if args.live_analysis and args.live_ideation:
        logging.getLogger(__name__).warning(
            "Starting Catalyst with live analysis provider=%s and live ideation provider=%s.",
            settings.provider, settings.provider,
        )
    elif args.live_analysis:
        logging.getLogger(__name__).warning(
            "Starting Catalyst with live analysis provider=%s and %d ideation scripted fake responses.",
            settings.provider, len(ideation_responses),
        )
    elif args.live_ideation:
        logging.getLogger(__name__).warning(
            "Starting Catalyst with %d analysis scripted fake responses and live ideation provider=%s.",
            len(responses), settings.provider,
        )
    else:
        logging.getLogger(__name__).warning(
            "Starting Catalyst with %d analysis and %d ideation scripted fake responses; no LLM is connected.",
            len(responses), len(ideation_responses),
        )
    server = create_server(
        provider=analysis_provider,
        ideation_provider=ideation_provider,
        repository=repository,
    )
    asyncio.run(run_stdio(server))
