"""BookStack CLI - Command-line interface for BookStack API.

This module provides a typer-based CLI for interacting with BookStack's
REST API, supporting full CRUD operations on pages, chapters, books,
shelves, attachments, users, and more.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from gishant_scripts.bookstack.client import BookStackClient
from gishant_scripts.common.config import AppConfig
from gishant_scripts.common.errors import APIError, ConfigurationError

# Main app
app = typer.Typer(
    name="bookstack",
    help="BookStack API CLI - Manage documentation programmatically",
    no_args_is_help=True,
)

# Sub-apps for each resource
pages_app = typer.Typer(help="Manage pages")
chapters_app = typer.Typer(help="Manage chapters")
books_app = typer.Typer(help="Manage books")
shelves_app = typer.Typer(help="Manage shelves")
attachments_app = typer.Typer(help="Manage attachments")
users_app = typer.Typer(help="Manage users")

app.add_typer(pages_app, name="pages")
app.add_typer(chapters_app, name="chapters")
app.add_typer(books_app, name="books")
app.add_typer(shelves_app, name="shelves")
app.add_typer(attachments_app, name="attachments")
app.add_typer(users_app, name="users")

console = Console()


def get_client() -> BookStackClient:
    """Get configured BookStack client."""
    try:
        config = AppConfig()
        config.require_valid("bookstack")
    except ConfigurationError as err:
        console.print(f"[red]Configuration Error:[/red] {err}")
        raise typer.Exit(1) from err

    return BookStackClient(
        base_url=config.bookstack.url,
        token_id=config.bookstack.token_id,
        token_secret=config.bookstack.token_secret,
        verify_ssl=config.bookstack.verify_ssl,
    )


def print_item(item: dict[str, Any], title: str | None = None) -> None:
    """Print a single item as a panel."""
    content = []
    for key, value in item.items():
        if isinstance(value, dict):
            content.append(f"[bold]{key}:[/bold] {json.dumps(value, indent=2)}")
        elif isinstance(value, list):
            if len(value) > 3:
                content.append(f"[bold]{key}:[/bold] [{len(value)} items]")
            else:
                content.append(f"[bold]{key}:[/bold] {value}")
        else:
            content.append(f"[bold]{key}:[/bold] {value}")

    panel_title = title or f"Item {item.get('id', 'N/A')}"
    panel = Panel("\n".join(content), title=f"[cyan]{panel_title}[/cyan]", border_style="cyan")
    console.print(panel)


def print_list(items: list[dict[str, Any]], columns: list[str], title: str) -> None:
    """Print a list of items as a table."""
    table = Table(title=title, show_header=True, header_style="bold cyan")

    for col in columns:
        table.add_column(col.replace("_", " ").title(), style="white")

    for item in items:
        row = []
        for col in columns:
            value = item.get(col, "N/A")
            if isinstance(value, dict):
                value = value.get("name", str(value))
            row.append(str(value)[:50])  # Truncate long values
        table.add_row(*row)

    console.print(table)
    console.print(f"\n[dim]Total: {len(items)} items[/dim]")


def print_dry_run(action: str, data: dict[str, Any]) -> None:
    """Print dry-run preview."""
    console.print()
    console.print(Panel.fit("[bold cyan]DRY RUN MODE[/bold cyan]", border_style="cyan"))
    console.print()
    console.print(f"[green]Action:[/green] {action}")
    console.print(f"[green]Data:[/green]")
    console.print(json.dumps(data, indent=2))
    console.print()
    console.print("[yellow]To execute, run again with --no-dry-run[/yellow]")


def print_success(action: str, result: dict[str, Any]) -> None:
    """Print success message."""
    console.print()
    console.print(Panel.fit(f"[bold green]{action} Successful[/bold green]", border_style="green"))
    if result:
        item_id = result.get("id", result.get("idReadable", ""))
        if item_id:
            console.print(f"ID: {item_id}")
        name = result.get("name", result.get("summary", ""))
        if name:
            console.print(f"Name: {name}")


# =============================================================================
# System Commands
# =============================================================================


@app.command()
def info():
    """Show BookStack system information."""
    client = get_client()
    try:
        data = client.system.info()
        print_item(data, "BookStack System Info")
    except APIError as err:
        console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1) from err


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    max_results: int = typer.Option(50, "--max", "-m", help="Maximum results"),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Search across all content."""
    client = get_client()
    try:
        results = client.search.search_all(query, max_results=max_results)

        if output_json:
            console.print(json.dumps(results, indent=2))
        else:
            print_list(results, ["id", "type", "name", "url"], f"Search Results for '{query}'")
    except APIError as err:
        console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1) from err


