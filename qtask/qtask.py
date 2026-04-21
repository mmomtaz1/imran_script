#!/p/foundry/env/ezb/ez/25ww39.1/python/3.11.1/bin/python3

"""
qtask.py - List Jira Tasks

Author: Md Imran Momtaz (borrowed initial work from Mohammad Al-Mamun)
Date: 04/06/2026

DESCRIPTION:
    Command-line tool to list all tasks assigned to the current user
    in the PDK80 Jira project, displayed as a formatted table.
    The username is automatically determined from $USER.

USAGE:
    python qtask.py list
    python qtask.py list --status Open
    python qtask.py list --output json
    python qtask.py update
    python qtask.py update --dry-run
    python qtask.py detail <ISSUE_KEY>

EXAMPLES:
    # List all your open tasks
    python qtask.py list

    # List tasks with a specific status, output as CSV
    python qtask.py list --status "In Progress" --output csv

    # Preview status updates without applying them
    python qtask.py update --dry-run

    # Actually update all issues to their next status
    python qtask.py update

    # View detailed description of a single issue
    python qtask.py detail PDK80-123

    # Verbose output with custom project
    python qtask.py list --project PDK78 -v
"""

import csv
import getpass
import hashlib
import io
import json
import os
import argparse
import re
import subprocess
import sys
import textwrap
import time
import yaml
from html.parser import HTMLParser
from pathlib import Path
sys.path.append("/p/fdk/drwork/python_pkgs/lib/python3.11/site-packages")
sys.path.append("/p/fdk/drwork/python_pkgs/lib/python3.7/site-packages")

get_issues_cmd = '/p/foundry/env/proj_tools/pdk_jira_utils/current/bin/getJiraIssues '
edit_issue_cmd = '/p/foundry/env/proj_tools/pdk_jira_utils/current/bin/updateJiraState '

debug_mode = False
inst_file = None

CACHE_TTL = 60  # seconds
CACHE_DIR = Path(os.environ.get('TMPDIR', '/tmp'))


def _cache_path(jql, fields):
    """Return a per-user cache file path based on the query hash."""
    user = os.environ.get('USER', 'unknown')
    key = hashlib.md5(f"{jql}|{fields}".encode()).hexdigest()[:12]
    return CACHE_DIR / f"qtask_cache_{user}_{key}.json"


def _read_cache(jql, fields):
    """Return cached issues dict if cache exists and is fresh, else None."""
    cp = _cache_path(jql, fields)
    if not cp.exists():
        return None
    age = time.time() - cp.stat().st_mtime
    if age > CACHE_TTL:
        return None
    try:
        with open(cp, 'r') as f:
            data = json.load(f)
        if debug_mode:
            print(f"[DEBUG] Cache hit ({age:.0f}s old): {cp}")
        return data
    except Exception:
        return None


def _write_cache(jql, fields, data):
    """Write issues dict to cache file."""
    cp = _cache_path(jql, fields)
    try:
        with open(cp, 'w') as f:
            json.dump(data, f)
    except Exception:
        pass  # cache write failure is non-fatal


# --- ANSI color helpers (#7) ---
class _Color:
    """ANSI color codes for terminal output. Disabled when not a TTY."""
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    CYAN = '\033[36m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

    @classmethod
    def disable(cls):
        cls.RED = cls.GREEN = cls.YELLOW = cls.CYAN = cls.BOLD = cls.RESET = ''


if not sys.stdout.isatty():
    _Color.disable()


STATUS_COLORS = {
    'Open': _Color.RED,
    'Reopened': _Color.RED,
    'In Progress': _Color.YELLOW,
    'In Review': _Color.YELLOW,
    'On Hold': _Color.CYAN,
    'Resolved': _Color.GREEN,
    'Resolved:Resolution Provided': _Color.GREEN,
    'Closed': _Color.GREEN,
}


