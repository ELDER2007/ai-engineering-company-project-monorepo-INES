"""Create an internal user from the command line (first user, recovery).

    uv run create-user --email ines@example.com [--role admin]   # prompts for the password

Every failure ends with a message on stderr and exit code 1 (``raise SystemExit("message")``).
"""

from __future__ import annotations

import argparse
import getpass

from pydantic import ValidationError

from core.errors import DatabaseUnavailableError
from users import service
from users.schemas import Role, UserCreate


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an internal API user.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--role", choices=[r.value for r in Role], default=Role.user.value)
    args = parser.parse_args()

    try:
        password = getpass.getpass("Password: ")
        repeated = getpass.getpass("Repeat password: ")
    except (EOFError, KeyboardInterrupt):  # no terminal to ask on, or Ctrl+C
        raise SystemExit("Cancelled: no password was entered.") from None
    if password != repeated:
        raise SystemExit("Passwords do not match.")
    try:
        user = service.create_user(UserCreate(email=args.email, password=password), role=Role(args.role))
    except ValidationError as exc:
        # The text of the error quotes the rejected value (the password): keep only which rule failed.
        problems = "; ".join(e["msg"] for e in exc.errors(include_input=False))
        raise SystemExit(f"Invalid user: {problems}") from None
    except service.EmailTakenError as exc:
        raise SystemExit(str(exc)) from exc
    except (DatabaseUnavailableError, OSError) as exc:
        raise SystemExit(f"The users database cannot be used ({exc}). Check the file can be read and written and is valid JSON.") from None
    print(f"Created {user.role} {user.email} ({user.id}).")


if __name__ == "__main__":
    main()
