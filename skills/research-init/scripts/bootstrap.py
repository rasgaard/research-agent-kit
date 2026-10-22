#!/usr/bin/env python3
"""Copy the static research-kit scaffold into a new project."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parents[3]
SKILL_ROOT = KIT_ROOT / "skills" / "research-init"


def copy_files(target: Path, pairs: list[tuple[Path, Path]], force: bool,
               dry_run: bool) -> None:
    for source, destination in pairs:
        relative = destination.relative_to(target)
        if not source.is_file():
            raise SystemExit(f"missing kit file: {source}")
        if dry_run:
            if (destination.exists() and
                    (not destination.is_file() or
                     destination.read_bytes() != source.read_bytes())):
                print(f"replace {relative}")
            else:
                print(f"copy {relative}")
            continue
        if destination.exists():
            if destination.is_file() and destination.read_bytes() == source.read_bytes():
                continue
            if not force:
                raise SystemExit(
                    f"{relative} already exists and differs; pass --force to replace it"
                )
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        print(f"copy {relative}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", default=".", help="project directory (default: .)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the layout without writing")
    parser.add_argument("--force", action="store_true",
                        help="replace existing files that differ")
    args = parser.parse_args()

    target = Path(args.target).expanduser().resolve()
    if not target.is_dir():
        raise SystemExit(f"target is not a directory: {target}")
    if not args.dry_run:
        target.mkdir(parents=True, exist_ok=True)

    pairs = [
        (KIT_ROOT / "AGENTS.md", target / "AGENTS.md"),
        (KIT_ROOT / ".gitignore", target / ".gitignore"),
        (KIT_ROOT / "templates" / "job.lsf", target / "templates" / "job.lsf"),
        (KIT_ROOT / "templates" / "smoke.lsf", target / "templates" / "smoke.lsf"),
        (KIT_ROOT / "templates" / "config.ini", target / "templates" / "config.ini"),
        (KIT_ROOT / "templates" / "ssh_config", target / "templates" / "ssh_config"),
        (SKILL_ROOT / "templates" / "README.md", target / "README.md"),
    ]
    for source in sorted((SKILL_ROOT / "templates" / "github").rglob("*")):
        if source.is_file():
            pairs.append((source, target / ".github" / source.relative_to(
                SKILL_ROOT / "templates" / "github")))

    copy_files(target, pairs, args.force, args.dry_run)

    experiments = target / "experiments.jsonl"
    if not experiments.exists():
        if args.dry_run:
            print("create experiments.jsonl")
        else:
            experiments.touch()
            print("create experiments.jsonl")
    return 0


if __name__ == "__main__":
    sys.exit(main())
