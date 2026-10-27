"""Stdio MCP tools and canonical JSON resources for saved records."""

import asyncio
import logging
import sqlite3
from importlib.metadata import version

from mcp import MCPError
from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.types import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    ListResourcesResult,
    PaginatedRequestParams,
    ReadResourceRequestParams,
    ReadResourceResult,
    Resource,
    TextContent,
    TextResourceContents,
    Tool,
)
from pydantic import ValidationError

from catalyst_mcp.llm_client import AnalysisProvider, IdeationProvider
from catalyst_mcp.models import (
    AnalyzeBusinessModelInput,
    BusinessArtifact,
    IdeateUseCaseInput,
    UseCaseCatalog,
)
from catalyst_mcp.repository import SQLiteRepository
from catalyst_mcp.services import (
    DEFAULT_MAX_BUSINESS_CONTENT_CHARS,
    DEFAULT_MAX_NUMBER_OF_IDEAS,
    SourceArtifactNotFoundError,
    analyze_business_model,
    ideate_use_case,
)


logger = logging.getLogger(__name__)
_ARTIFACT_JSON_PREFIX = "catalyst://business-artifact/"
_CATALOG_JSON_PREFIX = "catalyst://use-case-catalog/"


def _tool_error(tool_name: str, message: str) -> CallToolResult:
    """Log a fixed summary and return an MCP error without a success payload."""
    logger.warning("%s failed: %s", tool_name, message)
    return CallToolResult(
        content=[TextContent(type="text", text=message)], is_error=True
    )


def _resource_error(operation: str, code: int, message: str) -> MCPError:
    """Log a fixed summary and construct a resource protocol error."""
    logger.warning("%s failed: %s", operation, message)
    return MCPError(code=code, message=message)


def _list_json_resources(repository: SQLiteRepository) -> list[Resource]:
    """Describe all saved records as JSON, in record-type then ID order."""
    resources = [
        Resource(
            uri=artifact.uri,
            name=f"{artifact.name} ({artifact.id}, JSON)",
            mime_type="application/json",
        )
        for artifact in repository.list_business_artifacts()
    ]
    resources.extend(
        Resource(
            uri=f"{_CATALOG_JSON_PREFIX}{catalog.id}",
            name=f"Use-case Catalog {catalog.id} (JSON)",
            mime_type="application/json",
        )
        for catalog in repository.list_use_case_catalogs()
    )
    return resources


def _read_json_resource(repository: SQLiteRepository, uri: str) -> str | None:
    """Read one literal canonical URI and serialize its complete saved object."""
    if uri.startswith(_ARTIFACT_JSON_PREFIX):
        record = repository.get_business_artifact(uri[len(_ARTIFACT_JSON_PREFIX):])
    elif uri.startswith(_CATALOG_JSON_PREFIX):
        record = repository.get_use_case_catalog(uri[len(_CATALOG_JSON_PREFIX):])
    else:
        return None
    return record.model_dump_json() if record is not None else None


