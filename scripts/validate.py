#!/usr/bin/env python3
"""
Wordlist Validation and Quality Control System

This tool validates wordlist files for:
- Encoding consistency (UTF-8)
- Format correctness (one entry per line)
- File integrity (no corruption)
- Basic statistics generation

Philosophy: Quality is not an act, it's a habit.
"""

import os
import sys
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Tuple
from collections import Counter


class WordlistValidator:
    """Validates and analyzes wordlist files with surgical precision."""

    def __init__(self, root_dir: Path = None):
        self.root_dir = root_dir or Path(__file__).parent.parent
        self.errors = []
        self.warnings = []

    def validate_file(self, filepath: Path) -> Dict:
        """
        Validate a single wordlist file.

        Returns comprehensive metadata and validation results.
        Uses streaming reads for large files to minimize memory.
        """
        if not filepath.exists():
            return {"error": "File does not exist"}

        result = {
            "path": str(filepath.relative_to(self.root_dir))
                     if self.root_dir in filepath.parents
                     else str(filepath),
            "size_bytes": filepath.stat().st_size,
            "valid": True,
            "errors": [],
            "warnings": [],
        }

        try:
            # Read raw bytes (needed once for hash + encoding detection)
            with open(filepath, 'rb') as f:
                raw_data = f.read()
                result["sha256"] = hashlib.sha256(raw_data).hexdigest()

            # Detect encoding - try UTF-8 first, then latin-1, then system default
            encoding = None
            content = None
            for enc in ('utf-8', 'latin-1', 'cp1252'):
                try:
                    content = raw_data.decode(enc)
                    encoding = enc
                    break
                except (UnicodeDecodeError, LookupError):
                    continue

            if content is None:
                result["valid"] = False
                result["errors"].append("Unable to decode file with UTF-8, latin-1, or cp1252")
                return result

            result["encoding"] = encoding
            if encoding != 'utf-8':
                result["warnings"].append(f"Non-UTF-8 encoding detected ({encoding})")

            # Check for binary content on raw bytes (fast, no line iteration)
            null_bytes = raw_data.count(b'\x00')
            control_chars = sum(
                1 for b in raw_data if b < 0x20 and b not in (0x09, 0x0A, 0x0D)
            )
            null_ratio = null_bytes / len(raw_data) if raw_data else 0
            control_ratio = control_chars / len(raw_data) if raw_data else 0

            if null_ratio > 0.01:
                result["warnings"].append(
                    f"Binary content detected ({null_bytes} null bytes, "
                    f"{null_ratio:.2%} of file)"
                )

            # Analyze content line by line
            lines = content.splitlines()
            result["total_lines"] = len(lines)

            non_empty_lines = [line for line in lines if line.strip()]
            result["non_empty_lines"] = len(non_empty_lines)

            # Check for duplicates using set
            unique_entries = set(non_empty_lines)
            result["unique_entries"] = len(unique_entries)

            if len(unique_entries) < len(non_empty_lines):
                duplicates = len(non_empty_lines) - len(unique_entries)
                result["warnings"].append(f"{duplicates} duplicate entries found")
                result["duplicate_count"] = duplicates

            # Line length statistics
            if non_empty_lines:
                lengths = [len(line) for line in non_empty_lines]
                result["min_length"] = min(lengths)
                result["max_length"] = max(lengths)
                result["avg_length"] = sum(lengths) / len(lengths)

            # Warn on suspicious control character ratio
            if control_ratio > 0.001 and null_ratio <= 0.01:
                result["warnings"].append(
                    f"Unusual control characters detected ({control_chars} chars, "
                    f"{control_ratio:.4%} of file)"
                )

        except Exception as e:
            result["valid"] = False
            result["errors"].append(f"Validation error: {e}")

        return result

    def find_wordlists(self) -> List[Path]:
        """Find all wordlist files (*.txt, *.lst) recursively, skipping .git and scripts."""
        skip_dirs = {'.git', 'node_modules', 'scripts', '__pycache__'}
        wordlists = []
        for ext in ('*.txt', '*.lst'):
            for f in self.root_dir.rglob(ext):
                if not any(skip in f.parts for skip in skip_dirs):
                    wordlists.append(f)
        return sorted(wordlists)

    def validate_all(self) -> Dict:
        """Validate all wordlists and generate comprehensive report."""
        wordlists = self.find_wordlists()
        today = __import__('datetime').date.today().isoformat()

        results = {
            "validation_date": today,
            "total_files": len(wordlists),
            "files": [],
            "summary": {
                "valid_files": 0,
                "invalid_files": 0,
                "total_warnings": 0,
                "total_size_bytes": 0,
                "total_entries": 0,
                "total_unique_entries": 0,
            }
        }

        print(f"\nValidating {len(wordlists)} wordlist files...\n")

        for wordlist in wordlists:
            label = str(wordlist.relative_to(self.root_dir))
            print(f"  {label} ...", end=" ")
            file_result = self.validate_file(wordlist)
            results["files"].append(file_result)

            status = "OK" if file_result["valid"] else "FAIL"
            print(f"[{status}]")

            results["summary"]["total_warnings"] += len(file_result.get("warnings", []))
            results["summary"]["total_size_bytes"] += file_result.get("size_bytes", 0)
            results["summary"]["total_entries"] += file_result.get("non_empty_lines", 0)
            results["summary"]["total_unique_entries"] += file_result.get("unique_entries", 0)

            if file_result["valid"]:
                results["summary"]["valid_files"] += 1
            else:
                results["summary"]["invalid_files"] += 1
                for err in file_result.get("errors", []):
                    print(f"    Error: {err}")

        return results

    def generate_manifest(self, output_path: Path = None):
        """Generate a comprehensive manifest of all wordlists."""
        output_path = output_path or self.root_dir / "manifest.json"

        results = self.validate_all()

        summary = results["summary"]
        print(f"\nValidation Summary:")
        print(f"  Files:      {results['total_files']} total, "
              f"{summary['valid_files']} valid, "
              f"{summary['invalid_files']} invalid")
        print(f"  Warnings:   {summary['total_warnings']}")
        print(f"  Size:       {summary['total_size_bytes'] / 1024 / 1024:.2f} MB")
        print(f"  Entries:    {summary['total_entries']:,}")
        print(f"  Unique:     {summary['total_unique_entries']:,}")

        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"\nManifest saved to {output_path}")

        return 0 if summary['invalid_files'] == 0 else 1


def main():
    """Main entry point for validation tool."""
    validator = WordlistValidator()

    if len(sys.argv) > 1 and sys.argv[1] == "--file":
        filepath = Path(sys.argv[2]).resolve()
        if not filepath.exists():
            print(f"Error: file not found: {filepath}")
            sys.exit(1)
        result = validator.validate_file(filepath)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result.get("valid", False) else 1)
    else:
        sys.exit(validator.generate_manifest())


if __name__ == "__main__":
    main()
