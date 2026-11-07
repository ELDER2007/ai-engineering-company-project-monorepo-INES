"""Prefect ``Secret`` blocks: where the production credentials live (design, section 4.5).

The repository holds only the NAMES of the blocks, never a URL. The blocks are OPT-IN (``PIPELINE_SECRET_BLOCKS=1``): without
it the pipeline works exactly as before, from the environment (``TELEMETRY_DATABASE_URL``, ``REPORTING_DATABASE_URL``,
``DATABASE_URL``) and the API's ``.env``. With it, a database URL comes from its block and NOTHING else: if the block does
not exist the run stops with a clear message, instead of quietly falling back to a more powerful credential.

Create the blocks once, in the Prefect server the deployment uses, from the environment of whoever has the credentials::

    python -m data.pipelines.weekly_office_performance.blocks

It prints the NAMES it saved, never the values.
"""

from __future__ import annotations

import os
import sys

SECRET_BLOCKS_ENV = "PIPELINE_SECRET_BLOCKS"

# environment variable that would hold the URL -> block that holds it instead
TELEMETRY_BLOCK = "telemetry-db-url"  # read-only role over telemetry_events
REPORTING_BLOCK = "reporting-db-url"  # write role only on the reporting schema
ALERT_BLOCK = "pipeline-alert-webhook"  # Slack-compatible incoming webhook
DATABASE_BLOCKS = {"TELEMETRY_DATABASE_URL": TELEMETRY_BLOCK, "REPORTING_DATABASE_URL": REPORTING_BLOCK}


class SecretBlockError(RuntimeError):
    """A block the run needs is missing or cannot be read."""


def enabled() -> bool:
    return os.environ.get(SECRET_BLOCKS_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def load_secret(name: str) -> str | None:
    """The value of the ``Secret`` block ``name``; ``None`` if there is no such block (any other failure propagates)."""
    from prefect.blocks.system import Secret

    try:
        return Secret.load(name).get()
    except ValueError:  # Prefect raises ValueError for an unknown block name
        return None


def database_url(env: str) -> str:
    """The URL for ``env`` (``TELEMETRY_DATABASE_URL`` or ``REPORTING_DATABASE_URL``) from its Secret block."""
    name = DATABASE_BLOCKS[env]
    value = load_secret(name)
    if not value or not value.strip():
        raise SecretBlockError(
            f"{SECRET_BLOCKS_ENV} is on but the Secret block '{name}' does not exist or is empty. "
            "Create it with: python -m data.pipelines.weekly_office_performance.blocks"
        )
    return value.strip()


def save_from_environment(environ: dict[str, str] | None = None) -> list[str]:
    """Save the blocks from the environment (the variable of each one, else ``DATABASE_URL``). Returns the NAMES saved."""
    from prefect.blocks.system import Secret

    environ = dict(os.environ if environ is None else environ)
    fallback = environ.get("DATABASE_URL", "").strip()
    wanted = {block: environ.get(var, "").strip() or fallback for var, block in DATABASE_BLOCKS.items()}
    wanted[ALERT_BLOCK] = environ.get("PIPELINE_ALERT_WEBHOOK_URL", "").strip()
    saved = []
    for name, value in wanted.items():
        if value:
            Secret(value=value).save(name, overwrite=True)
            saved.append(name)
    return saved


def main() -> int:
    saved = save_from_environment()
    if not saved:
        print("nothing to save: set DATABASE_URL (or TELEMETRY_DATABASE_URL / REPORTING_DATABASE_URL) first", file=sys.stderr)
        return 1
    print("Secret blocks saved: " + ", ".join(saved))
    print(f"Turn them on with {SECRET_BLOCKS_ENV}=1 in the environment of the deployment.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
