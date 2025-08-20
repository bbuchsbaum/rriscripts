#!/usr/bin/env python3
"""
fmriprep_tui_autocomplete.py - TUI with Tab Completion for fMRIPrep Launcher

Enhanced version with tab completion for file/directory paths.

Requirements:
    pip install textual

Usage:
    python fmriprep_tui_autocomplete.py
"""

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import (
    Button, Header, Footer, Input, Label, Select, Switch, Static, TextArea,
    DataTable, TabbedContent, TabPane, ProgressBar, Rule
)
from textual.reactive import reactive
from textual import events
from textual.message import Message
from pathlib import Path
import subprocess
import os
import sys
from typing import List, Set, Optional
import glob

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


class PathInput(Input):
    """Custom Input widget with path completion support"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.suggestions: List[str] = []
        self.suggestion_index = 0
        self.original_value = ""
        self.showing_suggestions = False
    
    async def on_key(self, event: events.Key) -> None:
        """Handle key events for tab completion"""
        if event.key == "tab":
            event.prevent_default()
            await self.handle_tab_completion()
        elif event.key == "escape" and self.showing_suggestions:
            # Cancel completion and restore original value
            self.value = self.original_value
            self.showing_suggestions = False
            self.suggestions = []
        else:
            # Reset suggestions on any other key
            if self.showing_suggestions:
                self.showing_suggestions = False
                self.suggestions = []
    
    async def handle_tab_completion(self) -> None:
        """Handle tab key for path completion"""
        current_value = self.value
        
        if not self.showing_suggestions:
            # Start new completion
            self.original_value = current_value
            self.suggestions = self.get_path_completions(current_value)
            self.suggestion_index = 0
            
            if self.suggestions:
                self.showing_suggestions = True
                if len(self.suggestions) == 1:
                    # Single match - complete it
                    self.value = self.suggestions[0]
                    self.showing_suggestions = False
                    self.suggestions = []
                else:
                    # Multiple matches - show first one
                    self.value = self.suggestions[0]
                    # Show status with number of matches
                    status_msg = f"Tab: {len(self.suggestions)} matches. Press Tab to cycle, Enter to accept, Esc to cancel"
                    if hasattr(self.app, 'update_status'):
                        self.app.update_status(status_msg)
        else:
            # Cycle through suggestions
            self.suggestion_index = (self.suggestion_index + 1) % len(self.suggestions)
            self.value = self.suggestions[self.suggestion_index]
    
    def get_path_completions(self, partial_path: str) -> List[str]:
        """Get path completions for the given partial path"""
        if not partial_path:
            # If empty, start from current directory
            partial_path = "./"
        
        # Expand user home directory
        partial_path = os.path.expanduser(partial_path)
        
        # Handle absolute vs relative paths
        if partial_path.startswith('/'):
            base_path = partial_path
        else:
            base_path = partial_path
        
        # Add wildcard for completion
        if os.path.isdir(base_path) and not base_path.endswith('/'):
            # If it's a directory without trailing slash, add it
            pattern = base_path + '/*'
        else:
            # Otherwise add wildcard to complete the last component
            pattern = base_path + '*'
        
        # Get matches
        matches = glob.glob(pattern)
        
        # Sort and format matches
        completions = []
        for match in sorted(matches):
            if os.path.isdir(match):
                # Add trailing slash for directories
                if not match.endswith('/'):
                    match += '/'
            completions.append(match)
        
        # If no matches, return original
        if not completions:
            return [partial_path]
        
        return completions


class FMRIPrepAutocompleteTUI(App):
    """Terminal UI with tab completion for fMRIPrep Launcher"""
    
    CSS = """
    Screen {
        background: $surface;
    }
    
    TabbedContent {
        height: 100%;
    }
    
    Label {
        height: 1;
        margin: 0 0 1 0;
    }
    
    Input, PathInput {
        margin: 0 0 1 0;
    }
    
    Button {
        margin: 1 0;
    }
    
    .section-title {
        background: $primary;
        color: $text;
        text-align: center;
        text-style: bold;
        height: 3;
        content-align: center middle;
        margin: 1 0;
    }
    
    .help-text {
        color: $text-muted;
        text-style: italic;
        margin: 0 0 1 0;
    }
    
    #subject_table {
        height: 20;
        margin: 1 0;
    }
    
    #status_bar {
        dock: bottom;
        height: 3;
        background: $boost;
        border-top: solid $primary;
        padding: 1;
    }
    
    .preset-button {
        width: 20;
        margin: 0 1;
    }
    
    .completion-hint {
        color: $success;
        text-style: italic;
        height: 1;
    }
    """
    
    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+g", "generate", "Generate Script"),
        ("ctrl+s", "save_config", "Save Config"),
        ("ctrl+l", "load_config", "Load Config"),
        ("f1", "show_help", "Help"),
    ]
    
    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.subjects = []
        self.selected_subjects = set()
        self.container_paths = []
        
    def compose(self) -> ComposeResult:
        """Create enhanced UI layout"""
        yield Header()
        
        with TabbedContent(initial="paths"):
            # Paths Tab
            with TabPane("📁 Paths & Data", id="paths"):
                yield from self._compose_paths_tab()
            
            # Processing Tab
            with TabPane("⚙️ Processing", id="processing"):
                yield from self._compose_processing_tab()
            
            # SLURM Tab
            with TabPane("💼 SLURM/HPC", id="slurm"):
                yield from self._compose_slurm_tab()
            
            # Subjects Tab
            with TabPane("👥 Subjects", id="subjects"):
                yield from self._compose_subjects_tab()
            
            # Advanced Tab
            with TabPane("🔧 Advanced", id="advanced"):
                yield from self._compose_advanced_tab()
        
        # Status bar
        with Container(id="status_bar"):
            yield Static("Ready | Press Tab in path fields for auto-completion", id="status")
            progress = ProgressBar(total=100, show_eta=False, id="progress")
            progress.display = False
            yield progress
        
        yield Footer()
    
    def _compose_paths_tab(self) -> ComposeResult:
        """Compose the Paths tab with autocomplete inputs"""
        with ScrollableContainer():
            yield Static("Essential Paths", classes="section-title")
            yield Static("💡 Tip: Press Tab to auto-complete paths", classes="completion-hint")
            
            yield Label("BIDS Directory:")
            yield PathInput(
                value=self.config.get('bids', ''),
                placeholder="/path/to/bids",
                id="bids_dir"
            )
            yield Static("Path to your BIDS-formatted dataset", classes="help-text")
            
            yield Label("Output Directory:")
            yield PathInput(
                value=self.config.get('out', ''),
                placeholder="/path/to/output",
                id="out_dir"
            )
            yield Static("Where fMRIPrep outputs will be saved", classes="help-text")
            
            yield Label("Work Directory:")
            yield PathInput(
                value=self.config.get('work', '/scratch/work'),
                placeholder="/scratch/work",
                id="work_dir"
            )
            yield Static("Temporary working directory (needs lots of space)", classes="help-text")
            
            yield Label("FreeSurfer License:")
            yield PathInput(
                value=self.config.get('fs_license', ''),
                placeholder="/path/to/license.txt",
                id="fs_license"
            )
            yield Static("Path to FreeSurfer license file", classes="help-text")
            
            yield Label("TemplateFlow Directory:")
            yield PathInput(
                value=self.config.get('templateflow_home', os.path.expanduser('~/.cache/templateflow')),
                placeholder="~/.cache/templateflow",
                id="templateflow_home"
            )
            yield Static("Pre-downloaded templates directory", classes="help-text")
            
            yield Rule()
            
            with Horizontal():
                yield Button("Scan for Subjects", variant="primary", id="scan_subjects")
                yield Button("Detect Containers", variant="default", id="detect_containers")
    
    def _compose_processing_tab(self) -> ComposeResult:
        """Compose the Processing tab"""
        with ScrollableContainer():
            yield Static("Runtime Configuration", classes="section-title")
            
            yield Label("Container Runtime:")
            yield Select(
                [("Singularity/Apptainer", "singularity"),
                 ("Docker", "docker"),
                 ("fmriprep-docker", "fmriprep-docker")],
                id="runtime",
                value="singularity"
            )
            
            yield Label("Container Image:")
            yield PathInput(
                value=self.config.get('container', 'auto'),
                placeholder="auto or /path/to/container.sif",
                id="container"
            )
            yield Static("Use 'auto' to find latest, or specify path (Tab to complete)", classes="help-text")
            
            yield Rule()
            yield Static("Resource Allocation", classes="section-title")
            
            cpus, mem = default_resources_from_env()
            
            yield Label(f"Processors (--nprocs) [Detected: {cpus}]:")
            yield Input(
                value=str(self.config.get('nprocs', cpus)),
                id="nprocs"
            )
            
            yield Label("OMP Threads per processor:")
            yield Input(
                value=str(self.config.get('omp_threads', 2)),
                id="omp_threads"
            )
            
            yield Label(f"Memory in MB [Detected: {mem}]:")
            yield Input(
                value=str(self.config.get('mem_mb', mem)),
                id="mem_mb"
            )
            
            yield Rule()
            yield Static("fMRIPrep Options", classes="section-title")
            
            with Vertical():
                yield Horizontal(
                    Switch(id="skip_bids", value=True),
                    Label("Skip BIDS Validation (faster)")
                )
                yield Horizontal(
                    Switch(id="use_aroma", value=False),
                    Label("Use ICA-AROMA denoising")
                )
                yield Horizontal(
                    Switch(id="cifti_output", value=False),
                    Label("Generate CIFTI outputs (91k)")
                )
                yield Horizontal(
                    Switch(id="fs_reconall", value=False),
                    Label("Run FreeSurfer recon-all")
                )
                yield Horizontal(
                    Switch(id="use_syn_sdc", value=False),
                    Label("Use SyN SDC for fieldmap-less correction")
                )
            
            yield Label("Output Spaces (space-separated):")
            yield Input(
                value=self.config.get('output_spaces', 'MNI152NLin2009cAsym:res-2 T1w'),
                placeholder="MNI152NLin2009cAsym:res-2 T1w",
                id="output_spaces"
            )
            yield Static("Standard spaces: MNI152NLin2009cAsym, MNI152NLin6Asym, fsaverage", classes="help-text")
    
    def _compose_slurm_tab(self) -> ComposeResult:
        """Compose the SLURM tab"""
        with ScrollableContainer():
            yield Static("SLURM Configuration", classes="section-title")
            
            yield Horizontal(
                Switch(id="use_slurm", value=True),
                Label("Generate SLURM Script")
            )
            
            yield Rule()
            
            # Quick presets
            yield Static("Quick Presets", classes="section-title")
            with Horizontal():
                yield Button("Small Job", classes="preset-button", id="preset_small")
                yield Button("Medium Job", classes="preset-button", id="preset_medium")
                yield Button("Large Job", classes="preset-button", id="preset_large")
            
            yield Rule()
            
            yield Label("Partition:")
            yield Input(
                value=self.config.get('slurm_partition', 'compute'),
                placeholder="compute",
                id="partition"
            )
            
            yield Label("Time Limit (HH:MM:SS):")
            yield Input(
                value=self.config.get('slurm_time', '24:00:00'),
                placeholder="24:00:00",
                id="time"
            )
            
            yield Label("Account (leave empty if not required):")
            yield Input(
                value=self.config.get('slurm_account', ''),
                placeholder="rrg-username",
                id="account"
            )
            
            yield Label("Subjects per Job (batching):")
            yield Input(
                value=str(self.config.get('subjects_per_job', 1)),
                placeholder="1",
                id="subjects_per_job"
            )
            yield Static("Process multiple subjects in one job for efficiency", classes="help-text")
            
            yield Label("CPUs per Task:")
            yield Input(
                value=str(self.config.get('slurm_cpus_per_task', '')),
                placeholder="auto",
                id="cpus_per_task"
            )
            
            yield Label("Memory (e.g., 32G, 64000M):")
            yield Input(
                value=self.config.get('slurm_mem', ''),
                placeholder="auto",
                id="slurm_mem"
            )
            
            yield Horizontal(
                Switch(id="no_mem", value=False),
                Label("No memory specification (some clusters)")
            )
            
            yield Rule()
            yield Static("Notifications", classes="section-title")
            
            yield Label("Email (optional):")
            yield Input(
                value=self.config.get('slurm_email', ''),
                placeholder="user@domain.com",
                id="email"
            )
            
            yield Label("Mail Events (END, FAIL, BEGIN, etc.):")
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
            
            yield Label("Log Directory:")
            yield PathInput(
                value=self.config.get('slurm_log_dir', ''),
                placeholder="auto (output_dir/logs)",
                id="log_dir"
            )
            
            yield Horizontal(
                Switch(id="module_singularity", value=False),
                Label("Add 'module load singularity' to script")
            )
    
    def _compose_subjects_tab(self) -> ComposeResult:
        """Compose the Subjects tab"""
        with Vertical():
            yield Static("Subject Selection", classes="section-title")
            yield Static("Select subjects to process (click to toggle)", classes="help-text")
            
            yield DataTable(id="subject_table")
            
            with Horizontal():
                yield Button("Select All", id="select_all")
                yield Button("Select None", id="select_none")
                yield Button("Refresh", id="refresh_subjects")
            
            yield Label("Custom subject list (one per line, overrides table):")
            yield TextArea(
                id="subject_list",
                language="text"
            )
    
    def _compose_advanced_tab(self) -> ComposeResult:
        """Compose the Advanced tab"""
        with ScrollableContainer():
            yield Static("Advanced Options", classes="section-title")
            
            yield Label("Additional fMRIPrep arguments:")
            yield Input(
                value=self.config.get('extra_args', ''),
                placeholder="--ignore fieldmaps --low-mem",
                id="extra_args"
            )
            
            yield Rule()
            yield Static("Action Buttons", classes="section-title")
            
            with Horizontal():
                yield Button("Generate Script", variant="primary", id="generate")
                yield Button("Save Config", variant="success", id="save_config")
                yield Button("Load Config", variant="default", id="load_config_btn")
                yield Button("Quit", variant="error", id="quit")
    
    def on_mount(self) -> None:
        """Initialize the data table when mounted"""
        table = self.query_one("#subject_table", DataTable)
        table.add_columns("✓", "Subject ID", "Status")
        table.cursor_type = "row"
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        button_id = event.button.id
        
        if button_id == "scan_subjects":
            self.scan_for_subjects()
        elif button_id == "detect_containers":
            self.detect_containers()
        elif button_id == "generate":
            self.generate_script()
        elif button_id == "save_config":
            self.save_configuration()
        elif button_id == "load_config_btn":
            self.load_configuration()
        elif button_id == "quit":
            self.exit()
        elif button_id == "select_all":
            self.select_all_subjects()
        elif button_id == "select_none":
            self.select_no_subjects()
        elif button_id == "refresh_subjects":
            self.scan_for_subjects()
        elif button_id == "preset_small":
            self.apply_preset("small")
        elif button_id == "preset_medium":
            self.apply_preset("medium")
        elif button_id == "preset_large":
            self.apply_preset("large")
    
    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle subject selection in data table"""
        table = self.query_one("#subject_table", DataTable)
        row_key = event.row_key
        
        if row_key in self.selected_subjects:
            self.selected_subjects.remove(row_key)
            table.update_cell(row_key, "✓", "")
        else:
            self.selected_subjects.add(row_key)
            table.update_cell(row_key, "✓", "✓")
    
    def scan_for_subjects(self) -> None:
        """Scan BIDS directory for subjects"""
        bids_input = self.query_one("#bids_dir", PathInput)
        bids_dir = Path(bids_input.value)
        
        if bids_dir.exists():
            self.subjects = discover_subjects(bids_dir)
            table = self.query_one("#subject_table", DataTable)
            
            # Clear existing rows
            table.clear()
            
            if self.subjects:
                for subject in self.subjects:
                    table.add_row("", subject, "Ready", key=subject)
                
                self.update_status(f"✅ Found {len(self.subjects)} subjects")
            else:
                self.update_status("❌ No subjects found")
        else:
            self.update_status("❌ BIDS directory does not exist")
    
    def detect_containers(self) -> None:
        """Detect available container images"""
        runtime = self.query_one("#runtime", Select).value
        
        if runtime == "singularity":
            # Look for .sif files
            search_paths = [
                Path.home() / ".singularity",
                Path("/scratch/containers"),
                Path.cwd()
            ]
            
            containers = []
            for path in search_paths:
                if path.exists():
                    containers.extend(path.glob("*fmriprep*.sif"))
            
            if containers:
                # Update container input with the most recent one
                latest = max(containers, key=lambda p: p.stat().st_mtime)
                container_input = self.query_one("#container", PathInput)
                container_input.value = str(latest)
                self.update_status(f"✅ Found {len(containers)} container(s), selected: {latest.name}")
            else:
                self.update_status("ℹ️ No containers found, will use 'auto' to download")
    
    def select_all_subjects(self) -> None:
        """Select all subjects"""
        table = self.query_one("#subject_table", DataTable)
        for subject in self.subjects:
            self.selected_subjects.add(subject)
            table.update_cell(subject, "✓", "✓")
    
    def select_no_subjects(self) -> None:
        """Deselect all subjects"""
        table = self.query_one("#subject_table", DataTable)
        self.selected_subjects.clear()
        for subject in self.subjects:
            table.update_cell(subject, "✓", "")
    
    def apply_preset(self, preset: str) -> None:
        """Apply a resource preset"""
        if preset == "small":
            self.query_one("#nprocs", Input).value = "4"
            self.query_one("#mem_mb", Input).value = "16000"
            self.query_one("#time", Input).value = "12:00:00"
            self.update_status("Applied small job preset (4 cores, 16GB, 12h)")
        elif preset == "medium":
            self.query_one("#nprocs", Input).value = "8"
            self.query_one("#mem_mb", Input).value = "32000"
            self.query_one("#time", Input).value = "24:00:00"
            self.update_status("Applied medium job preset (8 cores, 32GB, 24h)")
        elif preset == "large":
            self.query_one("#nprocs", Input).value = "16"
            self.query_one("#mem_mb", Input).value = "64000"
            self.query_one("#time", Input).value = "48:00:00"
            self.update_status("Applied large job preset (16 cores, 64GB, 48h)")
    
    def generate_script(self) -> None:
        """Generate fMRIPrep script"""
        # Show progress
        progress = self.query_one("#progress", ProgressBar)
        progress.display = True
        progress.update(progress=0)
        
        # Gather all values - use PathInput for path fields
        bids_dir = self.query_one("#bids_dir", PathInput).value
        out_dir = self.query_one("#out_dir", PathInput).value
        work_dir = self.query_one("#work_dir", PathInput).value
        fs_license = self.query_one("#fs_license", PathInput).value
        templateflow_home = self.query_one("#templateflow_home", PathInput).value
        
        runtime = self.query_one("#runtime", Select).value
        container = self.query_one("#container", PathInput).value
        
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
        log_dir = self.query_one("#log_dir", PathInput).value
        module_singularity = self.query_one("#module_singularity", Switch).value
        
        extra_args = self.query_one("#extra_args", Input).value
        
        # Get subjects
        subject_list_text = self.query_one("#subject_list", TextArea).text
        if subject_list_text.strip():
            subjects = [s.strip() for s in subject_list_text.split("\n") if s.strip()]
        elif self.selected_subjects:
            subjects = list(self.selected_subjects)
        else:
            subjects = ["all"]
        
        progress.update(progress=25)
        
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
        
        if extra_args:
            cmd.extend(["--extra-args", extra_args])
        
        progress.update(progress=50)
        
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
        
        progress.update(progress=75)
        
        # Execute
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
            
            progress.update(progress=100)
            
            if result.returncode == 0:
                self.update_status("✅ Script generated successfully! Check fmriprep_job/")
            else:
                self.update_status(f"❌ Error: {result.stderr[:100]}")
        except Exception as e:
            self.update_status(f"❌ Error: {str(e)[:100]}")
        finally:
            progress.display = False
    
    def save_configuration(self) -> None:
        """Save current settings to config file"""
        config_content = f"""[defaults]
bids = {self.query_one("#bids_dir", PathInput).value}
out = {self.query_one("#out_dir", PathInput).value}
work = {self.query_one("#work_dir", PathInput).value}
fs_license = {self.query_one("#fs_license", PathInput).value}
templateflow_home = {self.query_one("#templateflow_home", PathInput).value}
runtime = {self.query_one("#runtime", Select).value}
container = {self.query_one("#container", PathInput).value}
nprocs = {self.query_one("#nprocs", Input).value}
omp_threads = {self.query_one("#omp_threads", Input).value}
mem_mb = {self.query_one("#mem_mb", Input).value}
skip_bids_validation = {str(self.query_one("#skip_bids", Switch).value).lower()}
use_aroma = {str(self.query_one("#use_aroma", Switch).value).lower()}
cifti_output = {str(self.query_one("#cifti_output", Switch).value).lower()}
fs_reconall = {str(self.query_one("#fs_reconall", Switch).value).lower()}
use_syn_sdc = {str(self.query_one("#use_syn_sdc", Switch).value).lower()}
output_spaces = {self.query_one("#output_spaces", Input).value}
extra_args = {self.query_one("#extra_args", Input).value}

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
log_dir = {self.query_one("#log_dir", PathInput).value}
module_singularity = {str(self.query_one("#module_singularity", Switch).value).lower()}
"""
        with open("fmriprep.ini", "w") as f:
            f.write(config_content)
        
        self.update_status("✅ Configuration saved to fmriprep.ini")
    
    def load_configuration(self) -> None:
        """Reload configuration from file"""
        self.config = load_config()
        self.update_status("✅ Configuration loaded from fmriprep.ini")
        # TODO: Update all inputs with loaded values
    
    def update_status(self, message: str) -> None:
        """Update status bar message"""
        status = self.query_one("#status", Static)
        status.update(message)


if __name__ == "__main__":
    app = FMRIPrepAutocompleteTUI()
    app.run()