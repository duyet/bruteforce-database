#!/usr/bin/env python3
"""
Wordlist Deduplication Tool

Remove duplicate entries from wordlists while preserving order and quality.
Now handles nested wordlists (forced-browsing/, etc.) with case-insensitive option.

Philosophy: Perfection is achieved not when there is nothing more to add,
but when there is nothing left to take away.
"""

import sys
import time
from pathlib import Path
from typing import Set, List, Optional


def read_lines_safely(filepath: Path) -> List[str]:
    """Read lines with automatic encoding detection. Never silently corrupts data."""
    # Try UTF-8 first (most common), fall back to latin-1/cp1252
    for enc in ('utf-8', 'latin-1', 'cp1252'):
        try:
            with open(filepath, 'r', encoding=enc) as f:
                return f.readlines()
        except (UnicodeDecodeError, ValueError):
            continue
    # Last resort: read as latin-1 (always succeeds, never corrupts)
    with open(filepath, 'r', encoding='latin-1') as f:
        return f.readlines()


def deduplicate_file(
    filepath: Path,
    output_path: Optional[Path] = None,
    preserve_order: bool = True,
    case_insensitive: bool = False,
    sort_output: bool = False,
):
    """
    Remove duplicates from a wordlist file.

    Args:
        filepath: Input wordlist file
        output_path: Output file (overwrites input if None)
        preserve_order: Keep first occurrence order (slower but maintains context)
        case_insensitive: Treat entries with different case as duplicates
        sort_output: Sort entries alphabetically in output
    """
    root = Path(__file__).parent.parent
    rel_path = str(filepath.relative_to(root)) if root in filepath.parents else str(filepath)
    print(f"  Processing {rel_path}...", end=" ")

    lines = read_lines_safely(filepath)

    original_count = len(lines)
    original_nonempty = sum(1 for line in lines if line.strip())

    # Deduplicate
    unique_lines: List[str] = []

    if sort_output:
        seen: Set[str] = set()
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            key = stripped.lower() if case_insensitive else stripped
            if key not in seen:
                seen.add(key)
                unique_lines.append(stripped)
        unique_lines = sorted(unique_lines)
        unique_lines = [line + '\n' for line in unique_lines]
    elif preserve_order:
        seen: Set[str] = set()
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            key = stripped.lower() if case_insensitive else stripped
            if key not in seen:
                seen.add(key)
                unique_lines.append(stripped + '\n')
    else:
        seen: Set[str] = set()
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            key = stripped.lower() if case_insensitive else stripped
            if key not in seen:
                seen.add(key)
                unique_lines.append(stripped)
        unique_lines = sorted(set(unique_lines))
        unique_lines = [line + '\n' for line in unique_lines]

    unique_count = len(unique_lines)
    removed = original_nonempty - unique_count

    print(f"{original_nonempty:,} -> {unique_count:,} entries ({removed:,} removed, "
          f"{removed / original_nonempty * 100:.1f}% reduction)"
          f"{' [CI]' if case_insensitive else ''}")

    # Write output
    output = output_path or filepath
    with open(output, 'w', encoding='utf-8') as f:
        f.writelines(unique_lines)

    return {
        "file": str(rel_path),
        "original": original_nonempty,
        "unique": unique_count,
        "removed": removed,
        "percentage": removed / original_nonempty * 100 if original_nonempty > 0 else 0,
    }


def find_wordlists(root: Path) -> List[Path]:
    """Find all wordlist files recursively, skipping .git and scripts."""
    skip_dirs = {'.git', 'node_modules', '__pycache__'}
    wordlists = []
    for ext in ('*.txt', '*.lst'):
        for f in root.rglob(ext):
            if not any(skip in f.parts for skip in skip_dirs):
                wordlists.append(f)
    return sorted(wordlists)


def deduplicate_all(
    root: Path,
    preserve_order: bool = True,
    case_insensitive: bool = False,
    sort_output: bool = False,
):
    """Deduplicate all wordlists in the repository."""
    wordlists = find_wordlists(root)
    print(f"\nDeduplicating {len(wordlists)} wordlists in "
          f"{'CI mode' if case_insensitive else 'standard mode'}...\n")

    total_removed = 0
    results = []
    for wordlist in wordlists:
        result = deduplicate_file(
            wordlist,
            preserve_order=preserve_order,
            case_insensitive=case_insensitive,
            sort_output=sort_output,
        )
        total_removed += result["removed"]
        results.append(result)

    print(f"\nComplete! Removed {total_removed:,} total duplicates across {len(wordlists)} files.")
    return results


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Deduplicate wordlist files in the bruteforce-database repository.",
    )
    parser.add_argument('input', nargs='?', help='Single wordlist file to deduplicate')
    parser.add_argument('output', nargs='?', help='Output file (default: overwrite input)')
    parser.add_argument('--all', action='store_true', help='Deduplicate all wordlists in repo')
    parser.add_argument('--case-insensitive', action='store_true',
                        help='Treat same words with different case as duplicates')
    parser.add_argument('--sort', action='store_true', help='Sort entries alphabetically')
    parser.add_argument('--no-preserve-order', action='store_true',
                        help='Allow reordering for faster dedup')

    args = parser.parse_args()

    if args.all:
        root = Path(__file__).parent.parent
        deduplicate_all(
            root,
            preserve_order=not args.no_preserve_order,
            case_insensitive=args.case_insensitive,
            sort_output=args.sort,
        )
    elif args.input:
        input_file = Path(args.input)
        output_file = Path(args.output) if args.output else None
        deduplicate_file(
            input_file,
            output_file,
            preserve_order=not args.no_preserve_order,
            case_insensitive=args.case_insensitive,
            sort_output=args.sort,
        )
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
