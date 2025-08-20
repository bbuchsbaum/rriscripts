#!/usr/bin/env python3
"""
fmriprep_tui.py - Terminal User Interface for fMRIPrep Launcher

A browser-free, terminal-based GUI that works over SSH without X11 forwarding.

Requirements:
    pip install textual

Usage:
    python fmriprep_tui.py
"""

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import Button, Header, Footer, Input, Label, Select, Switch, Static, TextArea
from textual.screen import Screen
from textual import events
from pathlib import Path
import subprocess
import os
import sys

# Import functions from fmriprep_launcher
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from fmriprep_launcher import (
        discover_subjects, discover_sif_images,
        detect_runtime, default_resources_from_env, load_config
    )
except ImportError:
    print("Could not import fmriprep_launcher.py")
    sys.exit(1)


class FMRIPrepTUI(App):
    """Terminal UI for fMRIPrep Launcher"""
    
    CSS = """
    Screen {
        background: $surface;
    }
    
    Label {
        height: 1;
        margin: 1 0;
    }
    
    Input {
        margin: 1 0;
    }
    
    Button {
        margin: 1 0;
    }
    
    #sidebar {
        width: 30%;
        border-right: solid $primary;
        padding: 1;
    }
    
    #main {
        width: 70%;
        padding: 1;
    }
    
    .section-title {
        background: $primary;
        color: $text;
        text-align: center;
        text-style: bold;
        height: 3;
        content-align: center middle;
    }
    """
    
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("g", "generate", "Generate Script"),
        ("s", "save_config", "Save Config"),
    ]
    
    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.subjects = []
        self.selected_subjects = set()
        
    def compose(self) -> ComposeResult:
        """Create UI layout"""
        yield Header()
        
        with Horizontal():
            # Sidebar
            with Vertical(id="sidebar"):
                yield Static("📁 PATHS", classes="section-title")
                yield Label("BIDS Directory:")
                yield Input(
                    value=self.config.get('bids', ''),
                    placeholder="/path/to/bids",
                    id="bids_dir"
                )
                yield Label("Output Directory:")
                yield Input(
                    value=self.config.get('out', ''),
                    placeholder="/path/to/output",
                    id="out_dir"
                )
                yield Label("Work Directory:")
                yield Input(
                    value=self.config.get('work', '/scratch/work'),
                    placeholder="/scratch/work",
                    id="work_dir"
                )
                yield Label("FreeSurfer License:")
                yield Input(
                    value=self.config.get('fs_license', ''),
                    placeholder="/path/to/license.txt",
                    id="fs_license"
                )
                yield Label("TemplateFlow Directory:")
                yield Input(
                    value=self.config.get('templateflow_home', os.path.expanduser('~/.cache/templateflow')),
                    placeholder="~/.cache/templateflow",
                    id="templateflow_home"
                )
                yield Button("Scan for Subjects", id="scan_subjects")
            
            # Main area
            with ScrollableContainer(id="main"):
                yield Static("🎯 PROCESSING OPTIONS", classes="section-title")
                
                yield Label("Runtime:")
                yield Select(
                    [("Singularity", "singularity"),
                     ("Docker", "docker"),
                     ("fmriprep-docker", "fmriprep-docker")],
                    id="runtime",
                    value="singularity"
                )
                
                yield Label("Container:")
                yield Input(
                    value=self.config.get('container', 'auto'),
                    placeholder="auto or /path/to/container",
                    id="container"
                )
                
                yield Label("Processors (--nprocs):")
                cpus, mem = default_resources_from_env()
                yield Input(
                    value=str(self.config.get('nprocs', cpus)),
                    id="nprocs"
                )
                
                yield Label("OMP Threads:")
                yield Input(
                    value=str(self.config.get('omp_threads', 2)),
                    id="omp_threads"
                )
                
                yield Label("Memory (MB):")
                yield Input(
                    value=str(self.config.get('mem_mb', mem)),
                    id="mem_mb"
                )
                
                yield Static("⚙️ FMRIPREP OPTIONS", classes="section-title")
                
                yield Horizontal(
                    Switch(id="skip_bids", value=True),
                    Label("Skip BIDS Validation")
                )
                
                yield Horizontal(
                    Switch(id="use_aroma", value=False),
                    Label("Use ICA-AROMA")
                )
                
                yield Horizontal(
                    Switch(id="cifti_output", value=False),
                    Label("CIFTI Output (91k)")
                )
                
                yield Horizontal(
                    Switch(id="fs_reconall", value=False),
                    Label("Run FreeSurfer recon-all")
                )
                
                yield Horizontal(
                    Switch(id="use_syn_sdc", value=False),
                    Label("Use SyN SDC")
                )
                
                yield Label("Output Spaces:")
                yield Input(
                    value=self.config.get('output_spaces', 'MNI152NLin2009cAsym:res-2 T1w'),
                    placeholder="MNI152NLin2009cAsym:res-2 T1w",
                    id="output_spaces"
                )
                
                yield Static("💼 SLURM OPTIONS", classes="section-title")
                
                yield Horizontal(
                    Switch(id="use_slurm", value=True),
                    Label("Generate SLURM Script")
                )
                
                yield Label("Partition:")
                yield Input(
                    value=self.config.get('slurm_partition', 'compute'),
                    id="partition"
                )
                
                yield Label("Time (HH:MM:SS):")
                yield Input(
                    value=self.config.get('slurm_time', '24:00:00'),
                    id="time"
                )
                
                yield Label("Account:")
                yield Input(
                    value=self.config.get('slurm_account', ''),
                    id="account"
                )
                
                yield Label("Subjects per Job (batching):")
                yield Input(
                    value=str(self.config.get('subjects_per_job', 1)),
                    placeholder="1",
                    id="subjects_per_job"
                )
                
                yield Label("CPUs per Task:")
                yield Input(
                    value=str(self.config.get('slurm_cpus_per_task', '')),
                    placeholder="auto",
                    id="cpus_per_task"
                )
                
                yield Label("Memory (e.g., 32G, 760000M):")
                yield Input(
                    value=self.config.get('slurm_mem', ''),
                    placeholder="auto",
                    id="slurm_mem"
                )
                
                yield Horizontal(
                    Switch(id="no_mem", value=False),
                    Label("No memory specification (Trillium)")
                )
                
                yield Label("Email (optional):")
                yield Input(
                    value=self.config.get('slurm_email', ''),
                    placeholder="user@domain.com",
                    id="email"
                )
                
                yield Label("Mail Type (optional):")
                yield Input(
                    value=self.config.get('slurm_mail_type', ''),
                    placeholder="END,FAIL",
                    id="mail_type"
                )
                
                yield Label("Job Name:")
                yield Input(
                    value=self.config.get('slurm_job_name', 'fmriprep'),
                    placeholder="fmriprep",
                    id="job_name"
                )
                
                yield Label("Log Directory (optional):")
                yield Input(
                    value=self.config.get('slurm_log_dir', ''),
                    placeholder="auto (script_outdir/logs)",
                    id="log_dir"
                )
                
                yield Horizontal(
                    Switch(id="module_singularity", value=False),
                    Label("Add 'module load singularity'")
                )
                
                yield Label("Subject List:")
                yield TextArea(
                    id="subject_list",
                    disabled=True
                )
                
                yield Static("", id="status")
                
                yield Horizontal(
                    Button("Generate Script", variant="primary", id="generate"),
                    Button("Save Config", variant="default", id="save_config"),
                    Button("Quit", variant="error", id="quit")
                )
        
        yield Footer()
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "scan_subjects":
            self.scan_for_subjects()
        elif event.button.id == "generate":
            self.generate_script()
        elif event.button.id == "save_config":
            self.save_configuration()
        elif event.button.id == "quit":
            self.exit()
    
    def scan_for_subjects(self) -> None:
        """Scan BIDS directory for subjects"""
        bids_input = self.query_one("#bids_dir", Input)
        bids_dir = Path(bids_input.value)
        
        if bids_dir.exists():
            self.subjects = discover_subjects(bids_dir)
            subject_list = self.query_one("#subject_list", TextArea)
            if self.subjects:
                subject_list.load_text("\n".join(self.subjects))
                subject_list.disabled = False
                status = self.query_one("#status", Static)
                status.update(f"✅ Found {len(self.subjects)} subjects")
            else:
                status = self.query_one("#status", Static)
                status.update("❌ No subjects found")
        else:
            status = self.query_one("#status", Static)
            status.update("❌ BIDS directory does not exist")
    
    def generate_script(self) -> None:
        """Generate fMRIPrep script"""
        # Gather all values
        bids_dir = self.query_one("#bids_dir", Input).value
        out_dir = self.query_one("#out_dir", Input).value
        work_dir = self.query_one("#work_dir", Input).value
        fs_license = self.query_one("#fs_license", Input).value
        templateflow_home = self.query_one("#templateflow_home", Input).value
        
        runtime = self.query_one("#runtime", Select).value
        container = self.query_one("#container", Input).value
        
        nprocs = self.query_one("#nprocs", Input).value
        omp_threads = self.query_one("#omp_threads", Input).value
        mem_mb = self.query_one("#mem_mb", Input).value
        
        skip_bids = self.query_one("#skip_bids", Switch).value
        use_aroma = self.query_one("#use_aroma", Switch).value
        cifti_output = self.query_one("#cifti_output", Switch).value
        fs_reconall = self.query_one("#fs_reconall", Switch).value
        use_syn_sdc = self.query_one("#use_syn_sdc", Switch).value
        output_spaces = self.query_one("#output_spaces", Input).value
        
        use_slurm = self.query_one("#use_slurm", Switch).value
        partition = self.query_one("#partition", Input).value
        time = self.query_one("#time", Input).value
        account = self.query_one("#account", Input).value
        subjects_per_job = self.query_one("#subjects_per_job", Input).value
        cpus_per_task = self.query_one("#cpus_per_task", Input).value
        slurm_mem = self.query_one("#slurm_mem", Input).value
        no_mem = self.query_one("#no_mem", Switch).value
        email = self.query_one("#email", Input).value
        mail_type = self.query_one("#mail_type", Input).value
        job_name = self.query_one("#job_name", Input).value
        log_dir = self.query_one("#log_dir", Input).value
        module_singularity = self.query_one("#module_singularity", Switch).value
        
        subject_list = self.query_one("#subject_list", TextArea).text
        subjects = [s.strip() for s in subject_list.split("\n") if s.strip()]
        
        if not subjects:
            subjects = ["all"]
        
        # Build command
        cmd = [
            "python", "fmriprep_launcher.py",
            "slurm-array" if use_slurm else "print-cmd",
            "--bids", bids_dir,
            "--out", out_dir,
            "--work", work_dir,
            "--subjects"] + subjects + [
            "--runtime", runtime,
            "--container", container,
            "--fs-license", fs_license,
            "--nprocs", nprocs,
            "--omp-threads", omp_threads,
            "--mem-mb", mem_mb
        ]
        
        if templateflow_home:
            cmd.extend(["--templateflow-home", templateflow_home])
        
        if skip_bids:
            cmd.append("--skip-bids-validation")
        if output_spaces:
            cmd.extend(["--output-spaces", output_spaces])
        if use_aroma:
            cmd.append("--use-aroma")
        if cifti_output:
            cmd.append("--cifti-output")
        if fs_reconall:
            cmd.append("--fs-reconall")
        if use_syn_sdc:
            cmd.append("--use-syn-sdc")
        
        if use_slurm:
            cmd.extend([
                "--partition", partition,
                "--time", time,
            ])
            if account:
                cmd.extend(["--account", account])
            if subjects_per_job and subjects_per_job != "1":
                cmd.extend(["--subjects-per-job", subjects_per_job])
            if cpus_per_task:
                cmd.extend(["--cpus-per-task", cpus_per_task])
            if no_mem:
                cmd.append("--no-mem")
            elif slurm_mem:
                cmd.extend(["--mem", slurm_mem])
            if email:
                cmd.extend(["--email", email])
            if mail_type:
                cmd.extend(["--mail-type", mail_type])
            if job_name:
                cmd.extend(["--job-name", job_name])
            if log_dir:
                cmd.extend(["--log-dir", log_dir])
            if module_singularity:
                cmd.append("--module-singularity")
        
        # Execute
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
            
            status = self.query_one("#status", Static)
            if result.returncode == 0:
                status.update("✅ Script generated successfully! Check fmriprep_job/")
            else:
                status.update(f"❌ Error: {result.stderr[:100]}")
        except Exception as e:
            status = self.query_one("#status", Static)
            status.update(f"❌ Error: {str(e)[:100]}")
    
    def save_configuration(self) -> None:
        """Save current settings to config file"""
        config_content = f"""[defaults]
bids = {self.query_one("#bids_dir", Input).value}
out = {self.query_one("#out_dir", Input).value}
work = {self.query_one("#work_dir", Input).value}
fs_license = {self.query_one("#fs_license", Input).value}
templateflow_home = {self.query_one("#templateflow_home", Input).value}
runtime = {self.query_one("#runtime", Select).value}
container = {self.query_one("#container", Input).value}
nprocs = {self.query_one("#nprocs", Input).value}
omp_threads = {self.query_one("#omp_threads", Input).value}
mem_mb = {self.query_one("#mem_mb", Input).value}
skip_bids_validation = {str(self.query_one("#skip_bids", Switch).value).lower()}
use_aroma = {str(self.query_one("#use_aroma", Switch).value).lower()}
cifti_output = {str(self.query_one("#cifti_output", Switch).value).lower()}
fs_reconall = {str(self.query_one("#fs_reconall", Switch).value).lower()}
use_syn_sdc = {str(self.query_one("#use_syn_sdc", Switch).value).lower()}
output_spaces = {self.query_one("#output_spaces", Input).value}

[slurm]
partition = {self.query_one("#partition", Input).value}
time = {self.query_one("#time", Input).value}
account = {self.query_one("#account", Input).value}
subjects_per_job = {self.query_one("#subjects_per_job", Input).value}
cpus_per_task = {self.query_one("#cpus_per_task", Input).value}
mem = {self.query_one("#slurm_mem", Input).value}
no_mem = {str(self.query_one("#no_mem", Switch).value).lower()}
email = {self.query_one("#email", Input).value}
mail_type = {self.query_one("#mail_type", Input).value}
job_name = {self.query_one("#job_name", Input).value}
log_dir = {self.query_one("#log_dir", Input).value}
module_singularity = {str(self.query_one("#module_singularity", Switch).value).lower()}
"""
        with open("fmriprep.ini", "w") as f:
            f.write(config_content)
        
        status = self.query_one("#status", Static)
        status.update("✅ Configuration saved to fmriprep.ini")


if __name__ == "__main__":
    app = FMRIPrepTUI()
    app.run()