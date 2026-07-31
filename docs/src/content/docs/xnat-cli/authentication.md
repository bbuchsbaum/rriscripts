---
title: Authentication
description: Set up the xnatR config, authenticate with a password or an alias token, and manage tokens.
---

## Initialize the config

```bash
Rscript xnat_cli.R init
```

Creates `~/.xnatR_config.yml` via `xnatR::initialize_config()` and prints the
path. Do this once per machine.

## Authenticate

```bash
Rscript xnat_cli.R authenticate \
    --base_url https://xnat.example.org \
    --username me \
    --password 'secret'
```

| Option | Effect |
|---|---|
| `--base_url URL` | Base URL of the XNAT server |
| `--username USER` | Username |
| `--password PASS` | Password |
| `--alias TOKEN_ALIAS` | Alias token, used in place of a username |
| `--secret TOKEN_SECRET` | Alias token secret, used in place of a password |
| `--ssl_verify` / `--no_ssl_verify` | Verify SSL certificates (default: verify) |
| `--verify` / `--no_verify` | Verify credentials with a test request (default: verify) |
| `--use_jsession` | Use JSESSION-based auth |

:::caution
A password on the command line lands in your shell history and is visible in
`ps` output. Prefer [alias tokens](#alias-tokens) for anything scripted, and
put the `base_url` in `~/.xnatR_config.yml` so you are not retyping it.
:::

### Alias tokens

Alias tokens are the better credential for scripts and cluster jobs: they are
scoped, revocable, and do not expose your account password.

`--alias` and `--secret` must be supplied together — passing only one is an
error. They are used as the username and password respectively:

```bash
Rscript xnat_cli.R authenticate \
    --base_url https://xnat.example.org \
    --alias abc123 \
    --secret def456
```

:::note
`--token` exists as an option but is **not supported** by the current
`xnatR::authenticate_xnat()` and will error. Use `--alias`/`--secret`.
:::

### Self-signed certificates

Some institutional XNAT servers use certificates R will not validate. Use
`--no_ssl_verify` when you know the host is trustworthy and the failure is
certificate chain policy rather than a real problem.

## Check status

```bash
Rscript xnat_cli.R auth_status
```

Prints `authenticated` or `not authenticated`.

Note that the browse and download commands call `authenticate_xnat()` themselves
before each request, so they generally work from the stored session or config
without an explicit `authenticate` step.

## Log out

```bash
Rscript xnat_cli.R logout
Rscript xnat_cli.R logout --invalidate_session
```

`--invalidate_session` also invalidates the remote session where applicable,
rather than only clearing local state.

## Managing tokens

```bash
# Issue a new alias token for the authenticated user
Rscript xnat_cli.R token_issue

# List active alias tokens
Rscript xnat_cli.R token_list

# Validate a token
Rscript xnat_cli.R token_validate --alias abc123 --secret def456

# Invalidate a token
Rscript xnat_cli.R token_invalidate --alias abc123 --secret def456
```

`token_validate` and `token_invalidate` both require `--alias` **and**
`--secret`.

A useful pattern for cluster work: issue a token from your workstation, store
the alias/secret pair in the config or a mode-600 file on the cluster, and let
batch jobs authenticate with that instead of your password. Invalidate it when
the project ends.