# =============================================================================
# Pages Commands
# =============================================================================


@pages_app.command("list")
def pages_list(
    book_id: int | None = typer.Option(None, "--book", "-b", help="Filter by book ID"),
    chapter_id: int | None = typer.Option(None, "--chapter", "-c", help="Filter by chapter ID"),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """List pages."""
    client = get_client()
    try:
        if chapter_id:
            pages = client.pages.list_by_chapter(chapter_id)
        elif book_id:
            pages = client.pages.list_by_book(book_id)
        else:
            pages = client.pages.list_all()

        if output_json:
            console.print(json.dumps(pages, indent=2))
        else:
            print_list(pages, ["id", "name", "book_id", "chapter_id", "updated_at"], "Pages")
    except APIError as err:
        console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1) from err


@pages_app.command("read")
def pages_read(
    page_id: int = typer.Argument(..., help="Page ID"),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Read a page's details and content."""
    client = get_client()
    try:
        page = client.pages.read(page_id)

        if output_json:
            console.print(json.dumps(page, indent=2))
        else:
            print_item(page, f"Page: {page.get('name', page_id)}")
    except APIError as err:
        console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1) from err


@pages_app.command("create")
def pages_create(
    name: str = typer.Argument(..., help="Page name"),
    book_id: int | None = typer.Option(None, "--book", "-b", help="Book ID"),
    chapter_id: int | None = typer.Option(None, "--chapter", "-c", help="Chapter ID"),
    html: str | None = typer.Option(None, "--html", help="HTML content"),
    markdown: str | None = typer.Option(None, "--markdown", "-md", help="Markdown content"),
    html_file: Path | None = typer.Option(None, "--html-file", help="HTML content from file"),
    markdown_file: Path | None = typer.Option(None, "--markdown-file", "-mdf", help="Markdown content from file"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Preview without creating"),
):
    """Create a new page."""
    if not book_id and not chapter_id:
        console.print("[red]Error:[/red] Either --book or --chapter is required")
        raise typer.Exit(1)

    # Load content from file if specified
    content_html = html
    content_md = markdown
    if html_file:
        content_html = html_file.read_text()
    if markdown_file:
        content_md = markdown_file.read_text()

    data = {
        "name": name,
        "book_id": book_id,
        "chapter_id": chapter_id,
        "html": content_html,
        "markdown": content_md,
    }
    data = {k: v for k, v in data.items() if v is not None}

    if dry_run:
        print_dry_run("Create Page", data)
        return

    client = get_client()
    try:
        result = client.pages.create(
            name=name,
            book_id=book_id,
            chapter_id=chapter_id,
            html=content_html,
            markdown=content_md,
        )
        print_success("Page Created", result)
    except APIError as err:
        console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1) from err


@pages_app.command("update")
def pages_update(
    page_id: int = typer.Argument(..., help="Page ID"),
    name: str | None = typer.Option(None, "--name", "-n", help="New name"),
    html: str | None = typer.Option(None, "--html", help="HTML content"),
    markdown: str | None = typer.Option(None, "--markdown", "-md", help="Markdown content"),
    book_id: int | None = typer.Option(None, "--book", "-b", help="Move to book"),
    chapter_id: int | None = typer.Option(None, "--chapter", "-c", help="Move to chapter"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Preview without updating"),
):
    """Update a page."""
    data = {
        "page_id": page_id,
        "name": name,
        "html": html,
        "markdown": markdown,
        "book_id": book_id,
        "chapter_id": chapter_id,
    }
    data = {k: v for k, v in data.items() if v is not None}

    if dry_run:
        print_dry_run("Update Page", data)
        return

    client = get_client()
    try:
        result = client.pages.update(
            page_id=page_id,
            name=name,
            html=html,
            markdown=markdown,
            book_id=book_id,
            chapter_id=chapter_id,
        )
        print_success("Page Updated", result)
    except APIError as err:
        console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1) from err


