#!/usr/bin/env bats
# Tests for bexec.sh (using qexec --dry-run)

setup() {
    BEXEC="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)/bexec.sh"
    TMPDIR="$(mktemp -d)"
    printf 'echo one\necho two\n' > "$TMPDIR/cmds.txt"
}

teardown() {
    rm -rf "$TMPDIR"
}

@test "dry-run: resolves local qexec and distributor" {
    run "$BEXEC" --dry-run -f "$TMPDIR/cmds.txt" -n 2
    [ "$status" -eq 0 ]
    [[ "$output" == *"Submitting 2 commands across 2 batch(es)."* ]]
    [[ "$output" == *"command_distributor.sh"* ]]
    [[ "$output" == *"Dry-run"* ]]
}

@test "invalid time fails" {
    run "$BEXEC" --dry-run -f "$TMPDIR/cmds.txt" --time 0
    [ "$status" -ne 0 ]
    [[ "$output" == *"--time"* ]]
}

@test "blank-only command files fail" {
    printf '\n  \n' > "$TMPDIR/blank.txt"
    run "$BEXEC" --dry-run -f "$TMPDIR/blank.txt"
    [ "$status" -ne 0 ]
    [[ "$output" == *"empty"* ]]
}
