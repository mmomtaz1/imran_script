# 📋 qtask — Jira Task Manager for PDK Projects

> A powerful command-line tool to **list**, **inspect**, **update**, and **export** Jira tasks assigned to you (or any user) in PDK Jira projects — right from your terminal.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Requirements](#requirements)
- [Quick Start](#quick-start)
- [Commands](#commands)
  - [`list` — View your tasks](#list--view-your-tasks)
  - [`update` — Advance issue statuses](#update--advance-issue-statuses)
  - [`detail` — Inspect a single issue](#detail--inspect-a-single-issue)
- [CLI Reference](#cli-reference)
  - [Global Options](#global-options)
  - [`list` Options](#list-options)
  - [`update` Options](#update-options)
  - [`detail` Options](#detail-options)
- [Configuration](#configuration)
  - [Config File Location](#config-file-location)
  - [Full Config Example](#full-config-example)
  - [Config vs CLI Precedence](#config-vs-cli-precedence)
- [Output Formats](#output-formats)
  - [Table (default)](#table-default)
  - [CSV](#csv)
  - [JSON](#json)
- [Status Transitions](#status-transitions)
- [Caching](#caching)
- [Recipes & Examples](#recipes--examples)
- [Troubleshooting](#troubleshooting)
- [Architecture](#architecture)

---

## Overview

`qtask` wraps Intel's internal `pdk_jira_utils` binaries (`getJiraIssues`, `updateJiraState`) into a convenient CLI with:

- **Subcommand structure** — `list`, `update`, `detail`
- **Rich terminal output** — color-coded statuses, box-drawn tables, text wrapping
- **Multiple export formats** — table, CSV, JSON
- **YAML configuration** — set your defaults once, override with flags
- **Local caching** — avoid hammering Jira on repeated queries

The tool automatically detects your username from `$USER`, so no login is needed — just run and go.

---

## Features

| Feature | Description |
|---------|-------------|
| 🔍 **List tasks** | View your assigned Jira issues in a formatted table |
| 📊 **Export** | Output as table, CSV, or JSON; save to file with `-f` |
| 🔄 **Bulk update** | Advance all matching issues to their next workflow status |
| 📝 **Issue detail** | View full issue descriptions with formatted HTML tables |
| 🎨 **Color-coded** | Statuses are color-coded: 🔴 Open, 🟡 In Progress, 🔵 On Hold, 🟢 Resolved |
| ⚡ **Caching** | 60-second local cache to speed up repeated queries |
| ⚙️ **Configurable** | YAML config with CLI overrides |

---

## Requirements

- **Python 3.12+**
- **`pyyaml`** — `pip install pyyaml`
- **Intel network** — requires access to internal `pdk_jira_utils` binaries
- **`installations.json`** — valid Jira authentication file (set path in config or via `-i`)

---

## Quick Start

```bash
# 1. List your open & in-progress tasks (uses $USER automatically)
qtask list

# 2. See details of a specific issue
qtask detail PDK80-12345

# 3. Advance all your open issues to "In Progress"
qtask update --dry-run    # preview first
qtask update              # apply changes
```

> **Tip:** The `qtask` wrapper script uses the same Python interpreter, so you can use either `qtask list` or `python qtask.py list`.

---

## Commands

### `list` — View your tasks

Fetch and display all Jira issues matching your filters.

```bash
# Default: shows your Open & In Progress tasks in a table
qtask list

# Filter by status
qtask list --status "Open"
qtask list --status "In Progress, Open"

# Export as CSV
qtask list --output csv

# Export as JSON and save to file
qtask list --output json -f my_tasks.json

# Use a different project
qtask list --project PDK78

# Bypass cache for fresh data
qtask list --no-cache

# Verbose/debug mode
qtask list -v
```

**Sample table output:**

```
#   Key          Status       Summary
--  -----------  -----------  --------------------------------------------------------
1   PDK80-31930  In Progress  ad-1280.3-3.0.5 OS#2 vs OS#5 Via Updates
2   PDK80-31926  In Progress  ad-1280.3-3.0.5 OS#2 vs OS#5 Via Updates

Total: 2 issue(s)
```

> Statuses are color-coded in the terminal: **red** for Open/Reopened, **yellow** for In Progress/In Review, **cyan** for On Hold, **green** for Resolved/Closed.

---

### `update` — Advance issue statuses

Bulk-update all matching issues to their next workflow status.

```bash
# Preview what would change (safe — no modifications)
qtask update --dry-run

# Apply updates (prompts for confirmation)
qtask update

# Update issues in a specific project
qtask update --project PDK78

# Update only Open issues
qtask update --status "Open"

# Save the update log to a file
qtask update -f update_log.txt
```

**How transitions work:**

| Current Status | → Next Status |
|:---|:---|
| Open | In Progress |
| In Progress | Resolved:Resolution Provided |
| Closed / Resolved | *Skipped (already done)* |
| Any other | In Progress |

**Sample dry-run output:**

```
#   Key          Status       Summary
--  -----------  -----------  --------------------------------------------------------
1   PDK80-31930  In Progress  ad-1280.3-3.0.5 OS#2 vs OS#5 Via Updates
2   PDK80-31926  Open         ad-1280.3-3.0.5 OS#2 vs OS#5 Via Updates

Total: 2 issue(s)

2 issue(s) found.
  [1/2] PDK80-31930: In Progress → Resolved:Resolution Provided
  [DRY-RUN] Would update PDK80-31930 → 'Resolved:Resolution Provided' (transition: 'To resolved')
  [2/2] PDK80-31926: Open → In Progress
  [DRY-RUN] Would update PDK80-31926 → 'In Progress' (transition: 'Start Progress')

All updates are done! 2 would be updated, 0 skipped.
```

> **Safety:** Without `--dry-run`, the tool will prompt `Proceed to update all N issue(s)? [y/N]` before making any changes.

---

### `detail` — Inspect a single issue

View the full description of a Jira issue, including embedded HTML tables rendered in your terminal.

```bash
# View issue details
qtask detail PDK80-12345

# With verbose output
qtask detail PDK80-12345 -v

# Save detail to a file
qtask detail PDK80-12345 -f issue_detail.txt
```

**Sample output:**

```
======================================================================
Key          : PDK80-12345
Summary      : ad-1280.3-3.0.5 OS#2 vs OS#5 Via Updates
Status       : In Progress
Description  :
  ┌─────────────────┬─────────────────────────────────────────────────────────┬───────┐
  │ Label           │ Rule                                                    │ Diff  │
  ├─────────────────┼─────────────────────────────────────────────────────────┼───────┤
  │ VIA_ENCLOSURE   │ VIA must be enclosed by M2 by >= 0.05 um on all sides   │ NEW   │
  ├─────────────────┼─────────────────────────────────────────────────────────┼───────┤
  │ VIA_SPACING     │ Minimum spacing between VIA shapes >= 0.10 um           │ MOD   │
  └─────────────────┴─────────────────────────────────────────────────────────┴───────┘
======================================================================
```

> The description renderer handles both HTML tables and Jira wiki markup, strips color macros, and formats everything with box-drawing characters.

---

## CLI Reference

### Global Options

These options are shared across `list`, `update`, and `detail`:

| Flag | Long Form | Description |
|:-----|:----------|:------------|
| `-i` | `--inst-file FILE` | Path to `installations.json` for Jira authentication |
| `-p` | `--project PROJECT` | Jira project key (default: `PDK80`) |
| `-s` | `--status STATUS` | Filter by status — comma-separated (e.g. `"Open, In Progress"`) |
| `-c` | `--config YAML` | Path to a custom `qtask_config.yaml` |
| `-f` | `--output-file FILE` | Redirect all output to a file (disables colors) |
| `-v` | | Enable verbose/debug output |

### `list` Options

| Flag | Long Form | Description |
|:-----|:----------|:------------|
| `-o` | `--output FORMAT` | Output format: `table` (default), `csv`, `json` |
| | `--no-cache` | Bypass local cache and fetch fresh data |

### `update` Options

| Flag | Long Form | Description |
|:-----|:----------|:------------|
| | `--dry-run` | Preview changes without applying them |

### `detail` Options

| Argument | Description |
|:---------|:------------|
| `ISSUE_KEY` | Jira issue key (e.g. `PDK80-12345`). **Required.** |

---

## Configuration

### Config File Location

`qtask` searches for `qtask_config.yaml` in this order:

1. Path passed via `-c` / `--config`
2. Same directory as `qtask.py`
3. Current working directory

### Full Config Example

```yaml
# qtask_config.yaml
jira:
  user: "mmomtaz"            # Your Jira username (overridden by $USER at runtime)
  project: "PDK80"           # Default Jira project key
  inst_file: "~/bin/installations.json"  # Path to authentication file
  issue_type: "Task"         # Jira issue type filter

query:
  # Comma-separated status filter. Leave empty ("") for all statuses.
  status: "Open, In Progress"

display:
  max_summary: 60            # Truncate summary column to this width

verbose: false               # Set to true for debug output
```

### Config vs CLI Precedence

CLI flags **always override** config file values:

```bash
# Config says project=PDK80, but this overrides to PDK78
qtask list --project PDK78

# Config says status="Open, In Progress", but this shows only Open
qtask list --status "Open"

# Config says verbose=false, but -v enables it
qtask list -v
```

---

## Output Formats

### Table (default)

Human-readable formatted table with aligned columns and color-coded statuses:

```bash
qtask list
qtask list --output table   # explicit
```

```
#   Key          Status       Summary
--  -----------  -----------  --------------------------------------------------------
1   PDK80-31930  In Progress  ad-1280.3-3.0.5 OS#2 vs OS#5 Via Updates
2   PDK80-31926  In Progress  ad-1280.3-3.0.5 OS#2 vs OS#5 Via Updates

Total: 2 issue(s)
```

### CSV

Machine-readable CSV, also printed to stdout and saved to a file:

```bash
qtask list --output csv
qtask list -o csv -f tasks.csv    # save to specific file
```

```csv
Key,Status,Summary
PDK80-31930,In Progress,ad-1280.3-3.0.5 OS#2 vs OS#5 Via Updates
PDK80-31926,In Progress,ad-1280.3-3.0.5 OS#2 vs OS#5 Via Updates
```

### JSON

Structured JSON array, ideal for piping to `jq` or downstream scripts:

```bash
qtask list --output json
qtask list -o json -f tasks.json  # save to specific file
```

```json
[
  {
    "key": "PDK80-31930",
    "status": "In Progress",
    "summary": "ad-1280.3-3.0.5 OS#2 vs OS#5 Via Updates"
  },
  {
    "key": "PDK80-31926",
    "status": "In Progress",
    "summary": "ad-1280.3-3.0.5 OS#2 vs OS#5 Via Updates"
  }
]
```

---

## Status Transitions

`qtask update` moves issues through the Jira workflow automatically. The full transition map:

| Target Status | Jira Transition Name |
|:---|:---|
| In Progress | `Start Progress` |
| In Review | `Start Review` |
| Resolved:Resolution Provided | `To resolved` |
| Closed | `To close directly` |
| On Hold | `to on hold` |
| Reopened | `Reopen Issue` |
| Open | `Reopen Issue` |

**Automatic progression used by `update`:**

```
Open  ──►  In Progress  ──►  Resolved:Resolution Provided
                                        │
                              Closed / Resolved = skipped
```

---

## Caching

To avoid excessive Jira API calls, `qtask` caches query results locally:

| Setting | Value |
|:--------|:------|
| **TTL** | 60 seconds |
| **Location** | `$TMPDIR` (falls back to `/tmp`) |
| **File pattern** | `qtask_cache_<USER>_<hash>.json` |
| **Scope** | Per-user, per-query (JQL + fields hash) |

```bash
# Force a fresh fetch (bypasses cache)
qtask list --no-cache

# The update command always bypasses cache automatically
qtask update
```

> Cache files are automatically stale after 60 seconds. No manual cleanup needed.

---

## Recipes & Examples

### Daily workflow

```bash
# Morning: check what's on your plate
qtask list

# Work through issues, then resolve them
qtask update --dry-run          # preview
qtask update                    # apply

# Check a specific issue's details
qtask detail PDK80-12345
```

### Export for reporting

```bash
# CSV for spreadsheets
qtask list -o csv -f weekly_report.csv

# JSON for scripts or dashboards
qtask list -o json -f tasks.json

# Pipe JSON to jq for custom filtering
qtask list -o json | jq '.[] | select(.status == "Open") | .key'
```

### Cross-project queries

```bash
# Check tasks in PDK78
qtask list --project PDK78

# Check tasks in PDK80 with all statuses
qtask list --status ""
```

### Filtering by status

```bash
# Only Open issues
qtask list --status "Open"

# Multiple statuses
qtask list --status "Open, In Progress, On Hold"

# All statuses (empty string)
qtask list --status ""
```

### Using a custom config

```bash
# Point to a different config file
qtask list --config /path/to/my_config.yaml

# Override auth file
qtask list --inst-file /path/to/installations.json
```

### Saving output to files

```bash
# Table output to file (colors are automatically disabled)
qtask list -f tasks.txt

# Detail view to file
qtask detail PDK80-12345 -f issue.txt

# Update log to file
qtask update -f update_log.txt
```

---

## Troubleshooting

| Problem | Solution |
|:--------|:---------|
| `No data returned from Jira` | Check network connectivity and `installations.json` path |
| `Error parsing Jira response` | Run with `-v` to see raw response; check if Jira is reachable |
| `No issues found` | Verify your `$USER` matches your Jira username; try `--status ""` to list all |
| `No known transition for status` | The target status is not in the transition map — check the status name exactly |
| Stale results | Use `--no-cache` to bypass the 60s cache |
| Colors not showing | Ensure your terminal supports ANSI codes; colors are disabled when piping or writing to file |
| Config not loading | Run with `-v` and check that `qtask_config.yaml` exists next to the script or in CWD |

---

## Architecture

```
qtask/
├── qtask              # Wrapper script (#!/usr/intel/bin/python3.12)
├── qtask.py           # Main source — CLI, commands, rendering
├── qtask_config.yaml  # Default configuration (YAML)
├── qtask_output.csv   # Sample CSV export
├── qtask_output.json  # Sample JSON export
└── README.md          # This file
```

**Key components in `qtask.py`:**

| Component | Purpose |
|:----------|:--------|
| `main()` | Argument parsing with subcommands (`list`, `update`, `detail`) |
| `cmd_list()` | Fetch & display issues in table/CSV/JSON format |
| `cmd_update()` | Bulk-update issues to next workflow status |
| `cmd_detail()` | Show full issue detail with formatted description |
| `fetch_issues()` | Execute `getJiraIssues`, parse JSON, manage cache |
| `update_status()` | Execute `updateJiraState` with transition mapping |
| `render_description()` | Parse HTML/wiki markup and render terminal-friendly tables |
| `_TableParser` | HTML table parser (extends `HTMLParser`) |
| `_print_boxed_table()` | Box-drawing table renderer with text wrapping |
| `build_jql()` | Construct JQL query strings from parameters |
| `load_config()` | YAML config loader with search path logic |
| `_Color` / `colorize_status()` | ANSI color helpers with TTY detection |

---

*Author: Md Imran Momtaz (initial work by Mohammad Al-Mamun) — April 2026*
