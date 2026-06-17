#!/usr/bin/env python3
"""
Wordlist Intelligence & Analysis Tool

Cross-reference, pattern analysis, and smart merging for wordlists.
Enables data-driven decisions about which wordlists to use and how they overlap.

Features:
  - Cross-reference: find entries common across multiple wordlists
  - Composition: character-class breakdown (upper, lower, digit, special)
  - Entropy estimation: approximate entropy per entry
  - Smart merge: combine wordlists with frequency tracking
  - Pattern analysis: detect dates, keyboard walks, repeated chars
  - Full JSON report for CI integration

Usage:
  python3 scripts/analyze.py --cross-reference file1.txt file2.txt
  python3 scripts/analyze.py --composition passwords.txt
  python3 scripts/analyze.py --merge --output merged.txt file1.txt file2.txt
  python3 scripts/analyze.py --all --report report.json
"""

import argparse
import hashlib
import json
import math
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


CHARSET_UPPER = set('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
CHARSET_LOWER = set('abcdefghijklmnopqrstuvwxyz')
CHARSET_DIGIT = set('0123456789')
CHARSET_SPECIAL = set('!@#$%^&*()_+-=[]{}|;:,.<>?/~`\'"\\ ')


def load_entries(filepath: Path, encoding: str = 'utf-8') -> List[str]:
    """Load non-empty, stripped entries from a wordlist file."""
    try:
        with open(filepath, 'r', encoding=encoding, errors='ignore') as f:
            content = f.read()
    except Exception:
        # Fallback to latin-1
        with open(filepath, 'r', encoding='latin-1', errors='ignore') as f:
            content = f.read()
    return [line.strip() for line in content.splitlines() if line.strip()]


def entropy(s: str) -> float:
    """Compute Shannon entropy of a string."""
    if not s:
        return 0.0
    freq = Counter(s)
    length = len(s)
    return -sum((c / length) * math.log2(c / length) for c in freq.values())


def charset_composition(s: str) -> Dict[str, float]:
    """Return fraction of each character class in the string."""
    if not s:
        return {'upper': 0, 'lower': 0, 'digit': 0, 'special': 0}
    total = len(s)
    return {
        'upper': sum(1 for c in s if c in CHARSET_UPPER) / total,
        'lower': sum(1 for c in s if c in CHARSET_LOWER) / total,
        'digit': sum(1 for c in s if c in CHARSET_DIGIT) / total,
        'special': sum(1 for c in s if c in CHARSET_SPECIAL) / total,
    }


def charset_categories(s: str) -> List[str]:
    """Return list of charset categories present in the string."""
    cats = []
    if any(c in CHARSET_UPPER for c in s):
        cats.append('upper')
    if any(c in CHARSET_LOWER for c in s):
        cats.append('lower')
    if any(c in CHARSET_DIGIT for c in s):
        cats.append('digit')
    if any(c in CHARSET_SPECIAL for c in s):
        cats.append('special')
    return cats


def is_date_like(s: str) -> bool:
    """Heuristic: does the string look like a date (YYYY, YYYYMMDD, etc.)."""
    digits = sum(1 for c in s if c.isdigit())
    return len(s) >= 4 and digits >= len(s) * 0.6 and any(
        pattern in s for pattern in
        ['19', '20', '21', '22', '23', '24', '25', '26']
    )


def is_keyboard_walk(s: str) -> bool:
    """Simple heuristic for sequential keyboard patterns."""
    rows = ['qwertyuiop', 'asdfghjkl', 'zxcvbnm']
    s_lower = s.lower()
    for i in range(len(s_lower) - 2):
        for row in rows:
            triplet = s_lower[i:i+3]
            if triplet in row or triplet[::-1] in row:
                return True
    return False


def is_repeated_pattern(s: str) -> bool:
    """Check if string is a repeated short pattern (abcabc, 123123)."""
    if len(s) < 4:
        return False
    for period in range(1, len(s) // 2 + 1):
        if len(s) % period == 0 and s[:period] * (len(s) // period) == s:
            return True
    return False


def analyze_composition(entries: List[str], sample_size: int = 100000) -> Dict:
    """
    Analyze character composition of password entries.
    If the list is large, analyze a random sample for speed.
    """
    if not entries:
        return {}

    total = len(entries)
    if total > sample_size:
        import random
        random.seed(42)
        sample = random.sample(entries, sample_size)
    else:
        sample = entries

    min_len = min(len(e) for e in entries)
    max_len = max(len(e) for e in entries)
    avg_len = sum(len(e) for e in entries) / total

    # Charset category distribution (over full set for accuracy)
    cats = Counter()
    for e in entries:
        for cat in charset_categories(e):
            cats[cat] += 1

    # Entropy distribution (over sample for speed)
    entropies = [entropy(e) for e in sample]
    avg_entropy = sum(entropies) / len(entropies) if entropies else 0

    # Pattern detection (over sample)
    date_like = sum(1 for e in sample if is_date_like(e))
    keyboard = sum(1 for e in sample if is_keyboard_walk(e))
    repeated = sum(1 for e in sample if is_repeated_pattern(e))

    # Length distribution (top 10)
    length_dist = Counter(len(e) for e in entries).most_common(10)

    return {
        'total_entries': total,
        'min_length': min_len,
        'max_length': max_len,
        'avg_length': round(avg_len, 4),
        'avg_entropy': round(avg_entropy, 4),
        'categories': {
            'upper_pct': round(cats.get('upper', 0) / total * 100, 2),
            'lower_pct': round(cats.get('lower', 0) / total * 100, 2),
            'digit_pct': round(cats.get('digit', 0) / total * 100, 2),
            'special_pct': round(cats.get('special', 0) / total * 100, 2),
        },
        'patterns': {
            'date_like_pct': round(date_like / len(sample) * 100, 2),
            'keyboard_walk_pct': round(keyboard / len(sample) * 100, 2),
            'repeated_pattern_pct': round(repeated / len(sample) * 100, 2),
        },
        'top_lengths': [(str(k), v) for k, v in length_dist],
    }


def cross_reference(filepaths: List[Path]) -> Dict:
    """
    Find overlapping entries across multiple wordlists.
    Returns intersection size, unique per list, and Jaccard similarities.
    """
    if len(filepaths) < 2:
        return {'error': 'Need at least 2 files for cross-reference'}

    names = [f.name for f in filepaths]
    sets: List[Set[str]] = []
    labels: List[str] = []

    print(f"\nLoading {len(filepaths)} wordlists for cross-reference...")
    for fp in filepaths:
        entries = load_entries(fp)
        s = set(entries)
        sets.append(s)
        labels.append(f"{fp.name} ({len(s):,} unique)")
        print(f"  {fp.name}: {len(s):,} unique entries")

    # Pairwise Jaccard similarity
    pairwise = []
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            intersection = sets[i] & sets[j]
            union = sets[i] | sets[j]
            jaccard = len(intersection) / len(union) if union else 0
            pairwise.append({
                'file_a': filepaths[i].name,
                'file_b': filepaths[j].name,
                'intersection': len(intersection),
                'union': len(union),
                'jaccard_similarity': round(jaccard, 6),
            })

    # Global intersection (common to ALL files)
    common_all = sets[0].copy()
    for s in sets[1:]:
        common_all &= s

    # Entries unique to each file
    uniques = []
    for i, s in enumerate(sets):
        others = set()
        for j in range(len(sets)):
            if i != j:
                others |= sets[j]
        unique_to_i = s - others
        uniques.append({
            'file': filepaths[i].name,
            'unique_entries': len(unique_to_i),
            'unique_pct': round(len(unique_to_i) / len(s) * 100, 2) if s else 0,
        })

    return {
        'files': labels,
        'common_to_all': len(common_all),
        'pairwise': pairwise,
        'unique_per_file': uniques,
    }


def smart_merge(filepaths: List[Path], output: Path, rank_by_frequency: bool = False) -> Dict:
    """
    Merge multiple wordlists, tracking source frequency.
    If rank_by_frequency, entries appearing in more files are placed first.
    """
    print(f"\nMerging {len(filepaths)} wordlists into {output}...")

    freq: Dict[str, int] = Counter()
    per_file = []

    for fp in filepaths:
        entries = load_entries(fp)
        unique = set(entries)
        per_file.append(len(unique))
        for e in unique:
            freq[e] += 1

    total_unique = len(freq)
    total_with_freq = sum(freq.values())

    if rank_by_frequency:
        sorted_entries = sorted(freq.items(), key=lambda x: (-x[1], x[0]))
        merged = [entry for entry, count in sorted_entries]
        write_lines = [f"{entry}\n" for entry in merged]
    else:
        merged = list(freq.keys())
        write_lines = sorted(merged + ['\n'])

    with open(output, 'w', encoding='utf-8') as f:
        f.writelines(write_lines)

    # Frequency distribution
    freq_dist = Counter(freq.values())
    freq_table = sorted(
        [{'sources': k, 'count': v} for k, v in freq_dist.items()],
        key=lambda x: -x['sources'],
    )

    print(f"  Unique entries: {total_unique:,}")
    print(f"  Total (with multiplicities): {total_with_freq:,}")
    print(f"  Saved to: {output}")

    return {
        'input_files': [str(f) for f in filepaths],
        'unique_per_file': per_file,
        'merged_unique': total_unique,
        'total_with_multiplicities': total_with_freq,
        'frequency_distribution': freq_table[:50],
    }


def generate_report(validator) -> Dict:
    """
    Generate a comprehensive intelligence report on the entire repository.
    Combines validation data with compositional analysis.
    """
    wordlists = validator.find_wordlists()
    report = {
        'generated': __import__('datetime').date.today().isoformat(),
        'repository': 'bruteforce-database',
        'total_files': len(wordlists),
        'file_reports': [],
        'global_summary': {
            'total_entries': 0,
            'total_unique_entries': 0,
            'total_size_bytes': 0,
        },
    }

    print(f"\nGenerating intelligence report on {len(wordlists)} wordlists...\n")

    for wl in wordlists:
        label = str(wl.relative_to(validator.root_dir))
        print(f"  Analyzing {label}...", end=" ")

        entries = load_entries(wl)
        if not entries:
            print("[SKIP - empty]")
            continue

        val = validator.validate_file(wl)
        comp = analyze_composition(entries)

        report_entry = {
            'file': label,
            'size_bytes': val.get('size_bytes', 0),
            'encoding': val.get('encoding', 'unknown'),
            'sha256': val.get('sha256', ''),
            'composition': comp,
        }
        report['file_reports'].append(report_entry)

        report['global_summary']['total_entries'] += comp.get('total_entries', 0)
        report['global_summary']['total_unique_entries'] += len(set(entries))
        report['global_summary']['total_size_bytes'] += val.get('size_bytes', 0)

        print(f"[{comp.get('total_entries', 0):,} entries]")

    return report


def main():
    parser = argparse.ArgumentParser(
        description='Wordlist Intelligence and Analysis Tool',
    )
    parser.add_argument('files', nargs='*', help='Wordlist files to analyze')

    parser.add_argument('--composition', '-c', action='store_true',
                        help='Analyze character composition of a wordlist')
    parser.add_argument('--cross-reference', '-x', action='store_true',
                        help='Cross-reference entries across wordlists')
    parser.add_argument('--merge', '-m', action='store_true',
                        help='Merge wordlists into a single deduplicated file')
    parser.add_argument('--output', '-o', type=str, default='',
                        help='Output file for merge or report')
    parser.add_argument('--rank-by-frequency', '-r', action='store_true',
                        help='In merge, rank entries by how many sources contain them')
    parser.add_argument('--report', action='store_true',
                        help='Generate comprehensive intelligence report on the repository')
    parser.add_argument('--report-output', type=str, default='intelligence-report.json',
                        help='Path for report output (default: intelligence-report.json)')

    args = parser.parse_args()
    root = Path(__file__).parent.parent

    # No args: show help
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    # Comprehensive report
    if args.report:
        validator = __import__('validate', fromlist=['WordlistValidator'])
        v = validator.WordlistValidator(root)
        report = generate_report(v)
        output_path = Path(args.report_output)
        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2)
        total = report['global_summary']
        print(f"\nReport Summary:")
        print(f"  Files:   {report['total_files']}")
        print(f"  Entries: {total['total_entries']:,}")
        print(f"  Unique:  {total['total_unique_entries']:,}")
        print(f"  Size:    {total['total_size_bytes'] / 1024 / 1024:.2f} MB")
        print(f"  Report:  {output_path}")
        sys.exit(0)

    if not args.files:
        print("Error: specify wordlist files to analyze")
        sys.exit(1)

    filepaths = [Path(f) for f in args.files]
    missing = [str(f) for f in filepaths if not f.exists()]
    if missing:
        print(f"Error: files not found: {', '.join(missing)}")
        sys.exit(1)

    # Composition analysis
    if args.composition:
        for fp in filepaths:
            entries = load_entries(fp)
            print(f"\n{'=' * 50}")
            print(f"File: {fp.name}")
            print(f"{'=' * 50}")
            comp = analyze_composition(entries)
            print(f"  Entries:     {comp.get('total_entries', 0):,}")
            print(f"  Length:      {comp.get('min_length')} - {comp.get('max_length')} "
                  f"(avg {comp.get('avg_length')})")
            print(f"  Avg Entropy: {comp.get('avg_entropy')}")
            print(f"\n  Character Classes:")
            cats = comp.get('categories', {})
            print(f"    Uppercase:  {cats.get('upper_pct', 0)}%")
            print(f"    Lowercase:  {cats.get('lower_pct', 0)}%")
            print(f"    Digits:     {cats.get('digit_pct', 0)}%")
            print(f"    Special:    {cats.get('special_pct', 0)}%")
            print(f"\n  Patterns (sample):")
            pat = comp.get('patterns', {})
            print(f"    Date-like:      {pat.get('date_like_pct', 0)}%")
            print(f"    Keyboard walk:  {pat.get('keyboard_walk_pct', 0)}%")
            print(f"    Repeated:       {pat.get('repeated_pattern_pct', 0)}%")
        sys.exit(0)

    # Cross-reference
    if args.cross_reference:
        xref = cross_reference(filepaths)
        print(f"\nCross-Reference Results:")
        print(f"  Common to all: {xref.get('common_to_all', 0):,} entries")
        print(f"\n  Unique per file:")
        for u in xref.get('unique_per_file', []):
            print(f"    {u['file']}: {u['unique_entries']:,} ({u['unique_pct']}%)")
        print(f"\n  Pairwise Jaccard Similarity:")
        for p in xref.get('pairwise', []):
            print(f"    {p['file_a']} vs {p['file_b']}: "
                  f"{p['jaccard_similarity']:.4f} "
                  f"(intersection: {p['intersection']:,})")
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(xref, f, indent=2)
            print(f"\n  Report saved to: {args.output}")
        sys.exit(0)

    # Merge
    if args.merge:
        if not args.output:
            print("Error: --output is required for merge")
            sys.exit(1)
        result = smart_merge(filepaths, Path(args.output), args.rank_by_frequency)

        # Write frequency metadata
        meta_path = Path(args.output).with_suffix('.meta.json')
        with open(meta_path, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"  Metadata:  {meta_path}")
        sys.exit(0)

    # Default: show info
    print("Specify an action: --composition, --cross-reference, --merge, or --report")
    sys.exit(1)


if __name__ == '__main__':
    main()
