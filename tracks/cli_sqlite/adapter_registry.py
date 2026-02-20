from __future__ import annotations

from tracks.cli_sqlite.domain_adapter import DomainAdapter


def resolve_adapter(
    domain: str,
    *,
    cryptic_errors: bool = False,
    semi_helpful_errors: bool = False,
) -> DomainAdapter:
    """Resolve a domain name to its adapter instance."""
    if domain == "sqlite":
        from tracks.cli_sqlite.domains.sqlite_adapter import SqliteAdapter

        return SqliteAdapter()
    if domain == "gridtool":
        from tracks.cli_sqlite.domains.gridtool_adapter import GridtoolAdapter

        return GridtoolAdapter(
            cryptic_errors=cryptic_errors,
            semi_helpful_errors=semi_helpful_errors,
            mixed_errors=False,
        )
    if domain == "fluxtool":
        from tracks.cli_sqlite.domains.fluxtool_adapter import FluxtoolAdapter

        return FluxtoolAdapter(
            cryptic_errors=cryptic_errors,
            semi_helpful_errors=semi_helpful_errors,
            mixed_errors=False,
        )
    if domain == "artic":
        from tracks.cli_sqlite.domains.artic_adapter import ArticAdapter

        return ArticAdapter()
    if domain == "shell":
        from tracks.cli_sqlite.domains.shell_adapter import ShellAdapter

        return ShellAdapter()
    raise ValueError(f"Unknown domain: {domain!r}. Available: sqlite, gridtool, fluxtool, artic, shell")


def resolve_adapter_with_mode(
    domain: str,
    *,
    cryptic_errors: bool,
    semi_helpful_errors: bool,
    mixed_errors: bool,
) -> DomainAdapter:
    """Resolve adapter with optional mixed per-command error policy."""
    if domain == "gridtool":
        from tracks.cli_sqlite.domains.gridtool_adapter import GridtoolAdapter

        return GridtoolAdapter(
            cryptic_errors=cryptic_errors,
            semi_helpful_errors=semi_helpful_errors,
            mixed_errors=mixed_errors,
        )
    if domain == "fluxtool":
        from tracks.cli_sqlite.domains.fluxtool_adapter import FluxtoolAdapter

        return FluxtoolAdapter(
            cryptic_errors=cryptic_errors,
            semi_helpful_errors=semi_helpful_errors,
            mixed_errors=mixed_errors,
        )
    return resolve_adapter(
        domain,
        cryptic_errors=cryptic_errors,
        semi_helpful_errors=semi_helpful_errors,
    )

