from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

import typer
from rich.console import Console
from rich.panel import Panel

from devmemory import __version__
from devmemory.diagnostics import DiagnosticResult, analyze_error_output
from devmemory.integration import (
    BackendDiagnosisResponse,
    BackendEnvironmentInfo,
    BackendErrorContext,
    DevMemoryClient,
    IncidentErrorInfo,
    IncidentPayload,
    IncidentSourceSnippet,
    IncidentStackFrame,
    IngestionResult,
    redact_secrets,
)
from devmemory.runner import CommandRunner, ExecutionResult

app = typer.Typer(
    name="devmemory",
    help="AI-powered developer troubleshooting and persistent developer-memory platform.",
    add_completion=False,
    no_args_is_help=True,
)

console = Console()
err_console = Console(stderr=True)

CONFIG_DIR_NAME = ".devmemory"
CONFIG_FILE_NAME = "config.json"
CONFIG_VERSION = 1
DEFAULT_BACKEND_URL = "http://localhost:8000"


def version_callback(value: bool) -> None:
    """Print the version and exit."""
    if value:
        console.print(f"DevMemory version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        help="Show the version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """DevMemory CLI entry point."""
    return


def _find_project_root(start_dir: Optional[Path] = None) -> tuple[Optional[Path], Optional[dict[str, Any]]]:
    """
    Traverse upwards from start_dir to find .devmemory/config.json.
    Returns (root_path, config_dict).
    """
    current = (start_dir or Path.cwd()).resolve()
    for directory in [current, *current.parents]:
        cfg_file = directory / CONFIG_DIR_NAME / CONFIG_FILE_NAME
        if cfg_file.is_file():
            try:
                data = json.loads(cfg_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return directory, data
            except Exception:
                pass
    return None, None


def _load_existing_config(config_path: Path) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """
    Attempt to read and parse an existing configuration file.
    Returns (config_dict, error_message).
    """
    try:
        raw_text = config_path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
        if not isinstance(data, dict):
            return None, "Configuration content is not a valid JSON object."
        return data, None
    except json.JSONDecodeError as exc:
        return None, f"Configuration file contains invalid JSON: {exc}"
    except OSError as exc:
        return None, f"Unable to read configuration file: {exc}"


def _write_config_atomic(config_path: Path, config_data: dict[str, Any]) -> None:
    """
    Write config atomically to avoid corruption on crash or interruption.
    Writes to a temporary file in the same directory, then replaces.
    """
    parent_dir = config_path.parent
    parent_dir.mkdir(parents=True, exist_ok=True)
    temp_file = parent_dir / f".tmp_{uuid.uuid4().hex}_{config_path.name}"
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        temp_file.replace(config_path)
    finally:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except OSError:
                pass


@app.command("init")
def init(
    project_name: Optional[str] = typer.Option(
        None,
        "--name",
        "-n",
        help="Optional name for the project. Defaults to current directory name.",
    ),
    backend_url: str = typer.Option(
        DEFAULT_BACKEND_URL,
        "--backend-url",
        "-b",
        help="DevMemory backend API URL.",
    ),
) -> None:
    """Initialize DevMemory in the current working directory and register project on backend."""
    cwd = Path.cwd().resolve()
    config_dir = cwd / CONFIG_DIR_NAME
    config_path = config_dir / CONFIG_FILE_NAME

    # Check if configuration already exists
    if config_path.exists():
        existing_data, err = _load_existing_config(config_path)
        if err:
            err_console.print(f"[bold red]Error:[/] Invalid existing configuration found at {config_path}:")
            err_console.print(f"  {err}")
            err_console.print("[yellow]Hint:[/] Correct or remove the invalid file to reinitialize.")
            raise typer.Exit(code=1)

        # Existing valid config found
        proj_id = existing_data.get("project_id", "unknown")
        proj_name = existing_data.get("project_name", cwd.name)
        target_backend = existing_data.get("backend_url", backend_url)

        # Attempt to ensure project is registered on the backend
        client = DevMemoryClient(base_url=target_backend)
        reg_result = client.register_project(project_id=proj_id, name=proj_name)
        backend_note = " (verified on backend)" if reg_result.success else " (backend offline / unverified)"

        console.print(
            f"[bold yellow]Project already initialized![/]\n"
            f"  [cyan]Project Name:[/] {proj_name}\n"
            f"  [cyan]Project ID:[/]   {proj_id}{backend_note}\n"
            f"  [cyan]Root:[/]         {cwd}\n"
            f"  [cyan]Config:[/]       {config_path}"
        )
        return

    # Check if .devmemory is a file instead of a directory
    if config_dir.exists() and not config_dir.is_dir():
        err_console.print(
            f"[bold red]Error:[/] Target path '{config_dir}' exists and is not a directory."
        )
        raise typer.Exit(code=1)

    resolved_name = project_name.strip() if project_name and project_name.strip() else cwd.name
    new_project_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    config_data: dict[str, Any] = {
        "config_version": CONFIG_VERSION,
        "project_id": new_project_id,
        "project_name": resolved_name,
        "project_root": str(cwd),
        "backend_url": backend_url.strip(),
        "created_at": now_iso,
    }

    try:
        _write_config_atomic(config_path, config_data)
    except OSError as exc:
        err_console.print(f"[bold red]Error:[/] Failed to write configuration at {config_path}: {exc}")
        raise typer.Exit(code=1)

    # Register project on backend
    client = DevMemoryClient(base_url=backend_url)
    reg_result = client.register_project(project_id=new_project_id, name=resolved_name)
    reg_status_str = (
        "[green]Registered on backend[/]"
        if reg_result.success
        else f"[yellow]Local config created (backend offline - {reg_result.error_message})[/]"
    )

    console.print(
        f"[bold green]Initialized DevMemory project successfully![/]\n"
        f"  [cyan]Project Name:[/] {resolved_name}\n"
        f"  [cyan]Project ID:[/]   {new_project_id}\n"
        f"  [cyan]Project Root:[/] {cwd}\n"
        f"  [cyan]Backend URL:[/]  {backend_url}\n"
        f"  [cyan]Status:[/]       {reg_status_str}\n"
        f"  [cyan]Config File:[/]  {config_path}"
    )


def _convert_diagnostic_to_backend_context(diag: Optional[DiagnosticResult]) -> Optional[BackendErrorContext]:
    """Map local DiagnosticResult to backend's ErrorContext schema."""
    if not diag or not diag.has_diagnostic:
        return None

    file_path = None
    line = None
    col = None
    snippet_str = None

    if diag.primary_frame:
        pf = diag.primary_frame
        file_path = pf.file_path
        line = pf.line_number
        col = pf.column_number
        if pf.snippet and pf.snippet.lines:
            snippet_str = "\n".join(pf.snippet.lines)

    return BackendErrorContext(
        error_type=diag.error_type,
        message=diag.message,
        file_path=file_path,
        line=line,
        column=col,
        snippet=snippet_str,
    )


def _render_diagnostic_report(diag: DiagnosticResult, cwd: Path) -> None:
    """Render a structured terminal diagnostic report with highlighted source snippet."""
    if not diag.has_diagnostic:
        console.print("[dim]No supported stack trace detected.[/]")
        return

    console.print(f"\n[bold red]--- Source-Aware Error Analysis ({diag.language.capitalize()}) ---[/]")
    console.print(f"  [bold cyan]Error Type:[/] [red]{diag.error_type}[/]")
    if diag.message:
        console.print(f"  [bold cyan]Message:[/]    {diag.message}")

    if diag.primary_frame:
        pf = diag.primary_frame
        loc_str = pf.file_path or "unknown file"
        if pf.line_number is not None:
            loc_str += f":{pf.line_number}"
        if pf.column_number is not None:
            loc_str += f":{pf.column_number}"
        if pf.function_name:
            loc_str += f" in `{pf.function_name}`"

        console.print(f"  [bold cyan]Location:[/]   {loc_str}")

        if pf.snippet and pf.snippet.lines:
            snip = pf.snippet
            console.print(f"\n  [bold yellow]Code Context ({Path(snip.file_path).name}:{snip.target_line}):[/]")
            for idx, line in enumerate(snip.lines, start=snip.start_line):
                marker = ">" if idx == snip.target_line else " "
                line_style = "[bold red]" if idx == snip.target_line else "[dim]"
                console.print(f"    {marker} {idx:4d} | {line_style}{line}[/]")
            console.print()
        elif pf.snippet and pf.snippet.error:
            console.print(f"  [dim yellow]Source snippet note:[/] {pf.snippet.error}")

    other_frames = [f for f in diag.frames if f != diag.primary_frame]
    if other_frames:
        console.print(f"\n  [bold cyan]Additional Stack Frames ({len(other_frames)}):[/]")
        for f in other_frames[-4:]:
            loc = f.file_path or "?"
            if f.line_number:
                loc += f":{f.line_number}"
            fn = f" ({f.function_name})" if f.function_name else ""
            console.print(f"    - {loc}{fn}")


def _render_backend_report(ingestion: IngestionResult) -> None:
    """Render backend ingestion status, incident identifier, and memory matches."""
    if ingestion.is_offline:
        console.print(f"\n[dim yellow]Backend Status:[/] Offline (Local mode - {ingestion.error_message})")
        return

    if not ingestion.success:
        console.print(f"\n[dim yellow]Backend Status:[/] Ingestion failed ({ingestion.error_message})")
        return

    console.print("\n[bold green]--- DevMemory Platform Diagnosis ---[/]")
    if ingestion.incident_id:
        console.print(f"  [bold cyan]Incident ID:[/] [magenta]{ingestion.incident_id}[/]")

    diag = ingestion.diagnosis
    if not diag:
        console.print("  [dim]Run recorded successfully in DevMemory backend.[/]")
        return

    if diag.probable_cause:
        console.print(f"  [bold cyan]Probable Cause:[/] {diag.probable_cause}")

    if diag.suggested_steps:
        console.print("  [bold cyan]Suggested Fix:[/]")
        for step in diag.suggested_steps:
            console.print(f"    - {step}")

    if diag.similar_incidents:
        console.print(f"\n  [bold cyan]Memory Matches ({len(diag.similar_incidents)}):[/]")
        for inc in diag.similar_incidents:
            scope = "[magenta]Cross-Project[/]" if inc.is_cross_project else "[blue]Project History[/]"
            console.print(f"    - {scope} ({inc.project_name}): {inc.summary}")


@app.command(
    "run",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def run(
    ctx: typer.Context,
    command: List[str] = typer.Argument(
        None,
        help="Command and arguments to execute.",
    ),
) -> None:
    """Execute a developer command, stream live output, diagnose errors, and ingest to DevMemory backend."""
    cmd_args: List[str] = []
    if command:
        cmd_args.extend(command)
    if ctx.args:
        cmd_args.extend(ctx.args)

    if not cmd_args:
        err_console.print("[bold red]Error:[/] No command specified to run.")
        err_console.print("[yellow]Usage:[/] devmemory run -- <command> [args...]")
        raise typer.Exit(code=2)

    cwd = Path.cwd().resolve()
    project_root, proj_config = _find_project_root(cwd)

    project_id = proj_config.get("project_id") if proj_config else None
    project_name = proj_config.get("project_name", cwd.name) if proj_config else cwd.name
    backend_url = proj_config.get("backend_url", DEFAULT_BACKEND_URL) if proj_config else DEFAULT_BACKEND_URL

    # Auto-initialize project identifier if not yet configured
    client = DevMemoryClient(base_url=backend_url)
    if not project_id:
        project_id = str(uuid.uuid4())

    runner = CommandRunner()
    result = runner.run(cmd_args, cwd=cwd)

    # Render execution summary
    cmd_display = " ".join(cmd_args)
    if result.interrupted:
        status_line = "[bold yellow]INTERRUPTED[/]"
    elif result.exit_code == 0:
        status_line = "[bold green]PASSED[/]"
    else:
        status_line = f"[bold red]FAILED[/] (Exit code: {result.exit_code})"

    console.print()
    console.print(f"[bold]DevMemory Run Summary:[/] {status_line}")
    console.print(f"  [cyan]Command:[/]   {cmd_display}")
    console.print(f"  [cyan]Directory:[/] {result.cwd}")
    console.print(f"  [cyan]Duration:[/]  {result.duration_ms:.1f}ms")

    if result.error_message:
        err_console.print(f"  [bold red]Execution error:[/] {result.error_message}")

    # Source-aware error diagnosis on failure
    diagnostic = None
    if result.exit_code != 0 and not result.interrupted:
        diagnostic = analyze_error_output(
            stdout=result.stdout,
            stderr=result.stderr,
            cwd=cwd,
            project_root=project_root or cwd,
        )
        _render_diagnostic_report(diagnostic, cwd=cwd)

    # Ingestion & Backend Integration
    event_id = str(uuid.uuid4())
    sanitized_stdout = redact_secrets(result.stdout)
    sanitized_stderr = redact_secrets(result.stderr)
    error_context = _convert_diagnostic_to_backend_context(diagnostic)

    # Ensure project is registered in backend before run ingestion
    client.register_project(project_id=project_id, name=project_name)

    payload = IncidentPayload(
        event_id=event_id,
        project_id=project_id,
        project_name=project_name,
        command=cmd_display,  # Serialized command string matching RunCreate schema
        cwd=result.cwd,
        started_at=result.started_at,
        ended_at=result.ended_at,
        duration_ms=int(result.duration_ms),  # Integer duration in milliseconds
        exit_code=result.exit_code,
        interrupted=result.interrupted,
        stdout=sanitized_stdout,
        stderr=sanitized_stderr,
        error_context=error_context,
    )

    ingestion_result = client.submit_incident(payload)
    _render_backend_report(ingestion_result)

    if result.exit_code != 0:
        raise typer.Exit(code=result.exit_code)


if __name__ == "__main__":
    app()
