# update_os_number.py

Automatically update the **OS version comment** (second line) in p1280 runset files based on the DR file.

## Overview

This script reads line 5 from a DR file (e.g. `p1280d1.21_dr.rs`), extracts the `drc` and `tic` OS version strings, and inserts/replaces a standardized comment as the **second line** of every matching `.rs` file:

```
// Updated wrt drcOS: ad-1280.1-1.0.5.1_X80D/3 and ticOS: ad-1280.1-1.0.5.1_X80D/4 at April 13, 2026
```

If a file already has an `// Updated wrt` line, it is **replaced** (not duplicated).

---

## Quick Start

```bash
# From the PXL directory — update all matching files
python scripts/update_os_number.py --root .

# Preview changes without modifying anything
python scripts/update_os_number.py --root . --dry-run

# Only update files you've changed in git
python scripts/update_os_number.py --root . --git-only
```

---

## Usage

```
python scripts/update_os_number.py [OPTIONS]
```

### Options

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--root DIR` | `-r` | `.` | Root directory to scan for matching files |
| `--os-file FILE` | | auto-detect | Path to the DR file to extract the OS version from. Defaults to `PXL/dr_files/p1280d1.21_dr.rs` |
| `--pattern REGEX` | `-p` | *(built-in)* | Regex to match filenames. Defaults to the p1280 layer/check pattern |
| `--match-path` | | off | Match regex against full file path instead of filename only |
| `--recursive` | `-R` | on | Search directories recursively |
| `--no-recursive` | | | Search only in the root directory |
| `--git-only` | `-g` | off | Only update files that git reports as changed (modified, added, or untracked) |
| `--backup` | `-bak` | off | Create `.bak` backup of each file before modifying |
| `--no-backup` | | *(default)* | Do not create backups |
| `--dry-run` | | off | Show what would be changed without writing any files |
| `--skip-if-present` | | *(default)* | Skip files whose second line already matches the new line |
| `--no-skip` | | | Force update even if the line is already present |
| `--verbose` | `-v` | | Show detailed per-file output |
| `--quiet` | `-q` | | Only show errors and the final summary |
| `--encoding` | | `utf-8` | File encoding to use |

---

## Examples

### Update all matching files

```bash
python scripts/update_os_number.py --root .
```

### Dry-run (preview only)

```bash
python scripts/update_os_number.py --root . --dry-run
```

Output:
```
Using OS file: /path/to/PXL/dr_files/p1280d1.21_dr.rs
Line to insert: // Updated wrt drcOS: ... and ticOS: ... at April 13, 2026
Found 47 file(s) to process.
[DRY-RUN] No files will be modified.

  ./p1280_V0.rs: (dry) modified
  ./p1280_V1.rs: (dry) modified
  ...

Summary: 45 modified, 2 skipped, 0 errors (out of 47 files)
```

### Only update git-changed files

```bash
python scripts/update_os_number.py --root . --git-only
```

This detects files changed in your working tree (staged, unstaged, or untracked) and only updates those that also match the filename pattern.

### Custom DR file

```bash
python scripts/update_os_number.py --root . --os-file /path/to/custom_dr.rs
```

### Custom file pattern

```bash
# Only target .rs files containing "M1" in the name
python scripts/update_os_number.py --root . --pattern "M1.*\.rs$"
```

### Create backups with verbose output

```bash
python scripts/update_os_number.py --root . --backup --verbose
```

Each modified file will have a `.bak` copy created before changes are applied.

---

## How It Works

1. **Extract**: Reads line 5 of the DR file and parses out the `drcOS: ...` and `ticOS: ...` substrings
2. **Scan**: Finds all files under `--root` matching the filename regex
3. **Filter** *(optional)*: If `--git-only`, only keeps files that git reports as changed
4. **Update**: For each matched file:
   - If the second line starts with `// Updated wrt` → **replace** it
   - Otherwise → **insert** the new line as line 2 (preserving all existing content)
   - If the second line already matches exactly → **skip**
5. **Write**: Uses atomic write (temp file + `os.replace`) to avoid partial writes

---

## Default File Pattern

The built-in pattern matches these file types:

| Category | Pattern |
|----------|---------|
| Via layers | `p1280_V[GT01].rs` |
| Via check modules | `Vm2xa_checks.rs`, `Vxaxb_checks.rs`, `Vyayb_checks.rs`, etc. |
| Specialized layers | `p1280_EDM.rs`, `p1280_HRS.rs`, `p1280_GCN.rs`, `p1280_BLV.rs`, etc. |

---

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success (all files processed without errors) |
| `1` | Errors occurred during processing, or OS line extraction failed |
| `2` | Root directory not found |

---

## Requirements

- Python 3.9+
- `git` in PATH (only required for `--git-only`)
- No external pip packages needed
