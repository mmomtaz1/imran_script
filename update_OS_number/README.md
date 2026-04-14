# xlsx_diff_to_html

Small utility to diff two Excel files and produce an HTML report.

Usage:

```bash
python scripts/xlsx_diff_to_html.py old.xlsx new.xlsx -o diff.html -w 120
```

Options:
- `-o`, `--output`: output HTML path (default `xlsx_diff_report.html`)
- `-w`, `--width`: wrap width for long lines (default 120)
- `--sheet`: only diff a single sheet by name

Install dependencies:

```bash
python -m pip install -r scripts/requirements.txt
```
