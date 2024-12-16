#!/usr/bin/env Rscript

# xnatR command-line interface
#
# This script provides a command-line interface to the xnatR package, allowing convenient access to XNAT repositories.
#
# Usage:
#   xnat_cli.R <command> [options]
#
# Commands:
#   init              Initialize configuration file
#   authenticate      Authenticate with XNAT server
#   list_projects     List projects
#   list_subjects     List subjects in a project
#   list_experiments  List experiments for a subject
#   list_scans        List scans in an experiment
#   download_files    Download files
#   download_subject  Download all data for a subject
#   download_all      Download all subjects' data from a project
#   help              Display this help message
#
# Examples:
#   xnat_cli.R init
#   xnat_cli.R authenticate
#   xnat_cli.R list_projects
#   xnat_cli.R list_subjects --project_id TEST
#   xnat_cli.R download_files --project_id TEST --subject_id SUBJ1 --experiment_id EXP1 --scan_id ALL
#
# For detailed help on a command, use xnat_cli.R help <command>
#
# The script uses the xnatR package and relies on the configuration file ~/.xnatR_config.yml for stored credentials.

# Load required packages
suppressPackageStartupMessages(library("optparse"))
suppressPackageStartupMessages(library("xnatR"))
suppressPackageStartupMessages(library("yaml"))

# Main script execution
args <- commandArgs(trailingOnly = TRUE)

if (length(args) == 0) {
  cat("No command provided. Use 'xnat_cli.R help' for usage information.\n")
  quit(status = 1)
}

command <- args[1]
options <- args[-1]

# Define commands
commands <- c("init", "authenticate", "list_projects", "list_subjects", "list_experiments", "list_scans",
              "download_files", "download_subject", "download_all", "help")

if (!command %in% commands) {
  cat("Unknown command:", command, "\n")
  quit(status = 1)
}

# Help function
print_help <- function() {
  cat("
xnatR command-line interface

This script provides a command-line interface to the xnatR package, allowing convenient access to XNAT repositories.

Usage:
  xnat_cli.R <command> [options]

Commands:
  init              Initialize configuration file
  authenticate      Authenticate with XNAT server
  list_projects     List projects
  list_subjects     List subjects in a project
  list_experiments  List experiments for a subject
  list_scans        List scans in an experiment
  download_files    Download files
  download_subject  Download all data for a subject
  download_all      Download all subjects' data from a project
  help              Display this help message

Examples:
  xnat_cli.R init
  xnat_cli.R authenticate
  xnat_cli.R list_projects
  xnat_cli.R list_subjects --project_id TEST
  xnat_cli.R download_files --project_id TEST --subject_id SUBJ1 --experiment_id EXP1 --scan_id ALL

For detailed help on a command, use xnat_cli.R help <command>

The script uses the xnatR package and relies on the configuration file ~/.xnatR_config.yml for stored credentials.
")
}

# Command functions
init_command <- function() {
  xnatR::initialize_config()
}

authenticate_command <- function() {
  option_list <- list(
    make_option("--base_url", type="character", default=NULL, help="Base URL of the XNAT server"),
    make_option("--username", type="character", default=NULL, help="Username for XNAT authentication"),
    make_option("--password", type="character", default=NULL, help="Password for XNAT authentication"),
    make_option("--token", type="character", default=NULL, help="API token for XNAT authentication"),
    make_option("--ssl_verify", action="store_true", default=FALSE, help="Verify SSL certificates [default]"),
    make_option("--no_ssl_verify", action="store_false", dest="ssl_verify", help="Do not verify SSL certificates")
  )

  parser <- OptionParser(option_list=option_list)
  opt <- parse_args(parser, args=options)  # Pass the options excluding the command

  xnatR::authenticate_xnat(
    base_url = opt$base_url,
    username = opt$username,
    password = opt$password,
    token = opt$token,
    ssl_verify = opt$ssl_verify
  )
}

list_projects_command <- function() {
  xnatR::authenticate_xnat()
  projects <- xnatR::list_projects()
  print(projects)
}

list_subjects_command <- function() {
  option_list <- list(
    make_option("--project_id", type="character", help="Project ID")
  )

  parser <- OptionParser(option_list=option_list)
  opt <- parse_args(parser, args=options)

  if (is.null(opt$project_id)) {
    cat("Error: --project_id is required for list_subjects\n")
    quit(status = 1)
  }

  xnatR::authenticate_xnat()
  subjects <- xnatR::list_subjects(project_id = opt$project_id)
  print(subjects)
}

list_experiments_command <- function() {
  option_list <- list(
    make_option("--project_id", type="character", help="Project ID"),
    make_option("--subject_id", type="character", help="Subject ID")
  )

  parser <- OptionParser(option_list=option_list)
  opt <- parse_args(parser, args=options)

  if (is.null(opt$project_id) || is.null(opt$subject_id)) {
    cat("Error: --project_id and --subject_id are required for list_experiments\n")
    quit(status = 1)
  }

  xnatR::authenticate_xnat()
  experiments <- xnatR::list_experiments(project_id = opt$project_id, subject_id = opt$subject_id)
  print(experiments)
}

list_scans_command <- function() {
  option_list <- list(
    make_option("--project_id", type="character", help="Project ID"),
    make_option("--subject_id", type="character", help="Subject ID"),
    make_option("--experiment_id", type="character", help="Experiment ID")
  )

  parser <- OptionParser(option_list=option_list)
  opt <- parse_args(parser, args=options)

  if (is.null(opt$project_id) || is.null(opt$subject_id) || is.null(opt$experiment_id)) {
    cat("Error: --project_id, --subject_id, and --experiment_id are required for list_scans\n")
    quit(status = 1)
  }

  xnatR::authenticate_xnat()
  scans <- xnatR::list_scans(
    project_id = opt$project_id,
    subject_id = opt$subject_id,
    experiment_id = opt$experiment_id
  )
  print(scans)
}

download_files_command <- function() {
  option_list <- list(
    make_option("--project_id", type="character", help="Project ID"),
    make_option("--subject_id", type="character", help="Subject ID"),
    make_option("--experiment_id", type="character", help="Experiment ID"),
    make_option("--scan_id", type="character", default="ALL", help="Scan ID (use 'ALL' for all scans) [default %default]"),
    make_option("--resource", type="character", default=NULL, help="Resource name (e.g., 'DICOM')"),
    make_option("--format", type="character", default="zip", help="Download format [default %default]"),
    make_option("--dest_dir", type="character", default=getwd(), help="Destination directory [default current directory]")
  )

  parser <- OptionParser(option_list=option_list)
  opt <- parse_args(parser, args=options)

  required_opts <- c("project_id", "subject_id", "experiment_id")
  missing_opts <- required_opts[sapply(required_opts, function(x) is.null(opt[[x]]))]

  if (length(missing_opts) > 0) {
    cat("Error: Missing required options:", paste0("--", missing_opts, collapse=", "), "\n")
    quit(status = 1)
  }

  xnatR::authenticate_xnat()
  xnatR::download_files(
    project_id = opt$project_id,
    subject_id = opt$subject_id,
    experiment_id = opt$experiment_id,
    scan_id = opt$scan_id,
    resource = opt$resource,
    format = opt$format,
    dest_dir = opt$dest_dir
  )
}

download_subject_command <- function() {
  option_list <- list(
    make_option("--project_id", type="character", help="Project ID"),
    make_option("--subject_id", type="character", help="Subject ID"),
    make_option("--format", type="character", default="zip", help="Download format [default %default]"),
    make_option("--dest_dir", type="character", default=getwd(), help="Destination directory [default current directory]")
  )

  parser <- OptionParser(option_list=option_list)
  opt <- parse_args(parser, args=options)

  required_opts <- c("project_id", "subject_id")
  missing_opts <- required_opts[sapply(required_opts, function(x) is.null(opt[[x]]))]

  if (length(missing_opts) > 0) {
    cat("Error: Missing required options:", paste0("--", missing_opts, collapse=", "), "\n")
    quit(status = 1)
  }

  xnatR::authenticate_xnat()
  xnatR::download_subject(
    project_id = opt$project_id,
    subject_id = opt$subject_id,
    format = opt$format,
    dest_dir = opt$dest_dir
  )
}

download_all_command <- function() {
  option_list <- list(
    make_option("--project_id", type="character", help="Project ID"),
    make_option("--format", type="character", default="zip", help="Download format [default %default]"),
    make_option("--dest_dir", type="character", default=getwd(), help="Destination directory [default current directory]")
  )

  parser <- OptionParser(option_list=option_list)
  opt <- parse_args(parser, args=options)

  if (is.null(opt$project_id)) {
    cat("Error: --project_id is required for download_all\n")
    quit(status = 1)
  }

  xnatR::authenticate_xnat()
  xnatR::download_all_subjects(
    project_id = opt$project_id,
    format = opt$format,
    dest_dir = opt$dest_dir
  )
}

# Command dispatch
if (command == "help") {
  if (length(options) == 0) {
    print_help()
  } else {
    # Provide help for specific command (not implemented separately)
    cat("Help for command:", options[1], "\n")
    # You can add detailed help for each command here
  }
} else if (command == "init") {
  init_command()
} else if (command == "authenticate") {
  authenticate_command()
} else if (command == "list_projects") {
  list_projects_command()
} else if (command == "list_subjects") {
  list_subjects_command()
} else if (command == "list_experiments") {
  list_experiments_command()
} else if (command == "list_scans") {
  list_scans_command()
} else if (command == "download_files") {
  download_files_command()
} else if (command == "download_subject") {
  download_subject_command()
} else if (command == "download_all") {
  download_all_command()
} else {
  cat("Unknown command:", command, "\n")
  quit(status = 1)
}