def create_server(
    *,
    provider: AnalysisProvider,
    ideation_provider: IdeationProvider,
    repository: SQLiteRepository,
) -> Server:
    """Register both tools with separate providers and shared persistence."""
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
    ideation_input_schema = IdeateUseCaseInput.model_json_schema()
    ideation_input_schema["properties"]["numberOfIdeas"]["maximum"] = (
        DEFAULT_MAX_NUMBER_OF_IDEAS
    )
    ideation_tool = Tool(
        name="ideate-use-case",
        description="Generate aligned use cases from a saved artifact and return the complete saved Catalog.",
        input_schema=ideation_input_schema,
        output_schema=UseCaseCatalog.model_json_schema(mode="serialization"),
    )

    async def list_tools(
        ctx: ServerRequestContext, params: PaginatedRequestParams | None
    ) -> ListToolsResult:
        """Advertise both tools with their exact input and output schemas."""
        return ListToolsResult(tools=[analysis_tool, ideation_tool])

    async def analyze(arguments: dict[str, object] | None) -> CallToolResult:
        """Validate analysis arguments and return the complete committed artifact."""
        try:
            request = AnalyzeBusinessModelInput.model_validate(arguments)
        except ValidationError:
            return _tool_error(
                "analyze-business-model",
                "Invalid analysis input: supply only non-blank businessContent text."
            )
        if len(request.businessContent) > DEFAULT_MAX_BUSINESS_CONTENT_CHARS:
            return _tool_error(
                "analyze-business-model",
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
            return _tool_error(
                "analyze-business-model", "Analysis provider timed out. No Business Artifact was saved."
            )
        except sqlite3.Error:
            return _tool_error("analyze-business-model", "Could not save the Business Artifact.")
        except ValueError:
            return _tool_error(
                "analyze-business-model",
                "Analysis could not produce a usable Business Artifact. Check the business content."
            )
        except Exception:
            return _tool_error("analyze-business-model", "Analysis failed. No Business Artifact was saved.")

        logger.info("analyze-business-model saved artifact_id=%s", artifact.id)
        return CallToolResult(
            content=[TextContent(type="text", text=artifact.model_dump_json())],
            structured_content=artifact.model_dump(mode="json"),
        )

    async def ideate(arguments: dict[str, object] | None) -> CallToolResult:
        """Validate ideation arguments and return the complete committed Catalog."""
        try:
            request = IdeateUseCaseInput.model_validate(arguments)
        except ValidationError:
            return _tool_error(
                "ideate-use-case",
                "Invalid ideation input: supply artifactId, a positive integer numberOfIdeas "
                "and optional non-blank focus; no extra fields.",
            )
        if request.numberOfIdeas > DEFAULT_MAX_NUMBER_OF_IDEAS:
            return _tool_error(
                "ideate-use-case",
                f"numberOfIdeas exceeds maximum of {DEFAULT_MAX_NUMBER_OF_IDEAS}.",
            )

        try:
            catalog = await asyncio.to_thread(
                ideate_use_case,
                request.artifactId,
                request.numberOfIdeas,
                focus=request.focus,
                provider=ideation_provider,
                repository=repository,
            )
        except SourceArtifactNotFoundError:
            return _tool_error("ideate-use-case", "Source Business Artifact was not found.")
        except TimeoutError:
            return _tool_error("ideate-use-case", "Ideation provider timed out. No Use-case Catalog was saved.")
        except sqlite3.Error:
            return _tool_error("ideate-use-case", "Could not read the source or save the Use-case Catalog.")
        except ValueError:
            return _tool_error(
                "ideate-use-case",
                "Ideation could not produce a usable Use-case Catalog. Check the source Business Artifact.",
            )
        except Exception:
            return _tool_error("ideate-use-case", "Ideation failed. No Use-case Catalog was saved.")

        logger.info("ideate-use-case saved catalog_id=%s", catalog.id)
        return CallToolResult(
            content=[TextContent(type="text", text=catalog.model_dump_json())],
            structured_content=catalog.model_dump(mode="json"),
        )

    async def call_tool(
        ctx: ServerRequestContext, params: CallToolRequestParams
    ) -> CallToolResult:
        """Dispatch only the two registered tool names to their handlers."""
        if params.name == "analyze-business-model":
            return await analyze(params.arguments)
        if params.name == "ideate-use-case":
            return await ideate(params.arguments)
        return _tool_error("tools/call", "Unknown tool.")

    async def list_resources(
        ctx: ServerRequestContext, params: PaginatedRequestParams | None
    ) -> ListResourcesResult:
        """Advertise the current saved JSON records as one complete page."""
        if params is not None and params.cursor is not None:
            raise _resource_error("resources/list", INVALID_PARAMS, "Resource listing does not accept a cursor.")
        try:
            resources = await asyncio.to_thread(_list_json_resources, repository)
        except Exception:
            raise _resource_error("resources/list", INTERNAL_ERROR, "Could not list saved resources.") from None
        return ListResourcesResult(resources=resources)

    async def read_resource(
        ctx: ServerRequestContext, params: ReadResourceRequestParams
    ) -> ReadResourceResult:
        """Return complete JSON or a fixed protocol error without writing data."""
        try:
            payload = await asyncio.to_thread(_read_json_resource, repository, params.uri)
        except Exception:
            raise _resource_error("resources/read", INTERNAL_ERROR, "Could not read saved resource.") from None
        if payload is None:
            raise _resource_error("resources/read", INVALID_PARAMS, "Resource not found.")
        return ReadResourceResult(contents=[
            TextResourceContents(uri=params.uri, mime_type="application/json", text=payload)
        ])

    return Server(
        "Catalyst",
        version=version("catalyst-mcp"),
        on_list_tools=list_tools,
        on_call_tool=call_tool,
        on_list_resources=list_resources,
        on_read_resource=read_resource,
    )


async def run_stdio(server: Server) -> None:
    """Serve MCP over stdin/stdout until the client disconnects."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )
