from __future__ import annotations

import typer

app = typer.Typer(add_completion=False, no_args_is_help=True, help="RosettaLog CLI")


@app.command()
def health() -> None:
    """Return health information for the service."""
    typer.echo("OK")


@app.command()
def version() -> None:
    """Display the package version."""
    typer.echo("0.1.0")


def main() -> None:
    """CLI entrypoint."""
    app()


if __name__ == "__main__":
    main()