def colorize_status(status_text):
    """Return status text wrapped in its ANSI color."""
    color = STATUS_COLORS.get(status_text, '')
    if color:
        return f"{color}{status_text}{_Color.RESET}"
    return status_text


def load_config(config_path=None):
    """Load YAML config. Searches script dir then CWD if no path given."""
    if config_path and os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return yaml.safe_load(f) or {}

    # Default search: next to this script, then CWD
    script_dir = Path(__file__).resolve().parent
    for candidate in [script_dir / 'qtask_config.yaml', Path('qtask_config.yaml')]:
        if candidate.exists():
            with open(str(candidate), 'r') as f:
                return yaml.safe_load(f) or {}
    return {}


def build_jql(user, project, status=None, issue_type='Task'):
    """Build JQL query string from parameters."""
    parts = [f'"project={project}']
    if issue_type:
        parts.append(f'issuetype={issue_type}')
    if user != 'All':
        parts.append(f'Assignee={user}')
    if status:
        # Support multiple statuses: "Open, In Progress" → status in (Open, 'In Progress')
        # Use single quotes inside since the whole JQL is wrapped in double quotes for shell
        status_list = [s.strip() for s in status.split(',')]
        quoted = ', '.join(f"'{s}'" if ' ' in s else s for s in status_list)
        parts.append(f'status in ({quoted})"')
    #return '"' + ' AND '.join(parts) + '" '
    return ' AND '.join(parts) 


def fetch_issues(jql, fields, use_cache=True):
    """Execute getJiraIssues and return parsed JSON dict.
    Results are cached for CACHE_TTL seconds unless use_cache=False.
    """
    global debug_mode, inst_file

    if use_cache:
        cached = _read_cache(jql, fields)
        if cached is not None:
            return cached

    cmd_parts = [get_issues_cmd.strip()]
    if inst_file:
        cmd_parts.extend(['-inst_file', inst_file])
    cmd_parts.append(jql.strip())
    fields = '-fields "Summary, Status, Description" '
    cmd_parts.append(fields)

    if debug_mode:
        print(f"[DEBUG] fetch_issues: {' '.join(cmd_parts)}")

    try:
        result = subprocess.run(' '.join(cmd_parts), shell=True, capture_output=True, text=True)
        raw = result.stdout
    except Exception as e:
        print(f"Error running getJiraIssues: {e}")
        return {}

    if not raw.strip():
        print("No data returned from Jira. Check credentials or query.")
        return {}

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Error parsing Jira response: {e}")
        if debug_mode:
            print(f"[DEBUG] Raw response:\n{raw[:500]}")
        return {}

    if data and use_cache:
        _write_cache(jql, fields, data)
    return data


TRANSITION_MAP = {
    'In Progress': 'Start Progress',
    'In Review':   'Start Review',
    'Resolved:Resolution Provided':    'To resolved',
    'Closed':      'To close directly',
    'On Hold':     'to on hold',
    'Reopened':    'Reopen Issue',
    'Open':        'Reopen Issue',
}


def update_status(issue_key, new_status, dry_run=False):
    """Update the status of a Jira issue via updateJiraState -trans."""
    global debug_mode, inst_file

    transition = TRANSITION_MAP.get(new_status)
    if not transition:
        print(f"No known transition for status '{new_status}'.")
        return False

    cmd_parts = [edit_issue_cmd.strip(), issue_key, '-trans', '"'+transition+'"' , '"'+new_status+'"']
    if inst_file:
        cmd_parts.extend(['-inst_file', inst_file])

    if debug_mode:
        print(f"[DEBUG] update_status: {' '.join(cmd_parts)}")

    if dry_run:
        print(f"[DRY-RUN] Would update {issue_key} → '{new_status}' (transition: '{transition}')")
        return True

    try:
        result = subprocess.run(' '.join(cmd_parts), shell=True, capture_output=True, text=True)

        if result.returncode == 0:
            print(f"Successfully updated {issue_key} status to '{new_status}'")
            return True
        else:
            print(f"Failed to update {issue_key}: {result.stderr or result.stdout}")
            return False
    except Exception as e:
        print(f"Error updating {issue_key}: {e}")
        return False


