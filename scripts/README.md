# Validation & Quality Control Scripts

This directory contains tools for maintaining the quality and integrity of the wordlist collection.

## Scripts

### `validate.py`
Validates all wordlists and generates a comprehensive manifest.

**Features:**
- Encoding detection and validation (UTF-8, latin-1, cp1252)
- Duplicate detection
- File integrity checks (SHA256)
- Statistics generation (line counts, lengths, etc.)
- Binary content detection via raw byte analysis
- Manifest generation with full metadata (dynamic date)

**Usage:**
```bash
# Validate all wordlists and generate manifest
python3 validate.py

# Validate a specific file
python3 validate.py --file wordlist.txt
```

**Output:**
- Console output showing validation progress
- `manifest.json` with comprehensive metadata
- Exit code 0 if all files valid, 1 if any invalid

### `deduplicate.py`
Remove duplicate entries from wordlists while preserving order.
Now handles wordlists in subdirectories (e.g., `forced-browsing/`).

**Features:**
- Order-preserving deduplication (keeps first occurrence)
- Recursive discovery of all wordlists (including nested dirs)
- Case-insensitive deduplication (`--case-insensitive`)
- Alphabetical sorting (`--sort`)
- Batch processing of all wordlists
- Statistics reporting (duplicates removed, percentage)

**Usage:**
```bash
# Deduplicate a specific file
python3 deduplicate.py wordlist.txt

# Deduplicate with output to new file
python3 deduplicate.py input.txt output.txt

# Deduplicate all wordlists in place (recursive)
python3 deduplicate.py --all

# Case-insensitive dedup across entire repo
python3 deduplicate.py --all --case-insensitive

# Sort entries while deduplicating
python3 deduplicate.py --all --sort
```

**Note:** Use `--all` with caution as it modifies files in place.

### `analyze.py`
Wordlist Intelligence & Analysis Tool — new in v2.0.

**Features:**
- **Composition analysis:** character class breakdown (upper, lower, digit, special), entropy estimation
- **Cross-reference:** pairwise Jaccard similarity, intersection/union, per-file uniqueness
- **Pattern detection:** date-like patterns, keyboard walks, repeated substrings
- **Smart merging:** combine wordlists with frequency tracking, rank by source count
- **Full repository report:** comprehensive intelligence report with per-file breakdowns

**Usage:**
```bash
# Character composition analysis
python3 analyze.py --composition passwords.txt

# Cross-reference two or more wordlists
python3 analyze.py --cross-reference file1.txt file2.txt

# Smart merge with frequency ranking
python3 analyze.py --merge --rank-by-frequency --output merged.txt *.txt

# Full repo intelligence report
python3 analyze.py --report --report-output report.json
```

## Requirements

- Python 3.8+
- No external dependencies (uses only standard library)

## CI/CD Integration

These scripts are automatically run by GitHub Actions on every commit and pull request.

See [`.github/workflows/validate.yml`](../.github/workflows/validate.yml) for the CI/CD configuration.

## Philosophy

These tools embody our commitment to quality:
- **Automation over manual effort** - Quality checks should be automatic
- **Transparency through data** - Every file's metadata is tracked
- **Prevention over correction** - Catch issues before they reach users
- **Simplicity in implementation** - Readable code that anyone can understand

---

**"Quality is not an act, it's a habit." - Aristotle**
