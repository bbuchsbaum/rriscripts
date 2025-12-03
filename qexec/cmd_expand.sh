#!/bin/bash
set -euo pipefail

# cmd_expand.sh
# Shell/Python reimplementation of the original cmd_expand logic (previously rewritten in Haskell).
# Generates expanded command lines via Cartesian product or linked (zip) mode.
#
# Usage:
#   cmd_expand.sh [--link] [--quote] [--json] <base_command> [arguments...]
#   Arguments can be named options (e.g., -f [file.txt]) or unnamed values.
#   Output controls:
#     --quote          Shell-quote tokens before joining.
#     --json           Emit commands as a JSON array of strings.
#   Value syntax inside []:
#     v1,v2           Comma list
#     N..M or N:M     Inclusive integer range
#     file:<path>     Lines from file (trimmed, skips blanks)
#     df:<col>:<csv>  CSV column by header name
#     glob:<pattern>  Glob pattern (*, ?) relative to CWD unless absolute
#   Examples:
#     cmd_expand.sh prog -a [1,2] [x,y]
#     cmd_expand.sh --link task -f [f1,f2] -p [A,B,C]
#     cmd_expand.sh run [1..4] -a [3]

python3 - "$@" <<'PY'
import csv
import glob
import json
import os
import shlex
import sys

usage = """Usage: cmd_expand.sh [--link] [--quote] [--json] <base_command> [arguments...]

Modes:
  Default: Cartesian product of all expanded values.
  --link : Link arguments by position, repeating the last value of shorter lists.

Output controls:
  --quote : Shell-quote tokens before joining.
  --json  : Emit commands as a JSON array of strings.

Value syntax (inside []):
  v1,v2          Comma-separated list
  N..M or N:M    Inclusive integer range
  file:<path>    Lines from file (trimmed, blanks dropped)
  df:<col>:<csv> CSV column by header name
  glob:<pattern> Glob pattern (* and ?)"""

def die(msg: str):
    sys.stderr.write(f"Error: {msg}\n")
    sys.exit(1)

def is_bracketed(s: str) -> bool:
    return len(s) >= 2 and s[0] == "[" and s[-1] == "]"

def drop_brackets(s: str) -> str:
    return s[1:-1] if is_bracketed(s) else s

def trim(s: str) -> str:
    return s.strip()

def drop_carriage(s: str) -> str:
    return s[:-1] if s.endswith("\r") else s

def read_file_lines(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return [trim(drop_carriage(line)) for line in f if trim(drop_carriage(line))]
    except FileNotFoundError:
        die(f"Specified file does not exist: {path}")
    except OSError as e:
        die(f"Failed to read file {path}: {e}")

def extract_csv_column(column: str, path: str):
    if not os.path.exists(path):
        die(f"Specified CSV file does not exist: {path}")
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            die(f"CSV file is empty: {path}")
        try:
            idx = header.index(column)
        except ValueError:
            die(f"Specified column '{column}' does not exist in the CSV file.")
        values = []
        for row in reader:
            if idx < len(row):
                val = trim(drop_carriage(row[idx]))
                if val:
                    values.append(val)
        return values

def parse_range(spec: str):
    if ".." in spec:
        sep = ".."
    elif ":" in spec:
        sep = ":"
    else:
        return None
    try:
        start_s, end_s = spec.split(sep, 1)
        start = int(start_s)
        end = int(end_s)
    except ValueError:
        return None
    if start <= end:
        return [str(x) for x in range(start, end + 1)]
    else:
        return [str(x) for x in range(start, end - 1, -1)]

def expand_value(raw: str):
    inner = drop_brackets(trim(raw))
    if inner.startswith("file:"):
        return read_file_lines(inner[len("file:"):])
    if inner.startswith("df:"):
        rest = inner[len("df:"):]
        if ":" not in rest:
            die("Malformed df: prefix. Expected df:<column>:<file>.")
        col, csv_path = rest.split(":", 1)
        return extract_csv_column(trim(col), trim(csv_path))
    if inner.startswith("glob:"):
        pattern = inner[len("glob:"):]
        matches = sorted(glob.glob(pattern))
        if not matches:
            die(f"No files match the glob pattern '{pattern}'.")
        return matches
    r = parse_range(inner)
    if r is not None:
        return r
    parts = [trim(drop_carriage(p)) for p in inner.split(",")]
    return [p for p in parts if p]

def cartesian(args):
    acc = [[]]
    for name, vals in args:
        acc = [prev + render(name, v) for prev in acc for v in vals]
    return acc

def linked(args):
    longest = max(len(vals) for _, vals in args) if args else 0
    result = []
    for i in range(longest):
        row = []
        for name, vals in args:
            v = vals[i] if i < len(vals) else vals[-1]
            row.extend(render(name, v))
        result.append(row)
    return result

def render(name, v):
    if name is None:
        return [trim(v)]
    else:
        return [name, trim(v)]

def parse_top_level(argv):
    mode = "cartesian"
    json_out = False
    quote_out = False
    opts = []
    unnamed = []
    base = None
    i = 0
    n = len(argv)
    while i < n:
        tok = argv[i]
        if tok in ("-h", "--help"):
            print(usage)
            sys.exit(0)
        if tok == "--link":
            mode = "link"
            i += 1
            continue
        if tok == "--json":
            json_out = True
            i += 1
            continue
        if tok == "--quote":
            quote_out = True
            i += 1
            continue
        if tok.startswith("-"):
            if i + 1 >= n:
                die(f"No value provided for option '{tok}'.")
            val = argv[i + 1]
            if val.startswith("-") and not is_bracketed(val):
                die(f"No value provided for option '{tok}'.")
            opts.append((tok, val))
            i += 2
            continue
        if base is None:
            base = tok
            i += 1
            continue
        unnamed.append(tok)
        i += 1
    if base is None:
        die("No base command provided.")
    named_args = [(opt, expand_value(val) if is_bracketed(val) else [trim(val)]) for opt, val in opts]
    unnamed_args = []
    for val in unnamed:
        if is_bracketed(val):
            expanded = expand_value(val)
        else:
            expanded = [trim(val)]
        unnamed_args.append((None, expanded))
    all_args = named_args + unnamed_args
    if any(len(vals) == 0 for _, vals in all_args):
        die("One of the provided arguments expanded to zero values.")
    return mode, json_out, quote_out, base, all_args

def main():
    mode, json_out, quote_out, base, args = parse_top_level(sys.argv[1:])
    if mode == "link":
        tokens_list = linked(args)
    else:
        tokens_list = cartesian(args)
    commands = []
    for tokens in tokens_list:
        pieces = [t for t in tokens if t]
        if quote_out:
            cmd = " ".join([shlex.quote(base)] + [shlex.quote(t) for t in pieces])
        else:
            cmd = " ".join([base] + pieces)
        commands.append(cmd)
    if json_out:
        print(json.dumps(commands))
    else:
        for cmd in commands:
            print(cmd)

if __name__ == "__main__":
    main()
PY
