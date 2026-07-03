from __future__ import annotations

import argparse

from bench.export import export_latest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export the latest benchmark run.")
    parser.add_argument("--output", default="results/")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = export_latest(args.output)
    for name, path in paths.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