def safe_field(issue, field_name):
    """Extract a display-friendly value from an issue field."""
    val = issue.get(field_name, '')
    if isinstance(val, dict):
        return val.get('name', str(val))
    if isinstance(val, list):
        return ', '.join(str(v) for v in val)
    if val is None:
        return ''
    return str(val)


def print_table(issues, max_summary=60, output_format='table', output_file=None):
    """Print issues as a numbered, aligned table. Returns ordered list of keys.
    For csv/json formats, writes to output_file (or a default filename) automatically.
    """
    if not issues:
        print("No issues found.")
        return []

    keys_ordered = list(issues.keys())

    # --- JSON output ---
    if output_format == 'json':
        out = []
        for key in keys_ordered:
            issue = issues[key]
            out.append({
                'key': key,
                'status': safe_field(issue, 'Status'),
                'summary': safe_field(issue, 'Summary'),
            })
        json_text = json.dumps(out, indent=2)
        dump_path = output_file or 'qtask_output.json'
        with open(dump_path, 'w', encoding='utf-8') as f:
            f.write(json_text + '\n')
        print(f"Exported {len(keys_ordered)} issue(s) to {dump_path}")
        return keys_ordered

    # --- CSV output ---
    if output_format == 'csv':
        dump_path = output_file or 'qtask_output.csv'
        with open(dump_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Key', 'Status', 'Summary'])
            for key in keys_ordered:
                issue = issues[key]
                writer.writerow([key, safe_field(issue, 'Status'), safe_field(issue, 'Summary')])
        print(f"Exported {len(keys_ordered)} issue(s) to {dump_path}")
        return keys_ordered

    # --- Default table output ---
    headers = ['#', 'Key', 'Status', 'Summary']

    rows = []
    for idx, key in enumerate(keys_ordered, 1):
        issue = issues[key]
        rows.append([str(idx), key, safe_field(issue, 'Status'), safe_field(issue, 'Summary')])

    # Truncate long summaries for readability
    for row in rows:
        if len(row[3]) > max_summary:
            row[3] = row[3][:max_summary - 3] + '...'

    # Calculate column widths (based on raw text, before color codes)
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(val))

    # Print header
    header_line = '  '.join(f"{_Color.BOLD}{h.ljust(col_widths[i])}{_Color.RESET}" for i, h in enumerate(headers))
    separator = '  '.join('-' * col_widths[i] for i in range(len(headers)))
    print(header_line)
    print(separator)

    # Print rows with color-coded status (#7)
    for row in rows:
        colored_row = list(row)
        colored_status = colorize_status(row[2])
        parts = []
        for i, val in enumerate(colored_row):
            if i == 2:  # Status column
                parts.append(colored_status + ' ' * (col_widths[i] - len(row[2])))
            else:
                parts.append(val.ljust(col_widths[i]))
        print('  '.join(parts))

    print(f"\nTotal: {len(rows)} issue(s)")
    return keys_ordered


