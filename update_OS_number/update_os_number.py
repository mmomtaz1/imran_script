#!/p/foundry/env/ezb/ez/25ww39.1/python/3.11.1/bin/python3
"""update_os_number.py

Scan files and replace/insert the second line with an OS version comment
extracted from a DR file. Targets files matching a regex pattern.

Examples:
  # Default: auto-detect os-file, update matching git-changed .rs files recursively
  python scripts/update_os_number.py --root .

  # Only update git-changed files (dry-run)
  python scripts/update_os_number.py --root . --git-only --dry-run

  # Specify a custom DR file and pattern
  python scripts/update_os_number.py --root . --os-file path/to/dr.rs --pattern "\\.rs$"

  # Dry-run to preview changes
  python scripts/update_os_number.py --root . --dry-run

  # Verbose output for debugging
  python scripts/update_os_number.py --root . --verbose

  # Create backups before modifying
  python scripts/update_os_number.py --root . --backup
"""
from __future__ import annotations

import argparse
from datetime import datetime
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable

sys.path.append("/p/fdk/drwork/python_pkgs/lib/python3.11/site-packages")
sys.path.append("/p/fdk/drwork/python_pkgs/lib/python3.7/site-packages")

log = logging.getLogger("update_os_number")

DEFAULT_PATTERN = (
    r"p1280_V[GT01].rs$"
    r"|(Vm2xa|Vxaxb|Vxbxc|Vxcya|Vya|Vyayb|Vyb|Vybyc|Vyc|Vbm0ye|Vyeyf|Vyfga|Vga|Vgagb)_checks.rs$"
    r"|p1280_(EDM|HRS|PRS_HU|TST|EMGR|IDR|ZIP|SRS|DIC|EtchRing|MC|EA|PRS|TPX|BLV|BSV|BVS|BVH).rs$"
)

# Regex to detect previously inserted OS lines (for replacement, not duplication)
OS_LINE_PATTERN = r"^// Updated wrt"

# Default DR file path (relative to script location)
DEFAULT_OS_FILE = Path(__file__).resolve().parent.parent / "dr_files" / "p1280d1.21_dr.rs"


def extract_os_line(os_file: Path) -> str:
    """Read line 5 from the DR file and extract the OS version comment.

    Returns the formatted comment string, or raises ValueError on failure.
    """
    if not os_file.exists():
        raise FileNotFoundError(f"OS file not found: {os_file}")

    with open(os_file, "r", encoding="utf-8") as f:
        os_lines = f.readlines()

    if len(os_lines) < 5:
        raise ValueError(f"OS file has only {len(os_lines)} lines (need at least 5): {os_file}")

    line_cand = os_lines[4].strip()
    log.debug("Raw line 5: %s", line_cand)

    drcline = re.search(r"drc([^;]*)", line_cand)
    ticline = re.search(r"tic([^;]*)", line_cand)

    if not drcline:
        raise ValueError(f"Could not extract 'drc...' from line 5 of {os_file}: {line_cand!r}")
    if not ticline:
        raise ValueError(f"Could not extract 'tic...' from line 5 of {os_file}: {line_cand!r}")

    result = f"// Updated wrt {drcline.group(0)} and {ticline.group(0)} at {datetime.now():%B %d, %Y}"
    log.debug("Extracted line: %s", result)
    return result


def find_files(root: Path, pattern: str, recursive: bool, match_path: bool) -> Iterable[Path]:
    """Yield files under root whose name (or path) matches the regex pattern."""
    rx = re.compile(pattern)
    if recursive:
        it = root.rglob("*")
    else:
        it = root.iterdir()
    for p in it:
        if not p.is_file():
            continue
        target = str(p) if match_path else p.name
        if rx.search(target):
            yield p


def get_git_changed_files(root: Path) -> set[Path]:
    """Return the set of files that git reports as changed (modified, added, renamed)
    relative to HEAD, including both staged and unstaged changes.
    """
    try:
        # Get staged + unstaged changed files in one shot
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            log.warning("git diff failed: %s", result.stderr.strip())
            return set()

        changed = set()
        for line in result.stdout.strip().splitlines():
            if line:
                changed.add((root / line).resolve())

        # Also include untracked new files
        result_untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=str(root),
            capture_output=True,
            text=True,
        )
        if result_untracked.returncode == 0:
            for line in result_untracked.stdout.strip().splitlines():
                if line:
                    changed.add((root / line).resolve())

        log.debug("Git reports %d changed file(s)", len(changed))
        return changed
    except FileNotFoundError:
        log.error("git not found in PATH. Cannot use --git-only.")
        return set()