@pages_app.command("delete")
def pages_delete(
    page_id: int = typer.Argument(..., help="Page ID"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Preview without deleting"),
):
    """Delete a page."""
    if dry_run:
        print_dry_run("Delete Page", {"page_id": page_id})
        return

    client = get_client()
    try:
        client.pages.delete(page_id)
        print_success("Page Deleted", {"id": page_id})
    except APIError as err:
        console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1) from err


@pages_app.command("export")
def pages_export(
    page_id: int = typer.Argument(..., help="Page ID"),
    format: str = typer.Option("html", "--format", "-f", help="Export format: html, pdf, plaintext, markdown, zip"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output file path"),
):
    """Export a page."""
    client = get_client()
    try:
        if output:
            result = client.pages.export(page_id, format, output)
            console.print(f"[green]Exported to:[/green] {result}")
        else:
            result = client.pages.export(page_id, format)
            if isinstance(result, bytes):
                # For binary formats, save to default path
                default_name = f"page_{page_id}.{format}"
                Path(default_name).write_bytes(result)
                console.print(f"[green]Exported to:[/green] {default_name}")
            else:
                console.print(result.decode() if isinstance(result, bytes) else str(result))
    except APIError as err:
        console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1) from err


# =============================================================================
# Chapters Commands
# =============================================================================


@chapters_app.command("list")
def chapters_list(
    book_id: int | None = typer.Option(None, "--book", "-b", help="Filter by book ID"),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """List chapters."""
    client = get_client()
    try:
        if book_id:
            chapters = client.chapters.list_by_book(book_id)
        else:
            chapters = client.chapters.list_all()

        if output_json:
            console.print(json.dumps(chapters, indent=2))
        else:
            print_list(chapters, ["id", "name", "book_id", "updated_at"], "Chapters")
    except APIError as err:
        console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1) from err


@chapters_app.command("read")
def chapters_read(
    chapter_id: int = typer.Argument(..., help="Chapter ID"),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Read a chapter's details."""
    client = get_client()
    try:
        chapter = client.chapters.read(chapter_id)

        if output_json:
            console.print(json.dumps(chapter, indent=2))
        else:
            print_item(chapter, f"Chapter: {chapter.get('name', chapter_id)}")
    except APIError as err:
        console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1) from err


@chapters_app.command("create")
def chapters_create(
    book_id: int = typer.Argument(..., help="Book ID"),
    name: str = typer.Argument(..., help="Chapter name"),
    description: str | None = typer.Option(None, "--description", "-d", help="Description"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Preview without creating"),
):
    """Create a new chapter."""
    data = {"book_id": book_id, "name": name, "description": description}
    data = {k: v for k, v in data.items() if v is not None}

    if dry_run:
        print_dry_run("Create Chapter", data)
        return

    client = get_client()
    try:
        result = client.chapters.create(book_id=book_id, name=name, description=description)
        print_success("Chapter Created", result)
    except APIError as err:
        console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1) from err


@chapters_app.command("update")
def chapters_update(
    chapter_id: int = typer.Argument(..., help="Chapter ID"),
    name: str | None = typer.Option(None, "--name", "-n", help="New name"),
    description: str | None = typer.Option(None, "--description", "-d", help="Description"),
    book_id: int | None = typer.Option(None, "--book", "-b", help="Move to book"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Preview without updating"),
):
    """Update a chapter."""
    data = {"chapter_id": chapter_id, "name": name, "description": description, "book_id": book_id}
    data = {k: v for k, v in data.items() if v is not None}

    if dry_run:
        print_dry_run("Update Chapter", data)
        return

    client = get_client()
    try:
        result = client.chapters.update(chapter_id=chapter_id, name=name, description=description, book_id=book_id)
        print_success("Chapter Updated", result)
    except APIError as err:
        console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1) from err


@chapters_app.command("delete")
def chapters_delete(
    chapter_id: int = typer.Argument(..., help="Chapter ID"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Preview without deleting"),
):
    """Delete a chapter."""
    if dry_run:
        print_dry_run("Delete Chapter", {"chapter_id": chapter_id})
        return

    client = get_client()
    try:
        client.chapters.delete(chapter_id)
        print_success("Chapter Deleted", {"id": chapter_id})
    except APIError as err:
        console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1) from err


@chapters_app.command("export")
def chapters_export(
    chapter_id: int = typer.Argument(..., help="Chapter ID"),
    format: str = typer.Option("html", "--format", "-f", help="Export format: html, pdf, plaintext, markdown, zip"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output file path"),
):
    """Export a chapter."""
    client = get_client()
    try:
        if output:
            result = client.chapters.export(chapter_id, format, output)
            console.print(f"[green]Exported to:[/green] {result}")
        else:
            default_name = f"chapter_{chapter_id}.{format}"
            result = client.chapters.export(chapter_id, format, Path(default_name))
            console.print(f"[green]Exported to:[/green] {result}")
    except APIError as err:
        console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1) from err


# =============================================================================
# Books Commands
# =============================================================================


@books_app.command("list")
def books_list(
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """List all books."""
    client = get_client()
    try:
        books = client.books.list_all()

        if output_json:
            console.print(json.dumps(books, indent=2))
        else:
            print_list(books, ["id", "name", "description", "updated_at"], "Books")
    except APIError as err:
        console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1) from err


@books_app.command("read")
def books_read(
    book_id: int = typer.Argument(..., help="Book ID"),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Read a book's details and contents."""
    client = get_client()
    try:
        book = client.books.read(book_id)

        if output_json:
            console.print(json.dumps(book, indent=2))
        else:
            print_item(book, f"Book: {book.get('name', book_id)}")
    except APIError as err:
        console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1) from err


@books_app.command("create")
def books_create(
    name: str = typer.Argument(..., help="Book name"),
    description: str | None = typer.Option(None, "--description", "-d", help="Description"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Preview without creating"),
):
    """Create a new book."""
    data = {"name": name, "description": description}
    data = {k: v for k, v in data.items() if v is not None}

    if dry_run:
        print_dry_run("Create Book", data)
        return

    client = get_client()
    try:
        result = client.books.create(name=name, description=description)
        print_success("Book Created", result)
    except APIError as err:
        console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1) from err


@books_app.command("update")
def books_update(
    book_id: int = typer.Argument(..., help="Book ID"),
    name: str | None = typer.Option(None, "--name", "-n", help="New name"),
    description: str | None = typer.Option(None, "--description", "-d", help="Description"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Preview without updating"),
):
    """Update a book."""
    data = {"book_id": book_id, "name": name, "description": description}
    data = {k: v for k, v in data.items() if v is not None}

    if dry_run:
        print_dry_run("Update Book", data)
        return

    client = get_client()
    try:
        result = client.books.update(book_id=book_id, name=name, description=description)
        print_success("Book Updated", result)
    except APIError as err:
        console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1) from err


@books_app.command("delete")
def books_delete(
    book_id: int = typer.Argument(..., help="Book ID"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Preview without deleting"),
):
    """Delete a book."""
    if dry_run:
        print_dry_run("Delete Book", {"book_id": book_id})
        return

    client = get_client()
    try:
        client.books.delete(book_id)
        print_success("Book Deleted", {"id": book_id})
    except APIError as err:
        console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1) from err


@books_app.command("export")
def books_export(
    book_id: int = typer.Argument(..., help="Book ID"),
    format: str = typer.Option("html", "--format", "-f", help="Export format: html, pdf, plaintext, markdown, zip"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output file path"),
):
    """Export a book."""
    client = get_client()
    try:
        if output:
            result = client.books.export(book_id, format, output)
            console.print(f"[green]Exported to:[/green] {result}")
        else:
            default_name = f"book_{book_id}.{format}"
            result = client.books.export(book_id, format, Path(default_name))
            console.print(f"[green]Exported to:[/green] {result}")
    except APIError as err:
        console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1) from err


# =============================================================================
# Shelves Commands
# =============================================================================


@shelves_app.command("list")
def shelves_list(
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """List all shelves."""
    client = get_client()
    try:
        shelves = client.shelves.list_all()

        if output_json:
            console.print(json.dumps(shelves, indent=2))
        else:
            print_list(shelves, ["id", "name", "description", "updated_at"], "Shelves")
    except APIError as err:
        console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1) from err


@shelves_app.command("read")
def shelves_read(
    shelf_id: int = typer.Argument(..., help="Shelf ID"),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Read a shelf's details and books."""
    client = get_client()
    try:
        shelf = client.shelves.read(shelf_id)

        if output_json:
            console.print(json.dumps(shelf, indent=2))
        else:
            print_item(shelf, f"Shelf: {shelf.get('name', shelf_id)}")
    except APIError as err:
        console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1) from err


@shelves_app.command("create")
def shelves_create(
    name: str = typer.Argument(..., help="Shelf name"),
    description: str | None = typer.Option(None, "--description", "-d", help="Description"),
    books: list[int] | None = typer.Option(None, "--book", "-b", help="Book IDs to add (can repeat)"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Preview without creating"),
):
    """Create a new shelf."""
    data = {"name": name, "description": description, "books": books}
    data = {k: v for k, v in data.items() if v is not None}

    if dry_run:
        print_dry_run("Create Shelf", data)
        return

    client = get_client()
    try:
        result = client.shelves.create(name=name, description=description, books=books)
        print_success("Shelf Created", result)
    except APIError as err:
        console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1) from err


@shelves_app.command("update")
def shelves_update(
    shelf_id: int = typer.Argument(..., help="Shelf ID"),
    name: str | None = typer.Option(None, "--name", "-n", help="New name"),
    description: str | None = typer.Option(None, "--description", "-d", help="Description"),
    books: list[int] | None = typer.Option(None, "--book", "-b", help="Book IDs (replaces existing)"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Preview without updating"),
):
    """Update a shelf."""
    data = {"shelf_id": shelf_id, "name": name, "description": description, "books": books}
    data = {k: v for k, v in data.items() if v is not None}

    if dry_run:
        print_dry_run("Update Shelf", data)
        return

    client = get_client()
    try:
        result = client.shelves.update(shelf_id=shelf_id, name=name, description=description, books=books)
        print_success("Shelf Updated", result)
    except APIError as err:
        console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1) from err


@shelves_app.command("delete")
def shelves_delete(
    shelf_id: int = typer.Argument(..., help="Shelf ID"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Preview without deleting"),
):
    """Delete a shelf."""
    if dry_run:
        print_dry_run("Delete Shelf", {"shelf_id": shelf_id})
        return

    client = get_client()
    try:
        client.shelves.delete(shelf_id)
        print_success("Shelf Deleted", {"id": shelf_id})
    except APIError as err:
        console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1) from err


# =============================================================================
# Attachments Commands
# =============================================================================


@attachments_app.command("list")
def attachments_list(
    page_id: int | None = typer.Option(None, "--page", "-p", help="Filter by page ID"),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """List attachments."""
    client = get_client()
    try:
        if page_id:
            attachments = client.attachments.list_by_page(page_id)
        else:
            attachments = client.attachments.list_all()

        if output_json:
            console.print(json.dumps(attachments, indent=2))
        else:
            print_list(attachments, ["id", "name", "extension", "uploaded_to", "external"], "Attachments")
    except APIError as err:
        console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1) from err


@attachments_app.command("read")
def attachments_read(
    attachment_id: int = typer.Argument(..., help="Attachment ID"),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Read an attachment's details."""
    client = get_client()
    try:
        attachment = client.attachments.read(attachment_id)

        if output_json:
            console.print(json.dumps(attachment, indent=2))
        else:
            print_item(attachment, f"Attachment: {attachment.get('name', attachment_id)}")
    except APIError as err:
        console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1) from err