class _TableParser(HTMLParser):
    """Parse HTML tables into list-of-lists and capture non-table text."""

    def __init__(self):
        super().__init__()
        self.tables = []      # list of tables, each table = list of rows
        self._cur_table = None
        self._cur_row = None
        self._cur_cell = None
        self._is_header = False
        self._segments = []   # ordered mix of ('text', str) and ('table', [[...]])
        self._text_buf = ''

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == 'table':
            if self._text_buf.strip():
                self._segments.append(('text', self._text_buf))
            self._text_buf = ''
            self._cur_table = []
        elif tag == 'tr' and self._cur_table is not None:
            self._cur_row = []
            self._is_header = False
        elif tag in ('td', 'th') and self._cur_row is not None:
            self._cur_cell = ''
            if tag == 'th':
                self._is_header = True
        elif tag == 'br':
            if self._cur_cell is not None:
                self._cur_cell += ' '
            else:
                self._text_buf += '\n'

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ('td', 'th') and self._cur_cell is not None:
            self._cur_row.append(self._cur_cell.strip())
            self._cur_cell = None
        elif tag == 'tr' and self._cur_row is not None:
            self._cur_table.append((self._is_header, self._cur_row))
            self._cur_row = None
        elif tag == 'table' and self._cur_table is not None:
            self._segments.append(('table', self._cur_table))
            self._cur_table = None

    def handle_data(self, data):
        if self._cur_cell is not None:
            self._cur_cell += data
        else:
            self._text_buf += data

    def get_segments(self):
        if self._text_buf.strip():
            self._segments.append(('text', self._text_buf))
        return self._segments


def strip_jira_markup(text):
    """Remove Jira wiki markup formatting from text."""
    # Remove {color:...}...{color} wrappers, keeping inner text
    text = re.sub(r'\{color(?::[^}]*)?\}', '', text)
    # Remove bold markup {*} or *...*
    text = re.sub(r'\{\*\}', '', text)
    # Remove monospace {{ }} wrappers, keeping inner text
    text = text.replace('{{', '').replace('}}', '')
    # Remove emoticon macros like (!) (?) (x) (/) (i)
    text = re.sub(r'\(([!?x/i])\)', r'\1', text)
    return text


def apply_strikethrough(text):
    """Convert Jira strikethrough -text- to ANSI strikethrough.
    Matches leading -...- blocks (old/deleted text in Jira diffs)."""
    return re.sub(r'(?<!\w)-([^-\n]{2,})-(?!\w)', r'\033[9m\1\033[0m', text)


def render_description(raw):
    """Render Jira description with HTML tables formatted for terminal."""
    if not raw:
        print('  (no description)')
        return

    raw = str(raw)
    raw = strip_jira_markup(raw)

    # Columns to show from description tables
    show_columns = ['Label', 'Rule', 'Diff_Status']
    # Fixed column widths: Label=15, Rule=55, Diff_Status=5
    col_max_widths = [15, 55, 5]

    # Check if description contains HTML tags
    if not re.search(r'<\s*(table|tr|td|th|p|br|div)\b', raw, re.IGNORECASE):
        # Plain text – join continuation lines, then split by | for columns
        lines = raw.replace('\r\n', '\n').split('\n')

        # Join continuation lines: if a line doesn't start with | or ||,
        # append it to the previous line (it's part of the same table row)
        merged = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('|') or stripped.startswith('||'):
                merged.append(stripped)
            elif merged and ('|' in merged[-1]):
                # Continuation of previous table row
                merged[-1] = merged[-1] + ' ' + stripped
            else:
                merged.append(stripped)

        table_rows = []
        text_lines = []
        for line in merged:
            if '|' in line:
                # Split by | and filter out empty segments
                parts = [p.strip() for p in line.split('|') if p.strip()]
                if len(parts) >= 3:
                    label = parts[0]
                    rule = parts[1]
                    diff_status = parts[2]
                    is_hdr = label in show_columns
                    table_rows.append((is_hdr, [label, rule, diff_status]))
                elif len(parts) == 2:
                    label = parts[0]
                    rule = parts[1]
                    is_hdr = label in show_columns
                    table_rows.append((is_hdr, [label, rule, '']))
                elif len(parts) == 1:
                    text_lines.append(line)
            else:
                text_lines.append(line)

        # Print non-table text
        for tl in text_lines:
            if tl:
                print(f"  {tl}")

        # Print collected table rows
        if table_rows:
            _print_boxed_table(table_rows, col_max_widths)
        return

    parser = _TableParser()
    parser.feed(raw)
    segments = parser.get_segments()

    for kind, content in segments:
        if kind == 'text':
            for line in content.split('\n'):
                stripped = line.strip()
                if stripped:
                    print(f"  {stripped}")
        elif kind == 'table':
            rows = content  # list of (is_header, [cells])
            if not rows:
                continue
            # Filter columns if header row present
            col_indices = None
            for is_hdr, cells in rows:
                if is_hdr:
                    col_indices = [i for i, c in enumerate(cells) if c in show_columns]
                    break
            if not col_indices:
                col_indices = list(range(min(len(show_columns), max(len(r[1]) for r in rows))))
            filtered = []
            for is_hdr, cells in rows:
                filtered.append((is_hdr, [cells[i] if i < len(cells) else '' for i in col_indices]))
            _print_boxed_table(filtered, col_max_widths)


