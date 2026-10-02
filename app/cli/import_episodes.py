"""Import episode metadata from a CSV file (repeatable, reported)."""

import argparse
import json
import sys
from pathlib import Path

from app.db import SessionLocal
from app.services.import_episodes import ImportReport, import_csv


def run(path: Path) -> ImportReport:
    with SessionLocal.begin() as session:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return import_csv(session, handle)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    args = parser.parse_args(argv)
    report = run(args.csv_path)
    print(
        json.dumps(
            {
                "inserted": report.inserted,
                "already_exists": report.already_exists,
                "skipped_invalid": report.skipped_invalid,
                "skipped_conflict": report.skipped_conflict,
                "errors": [
                    {"row": e.row, "episode_id": e.episode_id, "reason": e.reason}
                    for e in report.errors
                ],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