@attachments_app.command("create-link")
def attachments_create_link(
    page_id: int = typer.Argument(..., help="Page ID to attach to"),
    name: str = typer.Argument(..., help="Attachment name"),
    link: str = typer.Argument(..., help="External URL"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Preview without creating"),
):
    """Create a link attachment."""
    data = {"page_id": page_id, "name": name, "link": link}

    if dry_run:
        print_dry_run("Create Link Attachment", data)
        return

    client = get_client()
    try:
        result = client.attachments.create_link(name=name, uploaded_to=page_id, link=link)
        print_success("Link Attachment Created", result)
    except APIError as err:
        console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1) from err


@attachments_app.command("create-file")
def attachments_create_file(
    page_id: int = typer.Argument(..., help="Page ID to attach to"),
    name: str = typer.Argument(..., help="Attachment name"),
    file: Path = typer.Argument(..., help="File to upload"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Preview without creating"),
):
    """Create a file attachment."""
    if not file.exists():
        console.print(f"[red]Error:[/red] File not found: {file}")
        raise typer.Exit(1)

    data = {"page_id": page_id, "name": name, "file": str(file)}

    if dry_run:
        print_dry_run("Create File Attachment", data)
        return

    client = get_client()
    try:
        result = client.attachments.create_file(name=name, uploaded_to=page_id, file_path=file)
        print_success("File Attachment Created", result)
    except APIError as err:
        console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1) from err


@attachments_app.command("delete")
def attachments_delete(
    attachment_id: int = typer.Argument(..., help="Attachment ID"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Preview without deleting"),
):
    """Delete an attachment."""
    if dry_run:
        print_dry_run("Delete Attachment", {"attachment_id": attachment_id})
        return

    client = get_client()
    try:
        client.attachments.delete(attachment_id)
        print_success("Attachment Deleted", {"id": attachment_id})
    except APIError as err:
        console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1) from err


# =============================================================================
# Users Commands
# =============================================================================


@users_app.command("list")
def users_list(
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """List all users."""
    client = get_client()
    try:
        users = client.users.list_all()

        if output_json:
            console.print(json.dumps(users, indent=2))
        else:
            print_list(users, ["id", "name", "email", "last_activity_at"], "Users")
    except APIError as err:
        console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1) from err


@users_app.command("read")
def users_read(
    user_id: int = typer.Argument(..., help="User ID"),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Read a user's details."""
    client = get_client()
    try:
        user = client.users.read(user_id)

        if output_json:
            console.print(json.dumps(user, indent=2))
        else:
            print_item(user, f"User: {user.get('name', user_id)}")
    except APIError as err:
        console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1) from err


@users_app.command("create")
def users_create(
    name: str = typer.Argument(..., help="User name"),
    email: str = typer.Argument(..., help="User email"),
    roles: list[int] | None = typer.Option(None, "--role", "-r", help="Role IDs (can repeat)"),
    password: str | None = typer.Option(None, "--password", "-p", help="User password"),
    send_invite: bool = typer.Option(False, "--send-invite", help="Send invite email"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Preview without creating"),
):
    """Create a new user."""
    data = {"name": name, "email": email, "roles": roles, "send_invite": send_invite}
    if password:
        data["password"] = "********"  # Don't show password in dry run
    data = {k: v for k, v in data.items() if v is not None}

    if dry_run:
        print_dry_run("Create User", data)
        return

    client = get_client()
    try:
        result = client.users.create(
            name=name,
            email=email,
            roles=roles,
            password=password,
            send_invite=send_invite,
        )
        print_success("User Created", result)
    except APIError as err:
        console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1) from err


@users_app.command("delete")
def users_delete(
    user_id: int = typer.Argument(..., help="User ID"),
    migrate_to: int | None = typer.Option(None, "--migrate-to", "-m", help="User ID to transfer ownership to"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Preview without deleting"),
):
    """Delete a user."""
    data = {"user_id": user_id, "migrate_ownership_id": migrate_to}
    data = {k: v for k, v in data.items() if v is not None}

    if dry_run:
        print_dry_run("Delete User", data)
        return

    client = get_client()
    try:
        client.users.delete(user_id, migrate_ownership_id=migrate_to)
        print_success("User Deleted", {"id": user_id})
    except APIError as err:
        console.print(f"[red]Error:[/red] {err}")
        raise typer.Exit(1) from err


def main():
    """Entry point for CLI."""
    app()


if __name__ == "__main__":
    app()
