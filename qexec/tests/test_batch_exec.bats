#!/usr/bin/env bats
# Tests for batch_exec.sh (using --dry-run)

setup() {
    BATCH_EXEC="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)/batch_exec.sh"
    CMD_EXPAND="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)/cmd_expand.sh"
    TMPDIR="$(mktemp -d)"
}

teardown() {
    # Clean up any batch_exec_cmds.* files
    rm -rf "$TMPDIR"
    rm -f batch_exec_cmds.* 2>/dev/null || true
}

# ── Dry-run tests ──────────────────────────────────────────────────

@test "dry-run: expands commands and shows count" {
    run "$BATCH_EXEC" --dry-run -- echo [a,b,c]
    [ "$status" -eq 0 ]
    [[ "$output" == *"Expanded to 3 commands"* ]]
    [[ "$output" == *"Dry-run"* ]]
}

@test "dry-run: cartesian product" {
    run "$BATCH_EXEC" --dry-run -- prog [1,2] [x,y]
    [ "$status" -eq 0 ]
    [[ "$output" == *"Expanded to 4 commands"* ]]
}

@test "dry-run: link mode" {
    run "$BATCH_EXEC" --dry-run --link -- prog [a,b,c] [1,2,3]
    [ "$status" -eq 0 ]
    [[ "$output" == *"Expanded to 3 commands"* ]]
}

@test "dry-run: custom nodes and time" {
    run "$BATCH_EXEC" --dry-run -t 2 -n 4 -- echo [1..8]
    [ "$status" -eq 0 ]
    [[ "$output" == *"Expanded to 8 commands"* ]]
    [[ "$output" == *"--time"* ]]
}

@test "dry-run: memory option" {
    run "$BATCH_EXEC" --dry-run -m 8G -- echo [1,2]
    [ "$status" -eq 0 ]
    [[ "$output" == *"--mem"* ]]
}

@test "dry-run: job name" {
    run "$BATCH_EXEC" --dry-run -N testjob -- echo [1,2]
    [ "$status" -eq 0 ]
    [[ "$output" == *"--name"* ]]
}

# ── Validation ─────────────────────────────────────────────────────

@test "missing command after -- fails" {
    run "$BATCH_EXEC" --dry-run --
    [ "$status" -ne 0 ]
}

@test "no -- separator fails" {
    run "$BATCH_EXEC" --dry-run
    [ "$status" -ne 0 ]
}

@test "invalid --nodes value fails" {
    run "$BATCH_EXEC" --dry-run -n 0 -- echo [1,2]
    [ "$status" -ne 0 ]
}

@test "invalid --ncpus value fails" {
    run "$BATCH_EXEC" --dry-run --ncpus 0 -- echo [1,2]
    [ "$status" -ne 0 ]
}

@test "invalid --jobs value fails" {
    run "$BATCH_EXEC" --dry-run -j 0 -- echo [1,2]
    [ "$status" -ne 0 ]
}

# ── Help ───────────────────────────────────────────────────────────

@test "help flag shows usage" {
    run "$BATCH_EXEC" --help
    [[ "$output" == *"batch_exec.sh"* ]]
}
