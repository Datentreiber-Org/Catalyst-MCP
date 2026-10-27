"""Stdio MCP interface for the existing analysis workflow."""

import asyncio
import logging
import sqlite3
from importlib.metadata import version

from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)
from pydantic import ValidationError

from catalyst_mcp.llm_client import AnalysisProvider
from catalyst_mcp.models import AnalyzeBusinessModelInput, BusinessArtifact
from catalyst_mcp.repository import SQLiteRepository
from catalyst_mcp.services import (
    DEFAULT_MAX_BUSINESS_CONTENT_CHARS,
    analyze_business_model,
)


logger = logging.getLogger(__name__)


def _tool_error(message: str) -> CallToolResult:
    """Log a fixed summary and return an MCP error without a success payload."""
    logger.warning("analyze-business-model failed: %s", message)
    return CallToolResult(
        content=[TextContent(type="text", text=message)], is_error=True
    )


def create_server(
    *, provider: AnalysisProvider, repository: SQLiteRepository
) -> Server:
    """Register analysis using injected generation and persistence dependencies."""
    input_schema = AnalyzeBusinessModelInput.model_json_schema()
    input_schema["properties"]["businessContent"]["maxLength"] = (
        DEFAULT_MAX_BUSINESS_CONTENT_CHARS
    )
    analysis_tool = Tool(
        name="analyze-business-model",
        description="Analyze business text and return the complete saved Business Artifact.",
        input_schema=input_schema,
        output_schema=BusinessArtifact.model_json_schema(mode="serialization"),
    )

    async def list_tools(
        ctx: ServerRequestContext, params: PaginatedRequestParams | None
    ) -> ListToolsResult:
        """Advertise the analysis tool and its exact input and output schemas."""
        return ListToolsResult(tools=[analysis_tool])

    async def call_tool(
        ctx: ServerRequestContext, params: CallToolRequestParams
    ) -> CallToolResult:
        """Validate arguments, run analysis and wrap its committed result."""
        if params.name != "analyze-business-model":
            return _tool_error("Unknown tool.")
        try:
            request = AnalyzeBusinessModelInput.model_validate(params.arguments)
        except ValidationError:
            return _tool_error(
                "Invalid analysis input: supply only non-blank businessContent text."
            )
        if len(request.businessContent) > DEFAULT_MAX_BUSINESS_CONTENT_CHARS:
            return _tool_error(
                f"businessContent exceeds maximum of {DEFAULT_MAX_BUSINESS_CONTENT_CHARS} characters."
            )

        try:
            artifact = await asyncio.to_thread(
                analyze_business_model,
                request.businessContent,
                provider=provider,
                repository=repository,
            )
        except TimeoutError:
            return _tool_error("Analysis provider timed out. No Business Artifact was saved.")
        except sqlite3.Error:
            return _tool_error("Could not save the Business Artifact.")
        except ValueError:
            return _tool_error(
                "Analysis could not produce a usable Business Artifact. Check the business content."
            )
        except Exception:
            return _tool_error("Analysis failed. No Business Artifact was saved.")

        logger.info("analyze-business-model saved artifact_id=%s", artifact.id)
        return CallToolResult(
            content=[TextContent(type="text", text=artifact.model_dump_json())],
            structured_content=artifact.model_dump(mode="json"),
        )

    return Server(
        "Catalyst",
        version=version("catalyst-mcp"),
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


async def run_stdio(server: Server) -> None:
    """Serve MCP over stdin/stdout until the client disconnects."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )
