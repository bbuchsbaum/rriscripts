#!/usr/bin/env Rscript

suppressPackageStartupMessages(library("optparse"))
suppressPackageStartupMessages(library("xnatR"))

args <- commandArgs(trailingOnly = TRUE)

commands <- c(
  "init",
  "authenticate",
  "auth_status",
  "logout",
  "token_issue",
  "token_list",
  "token_validate",
  "token_invalidate",
  "list_projects",
  "list_subjects",
  "list_experiments",
  "list_scans",
  "search_scans",
  "download_files",
  "download_experiment",
  "download_subject",
  "download_all",
  "help"
)

print_help <- function() {
  cat(
"xnatR command-line interface

Usage:
  xnat_cli.R <command> [options]

Core commands:
  init               Initialize ~/.xnatR_config.yml
  authenticate       Authenticate with an XNAT server
  auth_status        Show whether a global xnatR session is active
  logout             Clear the current xnatR session

Token commands:
  token_issue        Issue a new alias token for the authenticated user
  token_list         List active alias tokens
  token_validate     Validate an alias token
  token_invalidate   Invalidate an alias token

Browse commands:
  list_projects      List projects
  list_subjects      List subjects in a project
  list_experiments   List experiments for a subject
  list_scans         List scans in an experiment
  search_scans       Search scans by scan/session metadata

Download commands:
  download_files     Download scan-level files
  download_experiment Download an experiment archive
  download_subject   Download all data for one subject
  download_all       Download all subjects in a project
  help               Display this help message

Notes:
  - This CLI targets the current xnatR API.
  - authenticate_xnat() does not accept a --token argument in xnatR 0.2.0.
    Use --alias/--secret or --username/--password instead.
  - download_all is implemented in this CLI by iterating over list_subjects()
    because xnatR no longer exports download_all_subjects().
"
  )
}

command_help <- function(command) {
  help_map <- list(
    authenticate =
"authenticate options:
  --base_url URL
  --username USER
  --password PASS
  --alias TOKEN_ALIAS
  --secret TOKEN_SECRET
  --ssl_verify / --no_ssl_verify
  --verify / --no_verify
  --use_jsession
",
    token_validate =
"token_validate options:
  --alias TOKEN_ALIAS
  --secret TOKEN_SECRET
",
    token_invalidate =
"token_invalidate options:
  --alias TOKEN_ALIAS
  --secret TOKEN_SECRET
",
    list_subjects =
"list_subjects options:
  --project_id PROJECT
  --columns COL1,COL2
  --limit N
  --offset N
",
    list_experiments =
"list_experiments options:
  --project_id PROJECT
  --subject_id SUBJECT
  --columns COL1,COL2
  --limit N
  --offset N
",
    list_scans =
"list_scans options:
  --project_id PROJECT
  --subject_id SUBJECT
  --experiment_id EXPERIMENT
  --columns COL1,COL2
  --limit N
  --offset N
",
    search_scans =
"search_scans options:
  --project_id PROJECT
  --subject_id SUBJECT
  --experiment_id EXPERIMENT
  --age AGE
  --scan_type TYPE
  --tr VALUE
  --te VALUE
  --ti VALUE
  --flip VALUE
  --voxel_res_units UNITS
  --voxel_res_x VALUE
  --voxel_res_y VALUE
  --voxel_res_z VALUE
  --orientation ORIENTATION
",
    download_files =
"download_files options:
  --project_id PROJECT
  --subject_id SUBJECT
  --experiment_id EXPERIMENT
  --scan_id SCAN_ID          default: ALL
  --resource RESOURCE
  --format zip|tar.gz
  --dest_dir DIR
  --dest_file FILE
  --progress / --no_progress
",
    download_experiment =
"download_experiment options:
  --experiment_id EXPERIMENT
  --scan_id SCAN_ID          default: ALL
  --format zip|tar.gz
  --dest_dir DIR
  --dest_file FILE
  --extract
  --progress / --no_progress
  --strict / --no_strict
",
    download_subject =
"download_subject options:
  --project_id PROJECT
  --subject_id SUBJECT
  --format zip|tar.gz
  --dest_dir DIR
  --progress / --no_progress
",
    download_all =
"download_all options:
  --project_id PROJECT
  --format zip|tar.gz
  --dest_dir DIR
  --progress / --no_progress
"
  )

  if (!is.null(help_map[[command]])) {
    cat(help_map[[command]])
  } else {
    print_help()
  }
}

quit_error <- function(..., status = 1) {
  cat(..., "\n", sep = "")
  quit(status = status)
}

require_opts <- function(opt, fields, command_name) {
  missing <- fields[vapply(fields, function(x) is.null(opt[[x]]) || identical(opt[[x]], ""), logical(1))]
  if (length(missing) > 0) {
    quit_error(
      "Error: Missing required options for ", command_name, ": ",
      paste0("--", missing, collapse = ", ")
    )
  }
}

split_columns <- function(value) {
  if (is.null(value) || identical(value, "")) {
    return(NULL)
  }
  trimws(strsplit(value, ",", fixed = TRUE)[[1]])
}

require_function <- function(fn) {
  if (!exists(fn, asNamespace("xnatR"), inherits = FALSE)) {
    quit_error(
      "Error: xnatR::", fn, "() is not available in the installed xnatR package. ",
      "Update the installed package to match the current source tree."
    )
  }
}

resolve_subject_ids <- function(subjects) {
  candidate_cols <- c("ID", "id", "label", "subject_id")
  found <- candidate_cols[candidate_cols %in% names(subjects)]
  if (length(found) == 0) {
    quit_error(
      "Error: Could not determine subject identifier column from list_subjects() output. ",
      "Available columns: ", paste(names(subjects), collapse = ", ")
    )
  }
  as.character(subjects[[found[[1]]]])
}

init_command <- function() {
  path <- xnatR::initialize_config()
  cat("Initialized config:", path, "\n")
}

authenticate_command <- function(options) {
  option_list <- list(
    make_option("--base_url", type = "character", default = NULL, help = "Base URL of the XNAT server"),
    make_option("--username", type = "character", default = NULL, help = "Username for XNAT authentication"),
    make_option("--password", type = "character", default = NULL, help = "Password for XNAT authentication"),
    make_option("--alias", type = "character", default = NULL, help = "Alias token to use as the username"),
    make_option("--secret", type = "character", default = NULL, help = "Alias token secret to use as the password"),
    make_option("--token", type = "character", default = NULL, help = "Deprecated and unsupported by current xnatR"),
    make_option("--ssl_verify", action = "store_true", default = TRUE, help = "Verify SSL certificates [default]"),
    make_option("--no_ssl_verify", action = "store_false", dest = "ssl_verify", help = "Do not verify SSL certificates"),
    make_option("--verify", action = "store_true", default = TRUE, help = "Verify credentials with a test request [default]"),
    make_option("--no_verify", action = "store_false", dest = "verify", help = "Skip credential verification"),
    make_option("--use_jsession", action = "store_true", default = FALSE, help = "Use JSESSION-based auth")
  )

  opt <- parse_args(OptionParser(option_list = option_list), args = options)

  if (!is.null(opt$token)) {
    quit_error(
      "Error: --token is not supported by current xnatR::authenticate_xnat(). ",
      "Use --username/--password or --alias/--secret."
    )
  }

  username <- opt$username
  password <- opt$password
  if (!is.null(opt$alias) || !is.null(opt$secret)) {
    if (is.null(opt$alias) || is.null(opt$secret)) {
      quit_error("Error: --alias and --secret must be supplied together.")
    }
    username <- opt$alias
    password <- opt$secret
  }

  xnatR::authenticate_xnat(
    base_url = opt$base_url,
    username = username,
    password = password,
    ssl_verify = opt$ssl_verify,
    verify = opt$verify,
    use_jsession = opt$use_jsession
  )

  cat("Authentication succeeded.\n")
}

auth_status_command <- function() {
  status <- xnatR::is_authenticated()
  cat(if (isTRUE(status)) "authenticated\n" else "not authenticated\n")
}

logout_command <- function(options) {
  option_list <- list(
    make_option("--invalidate_session", action = "store_true", default = FALSE, help = "Invalidate the remote session if applicable")
  )
  opt <- parse_args(OptionParser(option_list = option_list), args = options)
  xnatR::xnat_logout(invalidate_session = opt$invalidate_session)
  cat("Logged out.\n")
}

token_issue_command <- function() {
  print(xnatR::xnat_token_issue())
}

token_list_command <- function() {
  print(xnatR::xnat_token_list())
}

token_validate_command <- function(options) {
  option_list <- list(
    make_option("--alias", type = "character", help = "Token alias"),
    make_option("--secret", type = "character", help = "Token secret")
  )
  opt <- parse_args(OptionParser(option_list = option_list), args = options)
  require_opts(opt, c("alias", "secret"), "token_validate")
  print(xnatR::xnat_token_validate(alias = opt$alias, secret = opt$secret))
}

token_invalidate_command <- function(options) {
  option_list <- list(
    make_option("--alias", type = "character", help = "Token alias"),
    make_option("--secret", type = "character", help = "Token secret")
  )
  opt <- parse_args(OptionParser(option_list = option_list), args = options)
  require_opts(opt, c("alias", "secret"), "token_invalidate")
  print(xnatR::xnat_token_invalidate(alias = opt$alias, secret = opt$secret))
}

list_projects_command <- function(options) {
  option_list <- list(
    make_option("--columns", type = "character", default = NULL, help = "Comma-separated column names"),
    make_option("--limit", type = "integer", default = NULL, help = "Maximum number of rows"),
    make_option("--offset", type = "integer", default = NULL, help = "Number of rows to skip")
  )
  opt <- parse_args(OptionParser(option_list = option_list), args = options)
  xnatR::authenticate_xnat()
  print(xnatR::list_projects(columns = split_columns(opt$columns), limit = opt$limit, offset = opt$offset))
}

list_subjects_command <- function(options) {
  option_list <- list(
    make_option("--project_id", type = "character", help = "Project ID"),
    make_option("--columns", type = "character", default = NULL, help = "Comma-separated column names"),
    make_option("--limit", type = "integer", default = NULL, help = "Maximum number of rows"),
    make_option("--offset", type = "integer", default = NULL, help = "Number of rows to skip")
  )

  opt <- parse_args(OptionParser(option_list = option_list), args = options)
  require_opts(opt, c("project_id"), "list_subjects")
  xnatR::authenticate_xnat()
  print(xnatR::list_subjects(
    project_id = opt$project_id,
    columns = split_columns(opt$columns),
    limit = opt$limit,
    offset = opt$offset
  ))
}

list_experiments_command <- function(options) {
  option_list <- list(
    make_option("--project_id", type = "character", help = "Project ID"),
    make_option("--subject_id", type = "character", help = "Subject ID"),
    make_option("--columns", type = "character", default = NULL, help = "Comma-separated column names"),
    make_option("--limit", type = "integer", default = NULL, help = "Maximum number of rows"),
    make_option("--offset", type = "integer", default = NULL, help = "Number of rows to skip")
  )

  opt <- parse_args(OptionParser(option_list = option_list), args = options)
  require_opts(opt, c("project_id", "subject_id"), "list_experiments")
  xnatR::authenticate_xnat()
  print(xnatR::list_experiments(
    project_id = opt$project_id,
    subject_id = opt$subject_id,
    columns = split_columns(opt$columns),
    limit = opt$limit,
    offset = opt$offset
  ))
}

list_scans_command <- function(options) {
  option_list <- list(
    make_option("--project_id", type = "character", help = "Project ID"),
    make_option("--subject_id", type = "character", help = "Subject ID"),
    make_option("--experiment_id", type = "character", help = "Experiment ID"),
    make_option("--columns", type = "character", default = NULL, help = "Comma-separated column names"),
    make_option("--limit", type = "integer", default = NULL, help = "Maximum number of rows"),
    make_option("--offset", type = "integer", default = NULL, help = "Number of rows to skip")
  )

  opt <- parse_args(OptionParser(option_list = option_list), args = options)
  require_opts(opt, c("project_id", "subject_id", "experiment_id"), "list_scans")
  xnatR::authenticate_xnat()
  print(xnatR::list_scans(
    project_id = opt$project_id,
    subject_id = opt$subject_id,
    experiment_id = opt$experiment_id,
    columns = split_columns(opt$columns),
    limit = opt$limit,
    offset = opt$offset
  ))
}

search_scans_command <- function(options) {
  require_function("search_scans")

  option_list <- list(
    make_option("--subject_id", type = "character", default = NULL, help = "Subject ID filter"),
    make_option("--project_id", type = "character", default = NULL, help = "Project ID filter"),
    make_option("--age", type = "character", default = NULL, help = "Age filter"),
    make_option("--experiment_id", type = "character", default = NULL, help = "Experiment ID filter"),
    make_option("--scan_type", type = "character", default = NULL, help = "Scan type filter"),
    make_option("--tr", type = "double", default = NULL, help = "TR filter"),
    make_option("--te", type = "double", default = NULL, help = "TE filter"),
    make_option("--ti", type = "double", default = NULL, help = "TI filter"),
    make_option("--flip", type = "double", default = NULL, help = "Flip-angle filter"),
    make_option("--voxel_res_units", type = "character", default = NULL, help = "Voxel resolution units"),
    make_option("--voxel_res_x", type = "double", default = NULL, help = "Voxel resolution X"),
    make_option("--voxel_res_y", type = "double", default = NULL, help = "Voxel resolution Y"),
    make_option("--voxel_res_z", type = "double", default = NULL, help = "Voxel resolution Z"),
    make_option("--orientation", type = "character", default = NULL, help = "Orientation filter")
  )

  opt <- parse_args(OptionParser(option_list = option_list), args = options)
  xnatR::authenticate_xnat()
  print(xnatR::search_scans(
    subject_id = opt$subject_id,
    project_id = opt$project_id,
    age = opt$age,
    experiment_id = opt$experiment_id,
    scan_type = opt$scan_type,
    tr = opt$tr,
    te = opt$te,
    ti = opt$ti,
    flip = opt$flip,
    voxel_res_units = opt$voxel_res_units,
    voxel_res_x = opt$voxel_res_x,
    voxel_res_y = opt$voxel_res_y,
    voxel_res_z = opt$voxel_res_z,
    orientation = opt$orientation
  ))
}

download_files_command <- function(options) {
  option_list <- list(
    make_option("--project_id", type = "character", help = "Project ID"),
    make_option("--subject_id", type = "character", help = "Subject ID"),
    make_option("--experiment_id", type = "character", help = "Experiment ID"),
    make_option("--scan_id", type = "character", default = "ALL", help = "Scan ID [default %default]"),
    make_option("--resource", type = "character", default = NULL, help = "Resource name"),
    make_option("--format", type = "character", default = "zip", help = "Download format [default %default]"),
    make_option("--dest_dir", type = "character", default = getwd(), help = "Destination directory [default current directory]"),
    make_option("--dest_file", type = "character", default = NULL, help = "Optional destination file path"),
    make_option("--progress", action = "store_true", default = TRUE, help = "Show progress [default]"),
    make_option("--no_progress", action = "store_false", dest = "progress", help = "Disable progress output")
  )

  opt <- parse_args(OptionParser(option_list = option_list), args = options)
  require_opts(opt, c("project_id", "subject_id", "experiment_id"), "download_files")
  xnatR::authenticate_xnat()
  result <- xnatR::download_files(
    project_id = opt$project_id,
    subject_id = opt$subject_id,
    experiment_id = opt$experiment_id,
    scan_id = opt$scan_id,
    resource = opt$resource,
    format = opt$format,
    dest_dir = opt$dest_dir,
    dest_file = opt$dest_file,
    progress = opt$progress
  )
  if (!is.null(result)) {
    print(result)
  }
}

download_experiment_command <- function(options) {
  require_function("download_experiment")

  option_list <- list(
    make_option("--experiment_id", type = "character", help = "Experiment ID"),
    make_option("--scan_id", type = "character", default = "ALL", help = "Scan ID [default %default]"),
    make_option("--format", type = "character", default = "zip", help = "Download format [default %default]"),
    make_option("--dest_dir", type = "character", default = tempdir(), help = "Destination directory [default tempdir()]"),
    make_option("--dest_file", type = "character", default = NULL, help = "Optional destination file path"),
    make_option("--extract", action = "store_true", default = FALSE, help = "Extract the archive after download"),
    make_option("--progress", action = "store_true", default = TRUE, help = "Show progress [default]"),
    make_option("--no_progress", action = "store_false", dest = "progress", help = "Disable progress output"),
    make_option("--strict", action = "store_true", default = TRUE, help = "Fail on download errors [default]"),
    make_option("--no_strict", action = "store_false", dest = "strict", help = "Return NULL on download failure")
  )

  opt <- parse_args(OptionParser(option_list = option_list), args = options)
  require_opts(opt, c("experiment_id"), "download_experiment")
  xnatR::authenticate_xnat()
  result <- xnatR::download_experiment(
    experiment_id = opt$experiment_id,
    scan_id = opt$scan_id,
    format = opt$format,
    dest_dir = opt$dest_dir,
    dest_file = opt$dest_file,
    extract = opt$extract,
    progress = opt$progress,
    strict = opt$strict
  )
  if (!is.null(result)) {
    print(result)
  }
}

