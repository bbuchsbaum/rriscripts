#!/usr/bin/env bats
# Tests for command_distributor.sh
# These tests mock SLURM_ARRAY_TASK_ID and use a stub for 'parallel'.

setup() {
    CMD_DIST="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)/command_distributor.sh"
    TMPDIR="$(mktemp -d)"

    # Create a mock 'parallel' that just prints what it would run
    mkdir -p "$TMPDIR/bin"
    cat > "$TMPDIR/bin/parallel" <<'MOCK'
#!/bin/bash
# Mock parallel: just run each line from stdin sequentially
while IFS= read -r line; do
    echo "MOCK_RUN: $line"
done
MOCK
    chmod +x "$TMPDIR/bin/parallel"
    export PATH="$TMPDIR/bin:$PATH"
}

teardown() {
    rm -rf "$TMPDIR"
    unset SLURM_ARRAY_TASK_ID
}

# ── Basic distribution ─────────────────────────────────────────────

@test "distributes commands to batch 1 of 2" {
    printf 'cmd1\ncmd2\ncmd3\ncmd4\n' > "$TMPDIR/cmds.txt"
    export SLURM_ARRAY_TASK_ID=1
    run "$CMD_DIST" "$TMPDIR/cmds.txt" 2
    [ "$status" -eq 0 ]
    [[ "$output" == *"MOCK_RUN: cmd1"* ]]
    [[ "$output" == *"MOCK_RUN: cmd2"* ]]
    [[ "$output" != *"MOCK_RUN: cmd3"* ]]
}

@test "distributes commands to batch 2 of 2" {
    printf 'cmd1\ncmd2\ncmd3\ncmd4\n' > "$TMPDIR/cmds.txt"
    export SLURM_ARRAY_TASK_ID=2
    run "$CMD_DIST" "$TMPDIR/cmds.txt" 2
    [ "$status" -eq 0 ]
    [[ "$output" == *"MOCK_RUN: cmd3"* ]]
    [[ "$output" == *"MOCK_RUN: cmd4"* ]]
    [[ "$output" != *"MOCK_RUN: cmd1"* ]]
}

@test "handles uneven split (5 commands, 2 batches)" {
    printf 'a\nb\nc\nd\ne\n' > "$TMPDIR/cmds.txt"
    export SLURM_ARRAY_TASK_ID=1
    run "$CMD_DIST" "$TMPDIR/cmds.txt" 2
    [ "$status" -eq 0 ]
    # Batch 1 gets ceil(5/2)=3 commands
    [[ "$output" == *"MOCK_RUN: a"* ]]
    [[ "$output" == *"MOCK_RUN: b"* ]]
    [[ "$output" == *"MOCK_RUN: c"* ]]
}

@test "single batch gets all commands" {
    printf 'x\ny\nz\n' > "$TMPDIR/cmds.txt"
    export SLURM_ARRAY_TASK_ID=1
    run "$CMD_DIST" "$TMPDIR/cmds.txt" 1
    [ "$status" -eq 0 ]
    [[ "$output" == *"3 commands"* ]]
}

@test "last batch may have fewer commands" {
    printf 'a\nb\nc\nd\ne\n' > "$TMPDIR/cmds.txt"
    export SLURM_ARRAY_TASK_ID=2
    run "$CMD_DIST" "$TMPDIR/cmds.txt" 2
    [ "$status" -eq 0 ]
    # Batch 2 gets 2 commands (5 - 3 = 2)
    [[ "$output" == *"2 commands"* ]]
}

# ── Custom jobs_per_batch ──────────────────────────────────────────

@test "passes jobs_per_batch to parallel" {
    # Override mock to check --jobs flag
    cat > "$TMPDIR/bin/parallel" <<'MOCK'
#!/bin/bash
echo "PARALLEL_ARGS: $*"
cat > /dev/null
MOCK
    chmod +x "$TMPDIR/bin/parallel"
    printf 'cmd1\n' > "$TMPDIR/cmds.txt"
    export SLURM_ARRAY_TASK_ID=1
    run "$CMD_DIST" "$TMPDIR/cmds.txt" 1 10
    [ "$status" -eq 0 ]
    [[ "$output" == *"PARALLEL_ARGS: --jobs 10"* ]]
}

# ── Error cases ────────────────────────────────────────────────────

@test "fails without SLURM_ARRAY_TASK_ID" {
    unset SLURM_ARRAY_TASK_ID
    printf 'cmd1\n' > "$TMPDIR/cmds.txt"
    run "$CMD_DIST" "$TMPDIR/cmds.txt" 1
    [ "$status" -ne 0 ]
    [[ "$output" == *"SLURM_ARRAY_TASK_ID"* ]]
}

@test "fails with out-of-range task ID" {
    printf 'cmd1\n' > "$TMPDIR/cmds.txt"
    export SLURM_ARRAY_TASK_ID=5
    run "$CMD_DIST" "$TMPDIR/cmds.txt" 2
    [ "$status" -ne 0 ]
    [[ "$output" == *"out of range"* ]]
}

@test "fails with nonexistent commands file" {
    export SLURM_ARRAY_TASK_ID=1
    run "$CMD_DIST" "/no/such/file.txt" 1
    [ "$status" -ne 0 ]
}

@test "fails with wrong number of arguments" {
    run "$CMD_DIST"
    [ "$status" -ne 0 ]
}

@test "empty batch exits cleanly" {
    # 1 command, 3 batches — batch 3 should have 0 commands
    printf 'only_one\n' > "$TMPDIR/cmds.txt"
    export SLURM_ARRAY_TASK_ID=3
    run "$CMD_DIST" "$TMPDIR/cmds.txt" 3
    [ "$status" -eq 0 ]
    [[ "$output" == *"No commands"* ]]
}
