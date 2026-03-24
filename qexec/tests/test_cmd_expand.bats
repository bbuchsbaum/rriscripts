#!/usr/bin/env bats
# Tests for cmd_expand.sh

setup() {
    CMD_EXPAND="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)/cmd_expand.sh"
    TMPDIR="$(mktemp -d)"
}

teardown() {
    rm -rf "$TMPDIR"
}

# ── Cartesian product ──────────────────────────────────────────────

@test "cartesian: two lists produce correct product" {
    run "$CMD_EXPAND" echo [a,b] [1,2]
    [ "$status" -eq 0 ]
    [ "${#lines[@]}" -eq 4 ]
    [ "${lines[0]}" = "echo a 1" ]
    [ "${lines[1]}" = "echo a 2" ]
    [ "${lines[2]}" = "echo b 1" ]
    [ "${lines[3]}" = "echo b 2" ]
}

@test "cartesian: single value passes through unchanged" {
    run "$CMD_EXPAND" myprog [only]
    [ "$status" -eq 0 ]
    [ "${#lines[@]}" -eq 1 ]
    [ "${lines[0]}" = "myprog only" ]
}

@test "cartesian: three lists" {
    run "$CMD_EXPAND" cmd [a,b] [1,2] [x,y]
    [ "$status" -eq 0 ]
    [ "${#lines[@]}" -eq 8 ]
}

# ── Ranges ─────────────────────────────────────────────────────────

@test "range: dotdot ascending" {
    run "$CMD_EXPAND" prog [1..3]
    [ "$status" -eq 0 ]
    [ "${#lines[@]}" -eq 3 ]
    [ "${lines[0]}" = "prog 1" ]
    [ "${lines[1]}" = "prog 2" ]
    [ "${lines[2]}" = "prog 3" ]
}

@test "range: colon syntax" {
    run "$CMD_EXPAND" prog [2:4]
    [ "$status" -eq 0 ]
    [ "${#lines[@]}" -eq 3 ]
    [ "${lines[0]}" = "prog 2" ]
    [ "${lines[2]}" = "prog 4" ]
}

@test "range: descending" {
    run "$CMD_EXPAND" prog [3..1]
    [ "$status" -eq 0 ]
    [ "${#lines[@]}" -eq 3 ]
    [ "${lines[0]}" = "prog 3" ]
    [ "${lines[2]}" = "prog 1" ]
}

# ── Link mode ──────────────────────────────────────────────────────

@test "link: zips arguments by position" {
    run "$CMD_EXPAND" --link echo [a,b,c] [1,2,3]
    [ "$status" -eq 0 ]
    [ "${#lines[@]}" -eq 3 ]
    [ "${lines[0]}" = "echo a 1" ]
    [ "${lines[1]}" = "echo b 2" ]
    [ "${lines[2]}" = "echo c 3" ]
}

@test "link: shorter list repeats last value" {
    run "$CMD_EXPAND" --link echo [a,b,c] [X]
    [ "$status" -eq 0 ]
    [ "${#lines[@]}" -eq 3 ]
    [ "${lines[0]}" = "echo a X" ]
    [ "${lines[1]}" = "echo b X" ]
    [ "${lines[2]}" = "echo c X" ]
}

# ── Named options ──────────────────────────────────────────────────

@test "named option with bracket expansion" {
    run "$CMD_EXPAND" prog -f [a.txt,b.txt]
    [ "$status" -eq 0 ]
    [ "${#lines[@]}" -eq 2 ]
    [ "${lines[0]}" = "prog -f a.txt" ]
    [ "${lines[1]}" = "prog -f b.txt" ]
}

@test "named option with static value" {
    run "$CMD_EXPAND" prog -f myfile.txt
    [ "$status" -eq 0 ]
    [ "${#lines[@]}" -eq 1 ]
    [ "${lines[0]}" = "prog -f myfile.txt" ]
}

# ── file: source ───────────────────────────────────────────────────

@test "file: reads lines from file" {
    printf 'alpha\nbeta\ngamma\n' > "$TMPDIR/vals.txt"
    run "$CMD_EXPAND" prog "[file:${TMPDIR}/vals.txt]"
    [ "$status" -eq 0 ]
    [ "${#lines[@]}" -eq 3 ]
    [ "${lines[0]}" = "prog alpha" ]
    [ "${lines[2]}" = "prog gamma" ]
}

@test "file: skips blank lines" {
    printf 'one\n\ntwo\n  \nthree\n' > "$TMPDIR/vals.txt"
    run "$CMD_EXPAND" prog "[file:${TMPDIR}/vals.txt]"
    [ "$status" -eq 0 ]
    [ "${#lines[@]}" -eq 3 ]
}

@test "file: nonexistent file fails" {
    run "$CMD_EXPAND" prog "[file:/no/such/file.txt]"
    [ "$status" -ne 0 ]
}

# ── df: CSV column ─────────────────────────────────────────────────

@test "df: extracts CSV column by header" {
    printf 'name,value\nalpha,1\nbeta,2\n' > "$TMPDIR/data.csv"
    run "$CMD_EXPAND" prog "[df:name:${TMPDIR}/data.csv]"
    [ "$status" -eq 0 ]
    [ "${#lines[@]}" -eq 2 ]
    [ "${lines[0]}" = "prog alpha" ]
    [ "${lines[1]}" = "prog beta" ]
}

@test "df: missing column fails" {
    printf 'name,value\nalpha,1\n' > "$TMPDIR/data.csv"
    run "$CMD_EXPAND" prog "[df:missing:${TMPDIR}/data.csv]"
    [ "$status" -ne 0 ]
}

# ── glob: pattern ──────────────────────────────────────────────────

@test "glob: matches files" {
    touch "$TMPDIR/a.dat" "$TMPDIR/b.dat"
    run "$CMD_EXPAND" prog "[glob:${TMPDIR}/*.dat]"
    [ "$status" -eq 0 ]
    [ "${#lines[@]}" -eq 2 ]
}

@test "glob: no matches fails" {
    run "$CMD_EXPAND" prog "[glob:${TMPDIR}/*.zzz_nope]"
    [ "$status" -ne 0 ]
}

# ── Output modes ───────────────────────────────────────────────────

@test "json output" {
    run "$CMD_EXPAND" --json echo [a,b]
    [ "$status" -eq 0 ]
    # Should be valid JSON array
    echo "$output" | python3 -c "import json,sys; cmds=json.load(sys.stdin); assert len(cmds)==2"
}

@test "quote output shell-quotes tokens" {
    run "$CMD_EXPAND" --quote echo [a,b]
    [ "$status" -eq 0 ]
    # shlex.quote on simple strings may or may not add quotes, but should succeed
    [ "${#lines[@]}" -eq 2 ]
}

# ── Error cases ────────────────────────────────────────────────────

@test "no base command fails" {
    run "$CMD_EXPAND"
    [ "$status" -ne 0 ]
}

@test "help flag exits cleanly" {
    run "$CMD_EXPAND" --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"Usage"* ]]
}