def replace_second_line(
    path: Path,
    second_line: str,
    os_pattern: str = OS_LINE_PATTERN,
    backup: bool = False,
    encoding: str = "utf-8",
    skip_if_present: bool = True,
    dry_run: bool = False,
) -> bool:
    """Replace or insert the second line of file at ``path`` with ``second_line``.

    If the existing second line matches ``os_pattern``, it is replaced.
    Otherwise, the new line is inserted as the second line.
    Returns True if file was modified (or would be, in dry-run).
    """
    try:
        text = path.read_text(encoding=encoding)
    except Exception as e:
        raise RuntimeError(f"Failed to read {path}: {e}")

    # Preserve BOM if present
    if text.startswith("\ufeff"):
        bom = "\ufeff"
        text_content = text[1:]
    else:
        bom = ""
        text_content = text

    lines = text_content.splitlines(keepends=True)
    existing_second = lines[1].rstrip("\r\n") if len(lines) > 1 else ""

    if skip_if_present and existing_second == second_line:
        return False

    new_line = second_line.rstrip("\r\n") + "\n"
    first_line = lines[0] if lines else ""
    rest = lines[2:] if len(lines) > 2 else []

    # If the second line matches the OS pattern, replace it; otherwise insert as second line
    if len(lines) > 1 and re.search(os_pattern, existing_second):
        log.debug("  Replacing existing OS line: %s", existing_second.strip())
        new_text = bom + first_line + new_line + "".join(rest)
    else:
        log.debug("  Inserting new OS line (no match for existing)")
        new_text = bom + first_line + new_line + "".join(lines[1:])

    if dry_run:
        return True

    # Backup original if requested
    if backup:
        bak = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, bak)
        log.debug("  Backup: %s", bak)

    # Write atomically via temp file + os.replace
    fd, tmp_path = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(new_text)
        os.replace(tmp_path, str(path))
    except Exception:
        # Clean up temp file if rename failed
        try:
            Path(tmp_path).unlink()
        except OSError:
            pass
        raise

    return True


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Update the OS version comment (second line) in matching runset files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
    %(prog)s --root .                        Update git-changed files from CWD
  %(prog)s --root . --dry-run              Preview without modifying
  %(prog)s --root . --os-file custom.rs    Use a custom DR file
  %(prog)s --root . --pattern '\\.rs$'     Override file pattern
  %(prog)s --root . --backup --verbose     Create backups, show details
  %(prog)s --root . --git-only             Only update git-changed files
  %(prog)s --root . --git-only --dry-run   Preview git-changed file updates
""",
    )
    p.add_argument("--root", "-r", type=Path, default=Path("."),
                   help="Root directory to scan (default: current directory)")
    p.add_argument("--os-file", type=Path, default=None,
                   help="Path to DR file to extract OS version from (default: auto-detect)")
    p.add_argument("--pattern", "-p", type=str, default=DEFAULT_PATTERN,
                   help="Regex to match filenames (default: built-in p1280 pattern)")
    p.add_argument("--match-path", action="store_true",
                   help="Match regex against full path instead of filename only")
    p.add_argument("--recursive", "-R", action="store_true", default=True,
                   help="Search recursively (default: True)")
    p.add_argument("--no-recursive", dest="recursive", action="store_false",
                   help="Search only in root directory, not recursively")
    p.add_argument("--backup", "-bak", action="store_true", default=False,
                   help="Create .bak backup files before modifying")
    p.add_argument("--no-backup", dest="backup", action="store_false",
                   help="Do not create backup files (default)")
    p.add_argument("--dry-run", action="store_true",
                   help="Show what would be changed without writing")
    p.add_argument("--encoding", default="utf-8",
                   help="File encoding (default: utf-8)")
    p.add_argument("--skip-if-present", dest="skip", action="store_true", default=True,
                   help="Skip files whose second line already matches (default)")
    p.add_argument("--no-skip", dest="skip", action="store_false",
                   help="Do not skip even if second line already matches")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Show detailed output for each file")
    p.add_argument("--quiet", "-q", action="store_true",
                   help="Only show summary and errors")
    p.add_argument("--git-only", "-g", dest="git_only", action="store_true", default=True,
                   help="Only update files that git reports as changed (modified/added/untracked) (default)")
    args = p.parse_args(argv)

    # Set up logging
    if args.verbose:
        level = logging.DEBUG
    elif args.quiet:
        level = logging.WARNING
    else:
        level = logging.INFO
    logging.basicConfig(format="%(message)s", level=level, stream=sys.stderr)

    # Resolve OS file
    os_file_path = args.os_file or DEFAULT_OS_FILE
    log.info("Using OS file: %s", os_file_path)

    # Extract the line to insert
    try:
        line = extract_os_line(os_file_path)
    except (FileNotFoundError, ValueError) as e:
        log.error("Error: %s", e)
        return 1
    log.info("Line to insert: %s", line)

    # Validate root
    root = args.root
    if not root.exists() or not root.is_dir():
        log.error("Root path not found or not a directory: %s", root)
        return 2

    # Find matching files
    files = list(find_files(root, args.pattern, args.recursive, args.match_path))

    # Filter to git-changed files only if requested
    if args.git_only:
        git_changed = get_git_changed_files(root)
        if not git_changed:
            log.warning("No git-changed files detected (or git not available).")
            return 0
        before_count = len(files)
        files = [f for f in files if f.resolve() in git_changed]
        log.info("Git filter: %d of %d pattern-matched files are git-changed.",
                 len(files), before_count)

    if not files:
        log.warning("No matching files found.")
        return 0

    log.info("Found %d file(s) to process.", len(files))
    if args.dry_run:
        log.info("[DRY-RUN] No files will be modified.\n")

    # Process files
    modified = 0
    skipped = 0
    errors = 0
    for f in files:
        log.debug("Processing %s", f)
        try:
            would_change = replace_second_line(
                f, line,
                backup=args.backup,
                encoding=args.encoding,
                skip_if_present=args.skip,
                dry_run=args.dry_run,
            )
        except Exception as e:
            log.error("Error processing %s: %s", f, e)
            errors += 1
            continue
        if would_change:
            modified += 1
            action = "(dry) modified" if args.dry_run else "modified"
            log.info("  %s: %s", f, action)
        else:
            skipped += 1
            log.debug("  %s: skipped (already present)", f)

    # Summary
    log.info("")
    log.info("Summary: %d modified, %d skipped, %d errors (out of %d files)",
             modified, skipped, errors, len(files))
    return 1 if errors > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