download_subject_command <- function(options) {
  option_list <- list(
    make_option("--project_id", type = "character", help = "Project ID"),
    make_option("--subject_id", type = "character", help = "Subject ID"),
    make_option("--format", type = "character", default = "zip", help = "Download format [default %default]"),
    make_option("--dest_dir", type = "character", default = getwd(), help = "Destination directory [default current directory]"),
    make_option("--progress", action = "store_true", default = TRUE, help = "Show progress [default]"),
    make_option("--no_progress", action = "store_false", dest = "progress", help = "Disable progress output")
  )

  opt <- parse_args(OptionParser(option_list = option_list), args = options)
  require_opts(opt, c("project_id", "subject_id"), "download_subject")
  xnatR::authenticate_xnat()
  print(xnatR::download_subject(
    project_id = opt$project_id,
    subject_id = opt$subject_id,
    format = opt$format,
    dest_dir = opt$dest_dir,
    progress = opt$progress
  ))
}

download_all_command <- function(options) {
  option_list <- list(
    make_option("--project_id", type = "character", help = "Project ID"),
    make_option("--format", type = "character", default = "zip", help = "Download format [default %default]"),
    make_option("--dest_dir", type = "character", default = getwd(), help = "Destination directory [default current directory]"),
    make_option("--progress", action = "store_true", default = TRUE, help = "Show progress [default]"),
    make_option("--no_progress", action = "store_false", dest = "progress", help = "Disable progress output")
  )

  opt <- parse_args(OptionParser(option_list = option_list), args = options)
  require_opts(opt, c("project_id"), "download_all")
  xnatR::authenticate_xnat()

  subjects <- xnatR::list_subjects(project_id = opt$project_id)
  subject_ids <- resolve_subject_ids(subjects)

  if (length(subject_ids) == 0) {
    cat("No subjects found for project", opt$project_id, "\n")
    return(invisible(character()))
  }

  downloaded <- character()
  for (subject_id in subject_ids) {
    cat("Downloading subject", subject_id, "...\n")
    paths <- xnatR::download_subject(
      project_id = opt$project_id,
      subject_id = subject_id,
      format = opt$format,
      dest_dir = opt$dest_dir,
      progress = opt$progress
    )
    downloaded <- c(downloaded, paths)
  }

  invisible(downloaded)
}

if (length(args) == 0) {
  print_help()
  quit(status = 1)
}

command <- args[1]
options <- args[-1]

if (!command %in% commands) {
  quit_error("Unknown command: ", command)
}

if (identical(command, "help")) {
  if (length(options) == 0) {
    print_help()
  } else {
    command_help(options[1])
  }
} else if (identical(command, "init")) {
  init_command()
} else if (identical(command, "authenticate")) {
  authenticate_command(options)
} else if (identical(command, "auth_status")) {
  auth_status_command()
} else if (identical(command, "logout")) {
  logout_command(options)
} else if (identical(command, "token_issue")) {
  token_issue_command()
} else if (identical(command, "token_list")) {
  token_list_command()
} else if (identical(command, "token_validate")) {
  token_validate_command(options)
} else if (identical(command, "token_invalidate")) {
  token_invalidate_command(options)
} else if (identical(command, "list_projects")) {
  list_projects_command(options)
} else if (identical(command, "list_subjects")) {
  list_subjects_command(options)
} else if (identical(command, "list_experiments")) {
  list_experiments_command(options)
} else if (identical(command, "list_scans")) {
  list_scans_command(options)
} else if (identical(command, "search_scans")) {
  search_scans_command(options)
} else if (identical(command, "download_files")) {
  download_files_command(options)
} else if (identical(command, "download_experiment")) {
  download_experiment_command(options)
} else if (identical(command, "download_subject")) {
  download_subject_command(options)
} else if (identical(command, "download_all")) {
  download_all_command(options)
}