def _wrap_cells(cells, col_widths):
    """Wrap each cell's text to its column width and return list of line-lists."""
    wrapped = []
    for i, text in enumerate(cells):
        w = col_widths[i] if i < len(col_widths) else 20
        wrapped.append(textwrap.wrap(text, width=w) or [''])
    return wrapped


def _print_boxed_table(rows, col_max_widths):
    """Print rows with box-drawing borders and text wrapping."""
    num_cols = len(col_max_widths)

    def h_line(left, mid, right, fill='─'):
        parts = [fill * (w + 2) for w in col_max_widths]
        return '  ' + left + mid.join(parts) + right

    top    = h_line('┌', '┬', '┐')
    mid    = h_line('├', '┼', '┤')
    bottom = h_line('└', '┴', '┘')

    print(top)
    for row_idx, (is_hdr, cells) in enumerate(rows):
        # Pad cells list to num_cols
        while len(cells) < num_cols:
            cells.append('')
        wrapped = _wrap_cells(cells, col_max_widths)
        max_lines = max(len(w) for w in wrapped)
        for line_idx in range(max_lines):
            parts = []
            for col_idx in range(num_cols):
                w = col_max_widths[col_idx]
                text = wrapped[col_idx][line_idx] if line_idx < len(wrapped[col_idx]) else ''
                padded = text.ljust(w)
                # Apply strikethrough after padding so ANSI codes don't break alignment
                padded = apply_strikethrough(padded)
                parts.append(f' {padded} ')
            print('  │' + '│'.join(parts) + '│')
        # Print separator after header or between rows
        if row_idx < len(rows) - 1:
            print(mid)
    print(bottom)


def print_detail(issue_key, issue):
    """Print detailed description of a single issue."""
    fields = [
        ('Key', issue_key),
        ('Summary', safe_field(issue, 'Summary')),
        ('Status', safe_field(issue, 'Status')),
    ]

    label_width = max(len(f[0]) for f in fields + [('Description', '')])
    print()
    print('=' * 70)
    for label, value in fields:
        print(f"{label.ljust(label_width)}  : {value}")
    print(f"{'Description'.ljust(label_width)}  : ")
    render_description(issue.get('Description', ''))
    print('=' * 70)


def _add_common_args(sub):
    """Add arguments shared by list and update subcommands."""
    sub.add_argument('-i', '--inst-file', metavar='FILE',
                     help='Path to installations.json for authentication')
    sub.add_argument('-p', '--project', metavar='PROJECT',
                     help='Jira project key (default from config: PDK80)')
    sub.add_argument('-s', '--status', metavar='STATUS',
                     help='Filter by status (e.g. Open, "In Progress", Closed)')
    sub.add_argument('-c', '--config', metavar='YAML',
                     help='Path to qtask_config.yaml')
    sub.add_argument('-f', '--output-file', metavar='FILE',
                     help='Write output to FILE instead of stdout')
    sub.add_argument('-v', action='store_true',
                     help='Verbose / debug output')


