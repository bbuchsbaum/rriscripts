#!/usr/bin/env bash
# Select one 1-based data ID and append it as ONE argument; never interpret it as code.
# Usage: bash array-task.sh MANIFEST EXECUTABLE [ARGUMENT ...]
set -euo pipefail
fail() { printf 'array-task: %s\n' "$*" >&2; exit 64; }
(( $# >= 2 )) || fail 'need MANIFEST and EXECUTABLE [ARGUMENT ...]'
manifest=$1
shift
[[ -r "$manifest" && -f "$manifest" ]] || fail "unreadable manifest: $manifest"
index=${SLURM_ARRAY_TASK_ID:-}
[[ "$index" =~ ^[1-9][0-9]{0,9}$ ]] || fail 'SLURM_ARRAY_TASK_ID must be a positive 1-based index'
# An absolute manifest path cannot be mistaken for a sed option.
[[ "$manifest" == /* ]] || fail 'use an absolute manifest path in the frozen run directory'
item=$(sed -n "${index}p" "$manifest")
[[ -n "$item" && ! "$item" =~ ^[[:space:]]*$ ]] || fail "missing/blank manifest row $index"
[[ "$item" != *$'\r'* ]] || fail 'manifest must use LF, not CRLF, line endings'
# No eval, bash -c, word splitting, or shell interpretation of the selected ID.
exec "$@" "$item"
