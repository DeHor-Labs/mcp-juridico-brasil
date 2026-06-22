"""CLI do MCP Juridico Brasil."""

from __future__ import annotations

import typer

app = typer.Typer(
    name="mcp-juridico",
    help="MCP Juridico Brasil - acompanhamento de processos via DataJud CNJ.",
    add_completion=False,
)


@app.command()
def serve() -> None:
    """Inicia o servidor MCP em modo stdio."""
    from mcp_juridico_brasil.server import main

    main()


@app.command()
def version() -> None:
    """Exibe a versao instalada."""
    from mcp_juridico_brasil import __version__

    typer.echo(f"mcp-juridico-brasil {__version__}")


@app.command()
def tribunais() -> None:
    """Lista os tribunais suportados."""
    from mcp_juridico_brasil.datajud.tribunais import listar_tribunais

    for t in listar_tribunais():
        typer.echo(t)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
