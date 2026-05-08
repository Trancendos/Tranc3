#!/usr/bin/env python3
"""
scripts/spawn_personality.py
CLI tool to spawn a new Tranc3 personality repo.

Usage:
    python scripts/spawn_personality.py --list
    python scripts/spawn_personality.py --personality dorris-fontaine --repo-name tranc3-finance
    python scripts/spawn_personality.py --personality the-guardian --repo-name tranc3-security --output ./repos
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description="Spawn a Tranc3 personality repo")
    parser.add_argument("--personality", "-p", help="Personality ID to spawn")
    parser.add_argument("--repo-name", "-n", help="Name for the new repo directory")
    parser.add_argument("--output", "-o", default="./spawned", help="Output parent directory (default: ./spawned)")
    parser.add_argument("--list", "-l", action="store_true", help="List available personalities")
    args = parser.parse_args()

    from src.personality.spawner import PersonalitySpawner
    spawner = PersonalitySpawner()

    if args.list:
        personalities = spawner.list_personalities()
        print("\nAvailable personalities:\n")
        for p in personalities:
            print(f"  {p['id']:<26}  {p['code_name']:<28}  [{p['domain']}]")
            print(f"  {'':26}  {p['description']}")
            print()
        return 0

    if not args.personality:
        parser.error("--personality is required unless --list is used")
    if not args.repo_name:
        parser.error("--repo-name is required")

    print(f"\nSpawning personality '{args.personality}' as repo '{args.repo_name}'...\n")
    try:
        result = spawner.spawn(args.personality, args.repo_name, args.output)
    except (ValueError, FileExistsError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print(f"  Code Name  : {result['code_name']}")
    print(f"  Output     : {result['output_path']}")
    print(f"  Files      : {len(result['files_written'])}")
    print()
    print("Next steps:")
    print()
    for line in result["instructions"].splitlines():
        print(f"  {line}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
