#!/p/foundry/env/ezb/ez/23ww45.3/python/3.9.13/bin/python3
"""xlsx_diff_to_html.py

Read two .xlsx files, compute a line-wrapped diff per sheet, and produce an
HTML report with side-by-side diffs.

Usage:
  python scripts/xlsx_diff_to_html.py old.xlsx new.xlsx -o diff.html -w 120

Dependencies: pandas, openpyxl
"""
import argparse
import difflib
from difflib import SequenceMatcher
import html
import re
from itertools import zip_longest
import os
import textwrap
from typing import List
import sys
sys.path.append("/p/fdk/drwork/python_pkgs/lib/python3.11/site-packages")
sys.path.append("/p/fdk/drwork/python_pkgs/lib/python3.7/site-packages")
import pandas as pd


def df_to_lines(df: pd.DataFrame) -> List[str]:
    if df is None or df.empty:
        return [""]
    df2 = df.copy()
    df2 = df2.fillna("")
    # Keep index as a column for stable representation
    df2.insert(0, "__index__", df2.index)
    # Use a stable column order
    cols = list(df2.columns)
    # Convert all values to strings
    rows = []
    header = ",".join(map(str, cols))
    rows.append(header)
    for _, r in df2[cols].iterrows():
        # Join by comma to form a CSV-like line
        row = ",".join(map(lambda x: str(x), r.tolist()))
        rows.append(row)
    return rows


def wrap_lines(lines: List[str], width: int) -> List[str]:
    out = []
    for ln in lines:
        if ln == "":
            out.append("")
            continue
        wrapped = textwrap.wrap(ln, width=width, break_long_words=True, replace_whitespace=False)
        if not wrapped:
            out.append("")
        else:
            # Mark continuation lines for readability
            out.extend(wrapped)
    return out


def _tokenize_keep_spaces(s: str) -> List[str]:
    # Tokenize into words, whitespace, and punctuation so we can diff words while preserving spacing
    return re.findall(r"\w+|\s+|[^\w\s]+", s)


def _highlight_word_diff(a: str, b: str) -> (str, str):
    a_tokens = _tokenize_keep_spaces(a)
    b_tokens = _tokenize_keep_spaces(b)
    sm = SequenceMatcher(None, a_tokens, b_tokens)
    a_out = []
    b_out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            a_out.extend(map(html.escape, a_tokens[i1:i2]))
            b_out.extend(map(html.escape, b_tokens[j1:j2]))
        elif tag == 'delete':
            # old tokens removed -> mark red & highlighted
            a_out.append('<span class="old hl">' + html.escape(''.join(a_tokens[i1:i2])) + '</span>')
        elif tag == 'insert':
            # new tokens added -> mark green & highlighted
            b_out.append('<span class="new hl">' + html.escape(''.join(b_tokens[j1:j2])) + '</span>')
        elif tag == 'replace':
            a_out.append('<span class="old hl">' + html.escape(''.join(a_tokens[i1:i2])) + '</span>')
            b_out.append('<span class="new hl">' + html.escape(''.join(b_tokens[j1:j2])) + '</span>')
    return (''.join(a_out), ''.join(b_out))


def make_sheet_diff_html(name: str, a_lines: List[str], b_lines: List[str], fromdesc: str, todesc: str) -> str:
    # Build a horizontal two-column table: old (left, red) | new (right, green)
    rows = []
    sm = SequenceMatcher(None, a_lines, b_lines)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            for ai, bi in zip(a_lines[i1:i2], b_lines[j1:j2]):
                rows.append((html.escape(ai), html.escape(bi)))
        elif tag == 'replace':
            # Align replaced blocks line-by-line where possible
            for a_ln, b_ln in zip_longest(a_lines[i1:i2], b_lines[j1:j2], fillvalue=""):
                a_h, b_h = _highlight_word_diff(a_ln, b_ln)
                rows.append((a_h or '', b_h or ''))
        elif tag == 'delete':
            for a_ln in a_lines[i1:i2]:
                a_h, _ = _highlight_word_diff(a_ln, "")
                rows.append((a_h, ""))
        elif tag == 'insert':
            for b_ln in b_lines[j1:j2]:
                _, b_h = _highlight_word_diff("", b_ln)
                rows.append(("", b_h))

    # Build HTML table
    html_rows = []
    html_rows.append(f'<h2 id="sheet_{html.escape(name)}">Sheet: {html.escape(name)}</h2>')
    html_rows.append('<table class="horiz-diff" border="1">')
    html_rows.append(f'<thead><tr><th style="width:50%">Old ({html.escape(fromdesc)})</th><th style="width:50%">New ({html.escape(todesc)})</th></tr></thead>')
    html_rows.append('<tbody>')
    for a_html, b_html in rows:
        a_cell = a_html if a_html != "" else '&nbsp;'
        b_cell = b_html if b_html != "" else '&nbsp;'
        # Wrap old text in span.old and new in span.new for color
        # Note: _highlight_word_diff already wrapped changed segments; for unchanged lines we still need color classes
        if 'class="old' not in a_cell and a_cell.strip() != '&nbsp;':
            a_cell = '<span class="old">' + a_cell + '</span>'
        if 'class="new' not in b_cell and b_cell.strip() != '&nbsp;':
            b_cell = '<span class="new">' + b_cell + '</span>'
        html_rows.append(f'<tr><td class="old-col">{a_cell}</td><td class="new-col">{b_cell}</td></tr>')
    html_rows.append('</tbody></table>')
    return '\n'.join(html_rows)


