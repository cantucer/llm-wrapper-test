from __future__ import annotations

from bench.db import get_db_path, init_db


def main() -> None:
    init_db()
    print(f"Initialized database at {get_db_path()}")


if __name__ == "__main__":
    main()