def _resolve_common(args):
    """Resolve config + CLI overrides and return (cfg, user, project, status, issue_type, max_summary)."""
    global debug_mode, inst_file

    cfg = load_config(getattr(args, 'config', None))
    jira_cfg = cfg.get('jira', {})
    query_cfg = cfg.get('query', {})
    display_cfg = cfg.get('display', {})

    debug_mode = getattr(args, 'v', False) or cfg.get('verbose', False)
    inst_file = getattr(args, 'inst_file', None) or jira_cfg.get('inst_file', '') or None
    project = getattr(args, 'project', None) or jira_cfg.get('project', 'PDK80')
    user = os.environ.get('USER') or getpass.getuser()
    status = getattr(args, 'status', None) or query_cfg.get('status', '') or None
    issue_type = jira_cfg.get('issue_type', 'Task')
    max_summary = display_cfg.get('max_summary', 60)

    return cfg, user, project, status, issue_type, max_summary


def cmd_list(args):
    """Handler for 'list' subcommand."""
    cfg, user, project, status, issue_type, max_summary = _resolve_common(args)
    use_cache = not getattr(args, 'no_cache', False)

    if debug_mode:
        print(f"[DEBUG] User: {user}, Project: {project}, Status: {status}")
        print(f"[DEBUG] Issue type: {issue_type}, Config: {cfg}")

    jql = build_jql(user, project, status, issue_type)
    fields = '-fields "Summary, Status, Description" '
    issues = fetch_issues(jql, fields, use_cache=use_cache)
    print_table(issues, max_summary, output_format=args.output)


def cmd_update(args):
    """Handler for 'update' subcommand — update all matching issues to their next status."""
    cfg, user, project, status, issue_type, max_summary = _resolve_common(args)
    dry_run = args.dry_run

    if debug_mode:
        print(f"[DEBUG] User: {user}, Project: {project}, Status: {status}, Dry-run: {dry_run}")

    total_modified = 0
    total_skipped = 0
    confirmed = False

    for pass_idx in range(1, 3):
        print(f"\n=== Update pass {pass_idx}/2 ===")

        jql = build_jql(user, project, status, issue_type)
        fields = '-fields "Summary, Status, Description" '

        # Always bypass cache for update — need fresh data
        issues = fetch_issues(jql, fields, use_cache=False)
        keys_ordered = print_table(issues, max_summary, output_format=args.output)

        if not keys_ordered:
            print("No issues found for this pass.")
            continue

        issue_count = len(keys_ordered)
        print(f"\n{issue_count} issue(s) found.")

        # Ask for confirmation once before first real update pass.
        if not dry_run and not confirmed:
            answer = input(f"Proceed to update all {issue_count} issue(s)? [y/N] ").strip().lower()
            if answer not in ('y', 'yes'):
                print("Aborted.")
                return
            confirmed = True

        modified = 0
        skipped = 0
        for idx, issue_key in enumerate(keys_ordered, 1):
            current_status = safe_field(issues[issue_key], 'Status')
            progress = f"[{idx}/{issue_count}]"

            # (#3) Fixed: continue instead of break so remaining issues are still processed
            if current_status in ('Closed', 'Resolved', 'Resolved:Resolution Provided'):
                print(f"  {progress} {issue_key}: already {current_status} — skipped")
                skipped += 1
                continue

            if current_status == 'Open':
                next_status = 'In Progress'
            elif current_status == 'In Progress':
                next_status = 'Resolved:Resolution Provided'
            else:
                next_status = 'In Progress'

            print(f"  {progress} {issue_key}: {colorize_status(current_status)} → {colorize_status(next_status)}")

            try:
                if update_status(issue_key, next_status, dry_run=dry_run):
                    modified += 1
            except Exception as e:
                print(f"  {progress} Error updating {issue_key}: {e}")

        total_modified += modified
        total_skipped += skipped

        action = "would be updated" if dry_run else "updated"
        print(f"Pass {pass_idx} complete: {modified} {action}, {skipped} skipped.")

    action = "would be updated" if dry_run else "updated"
    print(f"\nAll updates are done! {total_modified} {action}, {total_skipped} skipped.")


