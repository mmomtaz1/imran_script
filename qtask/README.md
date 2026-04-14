# qtask – Jira Task Viewer & Updater

Command-line tool to list, inspect, and update Jira tasks assigned to a user.

## Requirements

- Python 3.12+
- `pyyaml` (`pip install pyyaml`)
- Intel network access (uses internal `pdk_jira_utils` binaries)
- A valid `installations.json` for Jira authentication

## Usage

```bash
python qtask.py -u <jira_username>
python qtask.py -u <jira_username> -i <installations.json>
python qtask.py -u <jira_username> -v
python qtask.py -u <jira_username> -s "In Progress"
python qtask.py -u <jira_username> -p PDK80
```

### CLI Options

| Flag | Description |
|------|-------------|
| `-u USERNAME` | Jira username (or `All` for all assignees). Required unless set in config. |
| `-i FILE` | Path to `installations.json` for authentication. |
| `-p PROJECT` | Jira project key (default: `PDK80`). |
| `-s STATUS` | Filter by status, comma-separated (e.g. `"Open, In Progress"`). |
| `-c YAML` | Path to a custom `qtask_config.yaml`. |
| `-v` | Enable verbose/debug output. |

## Configuration

Defaults are loaded from `qtask_config.yaml` (searched next to the script, then CWD). CLI flags override config values.

```yaml
jira:
  user: "malmamu1"
  project: "PDK80"
  inst_file: "~/inst_json/installations.json"
  issue_type: "Task"

query:
  status: "Open, In Progress"

display:
  max_summary: 60

verbose: false
```

Set `status: ""` to list all issues regardless of status.

## Interactive Workflow

1. Run the script to see a numbered table of matching issues.
2. Enter an issue number to view its full detail (summary, status, description with formatted tables).
3. From the detail view:
   - **`m`** – Modify the issue status (available transitions depend on current state).
   - **`b`** – Back to the issue list.
   - **`q`** – Quit.

### Status Transitions

| Current Status | Available Transitions |
|---------------|----------------------|
| Open | In Progress |
| In Progress | Resolved:Resolution Provided |
| Closed / Resolved | No modification available |

## Examples

```bash
# List open & in-progress tasks for malmamu1
python qtask.py -u malmamu1

# List all tasks regardless of status
python qtask.py -u malmamu1 -s ""

# Verbose output with a different project
python qtask.py -u malmamu1 -p PDK78 -v

# Use a specific installations.json
python qtask.py -u malmamu1 -i /path/to/installations.json
```
