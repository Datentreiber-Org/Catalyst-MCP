"""Stdio MCP tools and JSON/Markdown resources for complete saved records."""

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
    ResourceLink,
    TextContent,
    TextResourceContents,
    Tool,
)
from pydantic import ValidationError

from catalyst_mcp.llm_client import AnalysisProvider, IdeationProvider
from catalyst_mcp.markdown_views import render_business_artifact, render_use_case_catalog
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
_MARKDOWN_SUFFIX = "/view.md"


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


def _resource_views(record: BusinessArtifact | UseCaseCatalog) -> list[Resource]:
    """Describe the JSON and Markdown views without rendering or storing either."""
    if isinstance(record, BusinessArtifact):
        uri = record.uri
        name = f"{record.name} [{record.id}]"
    else:
        uri = f"{_CATALOG_JSON_PREFIX}{record.id}"
        name = f"Use-case Catalog {record.id}"
    return [
        Resource(
            uri=uri,
            name=f"{name} (JSON)",
            mime_type="application/json",
        ),
        Resource(
            uri=f"{uri}{_MARKDOWN_SUFFIX}",
            name=f"{name} (Markdown)",
            mime_type="text/markdown",
        ),
    ]


def _saved_tool_result(record: BusinessArtifact | UseCaseCatalog) -> CallToolResult:
    """Wrap a committed record with complete JSON and links to both resource views."""
    links = [
        ResourceLink(type="resource_link", **view.model_dump())
        for view in _resource_views(record)
    ]
    return CallToolResult(
        content=[TextContent(type="text", text=record.model_dump_json()), *links],
        structured_content=record.model_dump(mode="json"),
    )


def _list_saved_resources(repository: SQLiteRepository) -> list[Resource]:
    """List JSON/Markdown pairs in record-type then ID order, rejecting URI collisions."""
    records = [*repository.list_business_artifacts(), *repository.list_use_case_catalogs()]
    resources = [view for record in records for view in _resource_views(record)]
    if len({resource.uri for resource in resources}) != len(resources):
        raise ValueError("Saved record resource URIs collide")
    return resources


def _load_saved_record(
    repository: SQLiteRepository, uri: str
) -> BusinessArtifact | UseCaseCatalog | None:
    """Resolve one literal canonical URI without decoding or changing the identifier."""
    if uri.startswith(_ARTIFACT_JSON_PREFIX):
        return repository.get_business_artifact(uri[len(_ARTIFACT_JSON_PREFIX):])
    if uri.startswith(_CATALOG_JSON_PREFIX):
        return repository.get_use_case_catalog(uri[len(_CATALOG_JSON_PREFIX):])
    return None


def _read_saved_resource(
    repository: SQLiteRepository, uri: str
) -> TextResourceContents | None:
    """Preserve canonical JSON reads, otherwise render an exact Markdown-view URI."""
    record = _load_saved_record(repository, uri)
    if record is not None:
        return TextResourceContents(
            uri=uri, mime_type="application/json", text=record.model_dump_json()
        )
    if not uri.endswith(_MARKDOWN_SUFFIX):
        return None
    record = _load_saved_record(repository, uri[:-len(_MARKDOWN_SUFFIX)])
    if record is None:
        return None
    markdown = (
        render_business_artifact(record)
        if isinstance(record, BusinessArtifact)
        else render_use_case_catalog(record)
    )
    return TextResourceContents(uri=uri, mime_type="text/markdown", text=markdown)


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
        return _saved_tool_result(artifact)

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
        return _saved_tool_result(catalog)

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
        """Advertise both views of every saved record as one complete page."""
        if params is not None and params.cursor is not None:
            raise _resource_error("resources/list", INVALID_PARAMS, "Resource listing does not accept a cursor.")
        try:
            resources = await asyncio.to_thread(_list_saved_resources, repository)
        except Exception:
            raise _resource_error("resources/list", INTERNAL_ERROR, "Could not list saved resources.") from None
        return ListResourcesResult(resources=resources)

    async def read_resource(
        ctx: ServerRequestContext, params: ReadResourceRequestParams
    ) -> ReadResourceResult:
        """Return complete JSON/Markdown or a fixed protocol error without writing data."""
        try:
            content = await asyncio.to_thread(_read_saved_resource, repository, params.uri)
        except Exception:
            raise _resource_error("resources/read", INTERNAL_ERROR, "Could not read saved resource.") from None
        if content is None:
            raise _resource_error("resources/read", INVALID_PARAMS, "Resource not found.")
        return ReadResourceResult(contents=[content])

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
