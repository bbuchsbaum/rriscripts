#!/usr/bin/env python3

import csv
import os
import sys
import questionary
from questionary import Validator, ValidationError

# Custom Validator for Paths
class PathValidator(Validator):
    def validate(self, document):
        if not os.path.exists(document.text):
            raise ValidationError(
                message="Path does not exist.",
                cursor_position=len(document.text))  # Move cursor to end

def get_participants(bids_dir):
    participants_file = os.path.join(bids_dir, 'participants.tsv')
    if not os.path.isfile(participants_file):
        print(f"Error: {participants_file} does not exist.")
        sys.exit(1)
    
    participants = []
    with open(participants_file, 'r', newline='') as tsvfile:
        reader = csv.DictReader(tsvfile, delimiter='\t')
        for row in reader:
            participants.append(row['participant_id'])
    return participants

def load_defaults():
    """Load default values from config file."""
    defaults = {}
    config_file = os.path.expanduser('~/.fmriprep_builder')
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    defaults[key.strip()] = value.strip().strip('"\'')
    return defaults

def main():
    print("Welcome to the fMRIPrep Interactive Command Builder\n")

    # Load defaults
    defaults = load_defaults()

    # Step 1: Get BIDS directory
    bids_dir = questionary.path("Enter the path to your BIDS dataset:", 
                                validate=PathValidator()).ask()
    if not bids_dir:
        print("BIDS directory is required.")
        sys.exit(1)
    
    # Step 2: Read participants.tsv and get subject IDs
    participants = get_participants(bids_dir)
    if not participants:
        print("No participants found in participants.tsv.")
        sys.exit(1)
    
    # Step 3: Select participants to process
    selected_participants = questionary.checkbox(
        "Select participants to process:",
        choices=participants,
        validate=lambda answer: True if len(answer) > 0 else "You must choose at least one participant."
    ).ask()
    
    if not selected_participants:
        print("No participants selected.")
        sys.exit(1)
    
    # Step 4: Get output directory
    output_dir = questionary.path("Enter the output directory for fMRIPrep results:", 
                                  default=os.path.join(bids_dir, 'derivatives', 'fmriprep'),
                                  validate=lambda text: True if text else False).ask()
    if not output_dir:
        print("Output directory is required.")
        sys.exit(1)
    
    # Step 5: Get Singularity image path
    singularity_image = questionary.path(
        "Enter the path to the Singularity image (.simg):",
        default=defaults.get('singularity_image', ''),
        validate=PathValidator()
    ).ask()
    if not singularity_image:
        print("Singularity image path is required.")
        sys.exit(1)
    
    # Step 6: Get FreeSurfer license file
    fs_license = questionary.path(
        "Enter the path to the FreeSurfer license file (license.txt):",
        default=defaults.get('fs_license', ''),
        validate=PathValidator()
    ).ask()
    if not fs_license:
        print("FreeSurfer license file path is required.")
        sys.exit(1)
    
    # **New Step 7: Get Work Directory**
    work_dir = questionary.path(
        "Enter the work directory (--work-dir):",
        default=defaults.get('work_dir', os.path.join(output_dir, 'work')),
        validate=PathValidator()
    ).ask()
    if not work_dir:
        print("Work directory is required.")
        sys.exit(1)
    
    # Step 8: Configure fMRIPrep parameters
    print("\nConfigure fMRIPrep parameters (press Enter to accept default values):\n")
    
    # Number of threads
    nthreads = questionary.text(
        "Number of threads (--nthreads)", 
        default=defaults.get('nthreads', "4")
    ).ask()
    
    # OMP threads
    omp_nthreads = questionary.text(
        "Number of OMP threads (--omp-nthreads)", 
        default=defaults.get('omp_nthreads', "2")
    ).ask()
    
    # Memory limit
    mem_mb = questionary.text(
        "Memory limit in MB (--mem_mb)", 
        default=defaults.get('mem_mb', "8000")
    ).ask()
    
    # Output spaces
    output_spaces = questionary.text(
        "Output spaces (--output-spaces)", 
        default=defaults.get('output_spaces', "MNI152NLin2009cAsym anat fsnative fsaverage5")
    ).ask()
    
    # Use AROMA
    use_aroma = questionary.confirm(
        "Use ICA-AROMA for denoising (--use-aroma)?", 
        default=defaults.get('use_aroma', "True").lower() == "true"
    ).ask()
    
    # Opt out of tracking
    notrack = questionary.confirm(
        "Opt out of sending tracking information (--notrack)?",
        default=defaults.get('notrack', "False").lower() == "true"
    ).ask()
    
    # **New Prompts Start Here**

    # Use SyN distortion correction
    use_syn_sdc = questionary.confirm(
        "Enable SyN distortion correction (--use-syn-sdc)?",
        default=defaults.get('use_syn_sdc', "False").lower() == "true"
    ).ask()
    
    # Skip BIDS validation
    skip_bids_validation = False  # Default value
    version = defaults.get('version', "1.1.8")
    if version != "1.1.8":
        skip_bids_validation = questionary.confirm(
            "Skip BIDS dataset validation (--skip_bids_validation)?",
            default=defaults.get('skip_bids_validation', "False").lower() == "true"
        ).ask()
    
    # Template resampling grid (only for version 1.1.8)
    template_resampling_grid = ""
    if version == "1.1.8":
        template_resampling_grid = questionary.text(
            "Template resampling grid (--template-resampling-grid)", 
            default=defaults.get('template_resampling_grid', "native")
        ).ask()
    
    # Disable FreeSurfer recon-all
    fs_no_reconall = questionary.confirm(
        "Disable FreeSurfer recon-all (--fs-no-reconall)?",
        default=defaults.get('fs_no_reconall', "False").lower() == "true"
    ).ask()
    
    # **New Prompts End Here**
    
    # Additional options
    additional_opts = questionary.text("Any additional fMRIPrep options (e.g., --ignore slicetiming)", default="").ask()
    
    # Step 9: Assemble the command
    # Construct participant labels
    participant_labels = ' '.join(selected_participants)
    
    # Prepare bind mounts
    bind_mounts = (
        f"-B {bids_dir}:/data "
        f"-B {output_dir}:/out "
        f"-B {fs_license}:/opt/freesurfer/license.txt "
        f"-B {work_dir}:/work "
    )
    
    # FreeSurfer license environment variable
    env_vars = "SINGULARITYENV_FS_LICENSE=/opt/freesurfer/license.txt"
    
    # TemplateFlow home (optional, can be customized)
    templateflow_home = os.path.join(os.path.expanduser("~"), ".cache", "templateflow")
    os.makedirs(templateflow_home, exist_ok=True)
    bind_mounts += f"-B {templateflow_home}:/templateflow "
    env_vars += " SINGULARITYENV_TEMPLATEFLOW_HOME=/templateflow"
    
    # Base Singularity command with work directory
    singularity_cmd = f"singularity run --cleanenv -w /work {bind_mounts} {singularity_image}"
    
    # fMRIPrep positional arguments
    fmriprep_cmd = "/data /out participant"
    
    # fMRIPrep named arguments
    named_args = f"--participant-label {participant_labels} --nthreads {nthreads} --omp-nthreads {omp_nthreads} --mem_mb {mem_mb} --output-spaces {output_spaces}"
    
    if use_aroma:
        named_args += " --use-aroma"
    
    if notrack:
        named_args += " --notrack"
    
    # **Adding New Options to named_args**

    if use_syn_sdc:
        named_args += " --use-syn-sdc"
    
    if fs_no_reconall:
        named_args += " --fs-no-reconall"
    
    if skip_bids_validation:
        named_args += " --skip_bids_validation"
    
    if template_resampling_grid:
        named_args += f" --template-resampling-grid {template_resampling_grid}"
    
    # **End of New Options**
    
    if additional_opts:
        named_args += f" {additional_opts}"
    
    # Full command
    full_cmd = f"{env_vars} {singularity_cmd} {fmriprep_cmd} {named_args}"
    
    # Optional: Wrap in a bash script
    script_content = f"""#!/bin/bash
# Generated by fMRIPrep Interactive Command Builder

{full_cmd}
"""
    
    # Step 10: Save the command to a shell script
    script_path = os.path.join(os.getcwd(), 'run_fmriprep.sh')
    with open(script_path, 'w') as script_file:
        script_file.write(script_content)
    
    # Make the script executable
    os.chmod(script_path, 0o755)
    
    print(f"\nCommand successfully saved to {script_path}")
    print("You can execute it by running:")
    print(f"bash {script_path}")

if __name__ == "__main__":
    try:
        import questionary
    except ImportError:
        print("The 'questionary' library is required. Install it using 'pip install questionary'")
        sys.exit(1)
    main()