def cmd_detail(args):
    """Handler for 'detail' subcommand — show full description of a single issue."""
    global debug_mode, inst_file

    cfg = load_config(getattr(args, 'config', None))
    jira_cfg = cfg.get('jira', {})
    debug_mode = getattr(args, 'v', False) or cfg.get('verbose', False)
    inst_file = getattr(args, 'inst_file', None) or jira_cfg.get('inst_file', '') or None

    issue_key = args.issue_key
    project = issue_key.split('-')[0] if '-' in issue_key else jira_cfg.get('project', 'PDK80')

    jql = f'"key={issue_key}" '
    fields = '-fields "Summary, Status, Description" '
    issues = fetch_issues(jql, fields)

    if issue_key not in issues:
        print(f"Issue {issue_key} not found.")
        return

    # (#11) Show full detail including description
    print_detail(issue_key, issues[issue_key])


# (#12) Epilog examples shown in --help
_EPILOG = """\
examples:
  %(prog)s list                          List your tasks (uses $USER)
  %(prog)s list --output csv             Export as CSV
  %(prog)s list --status "In Progress"   Filter by status
  %(prog)s list -f tasks.txt             Save task list to a file
  %(prog)s list -o csv -f tasks.csv      Export CSV to a file
  %(prog)s update --dry-run              Preview changes without applying
  %(prog)s update                        Update all issues to next status
  %(prog)s update -f update_log.txt      Save update log to a file
  %(prog)s detail PDK80-123              Show full issue description
  %(prog)s detail PDK80-123 -f out.txt   Save issue detail to a file
"""


def main():
    # (#4) Subcommand structure
    parser = argparse.ArgumentParser(
        description='Jira task manager for PDK projects.',
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # --- list ---
    sp_list = subparsers.add_parser('list', help='List Jira tasks',
                                    formatter_class=argparse.RawDescriptionHelpFormatter)
    _add_common_args(sp_list)
    sp_list.add_argument('-o', '--output', choices=['table', 'json', 'csv'], default='table',
                         help='Output format (default: table)')
    sp_list.add_argument('--no-cache', action='store_true',
                         help='Bypass cache and fetch fresh data from Jira')
    sp_list.set_defaults(func=cmd_list)

    # --- update ---
    sp_update = subparsers.add_parser('update', help='Update all issues to their next status',
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    _add_common_args(sp_update)
    sp_update.add_argument('--dry-run', action='store_true',
                           help='Show what would be changed without applying')
    sp_update.add_argument('-o', '--output', choices=['table', 'json', 'csv'], default='table',
                         help='Output format (default: table)')
    sp_update.set_defaults(func=cmd_update)

    # --- detail ---
    sp_detail = subparsers.add_parser('detail', help='Show full details of a single issue',
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    sp_detail.add_argument('issue_key', metavar='ISSUE_KEY',
                           help='Jira issue key (e.g. PDK80-123)')
    sp_detail.add_argument('-i', '--inst-file', metavar='FILE',
                           help='Path to installations.json')
    sp_detail.add_argument('-f', '--output-file', metavar='FILE',
                           help='Write output to FILE instead of stdout')
    sp_detail.add_argument('-c', '--config', metavar='YAML',
                           help='Path to qtask_config.yaml')
    sp_detail.add_argument('-v', action='store_true', help='Verbose output')
    sp_detail.set_defaults(func=cmd_detail)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Redirect stdout to file if --output-file is specified
    output_file_path = getattr(args, 'output_file', None)
    original_stdout = sys.stdout
    outfile = None
    try:
        if output_file_path:
            outfile = open(output_file_path, 'w', encoding='utf-8')
            sys.stdout = outfile
            # Disable colors when writing to file
            _Color.disable()

        args.func(args)
    finally:
        sys.stdout = original_stdout
        if outfile:
            outfile.close()
            print(f"Output written to {output_file_path}")


if __name__ == '__main__':
    main()