def render_report(title: str, sheet_results: List[dict], out_path: str):
    css = """
    body{font-family: Arial, Helvetica, sans-serif; padding: 20px}
    h1{font-size:1.4em}
    .summary ul{list-style:none;padding:0}
    .summary li{margin:4px 0}
    table.horiz-diff{width:100%;border-collapse:collapse;margin-top:12px}
    table.horiz-diff td, table.horiz-diff th{vertical-align:top;padding:8px;white-space:pre-wrap;font-family:monospace}
    table.horiz-diff thead th{background:#eee;font-weight:700}
    .old{color:#a40000}
    .new{color:#007a00}
    .hl{background: #fff59d; padding:0 2px; border-radius:2px}
    .old-col{background:#fff5f5}
    .new-col{background:#f5fff5}
    """

    parts = []
    parts.append(f"<html><head><meta charset=\"utf-8\"><title>{html.escape(title)}</title><style>{css}</style></head><body>")
    parts.append(f"<h1>{html.escape(title)}</h1>")
    parts.append('<div class="summary"><strong>Sheets</strong><ul>')
    for r in sheet_results:
        ok = "identical" if r["identical"] else "diff"
        parts.append(f'<li><a href="#sheet_{html.escape(r["name"])}">{html.escape(r["name"])}</a>: {ok}</li>')
    parts.append('</ul></div>')
    for r in sheet_results:
        parts.append(r["html"])
    parts.append("</body></html>")

    html_text = "\n".join(parts)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_text)


def main():
    p = argparse.ArgumentParser(description="Diff two Excel files and produce an HTML report")
    p.add_argument("old", help="Old Excel file path")
    p.add_argument("new", help="New Excel file path")
    p.add_argument("-o", "--output", default="xlsx_diff_report.html", help="Output HTML file")
    p.add_argument("-w", "--width", type=int, default=120, help="Wrap width for lines")
    p.add_argument("--sheet", help="Optional: only diff this sheet name (exact match)")
    args = p.parse_args()

    if not os.path.exists(args.old):
        raise SystemExit(f"Old file not found: {args.old}")
    if not os.path.exists(args.new):
        raise SystemExit(f"New file not found: {args.new}")

    a_sheets = pd.read_excel(args.old, sheet_name=None, engine="openpyxl")
    b_sheets = pd.read_excel(args.new, sheet_name=None, engine="openpyxl")

    names = set(a_sheets.keys()) | set(b_sheets.keys())
    if args.sheet:
        if args.sheet not in names:
            raise SystemExit(f"Sheet '{args.sheet}' not found in either file")
        names = {args.sheet}

    sheet_results = []
    for name in sorted(names):
        a_df = a_sheets.get(name)
        b_df = b_sheets.get(name)
        a_lines = df_to_lines(a_df)
        b_lines = df_to_lines(b_df)
        a_wrapped = wrap_lines(a_lines, args.width)
        b_wrapped = wrap_lines(b_lines, args.width)
        identical = a_wrapped == b_wrapped
        html_fragment = make_sheet_diff_html(name, a_wrapped, b_wrapped, f"{os.path.basename(args.old)}:{name}", f"{os.path.basename(args.new)}:{name}")
        sheet_results.append({"name": name, "identical": identical, "html": html_fragment})

    render_report(f"Excel Diff: {os.path.basename(args.old)} ↔ {os.path.basename(args.new)}", sheet_results, args.output)
    print(f"Wrote HTML diff to: {args.output}")


if __name__ == "__main__":
    main()
