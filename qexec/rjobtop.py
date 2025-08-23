#!/usr/bin/env python3

"""
rjobtop — focus view of a Slurm job's CPU+Memory utilization (great for R/future.apply/callr forks)

Why this exists
---------------
`top`/`htop` are great but noisy when R spawns short-lived workers. rjobtop zooms in on *your job*
and shows:
  • Total CPU in "core-equivalents" (e.g., 153.2 cores out of 192)
  • Total memory (cgroup-aware if available; otherwise RSS sum)
  • Process count and fork rate (how many new workers/sec)
  • A compact table of the hottest processes (CPU cores & RSS)
  • Tiny ASCII sparklines for CPU and memory
  • Works per-job, per-step, or by PID subtree; filters to R processes if desired

Dependencies: Python 3.7+, Linux with /proc. No root required. No psutil needed.

Typical usage
-------------
  # best: run on a compute node where the job is running
  rjobtop --job 123456
  rjobtop --job 123456 --interval 0.5
  rjobtop --job 123456 --pattern 'R|Rscript|callr'    # only show these in the table (aggregates still use all)
  rjobtop --once --job 123456                         # one-shot textual snapshot, no curses UI
  rjobtop --pid 98765                                 # monitor a PID subtree (e.g., your Rscript launcher)

Inside an srun shell on the node, you can often omit --job:
  srun --pty bash
  rjobtop                     # auto-detect SLURM_JOB_ID / SLURM_STEP_ID

Keys in the UI
--------------
  q           Quit
  a           Toggle All-process vs. Pattern-filtered table view
  r           Toggle R-focused default pattern (R|Rscript|callr|Rterm)
  c           Toggle cgroup memory read (if available) vs. RSS-sum
  1 / 2       Change update interval (x0.5 / x2)
  p           Toggle per-process table sorting (CPU vs RSS)

Notes & caveats
---------------
  * CPU numbers are "core-equivalents": 1.00 == one full core saturated for the interval.
    Summing over processes equals the total cores your job is using on this node.
  * Sum of per-process RSS double-counts shared memory. cgroup memory (when available) avoids that.
  * If your job spans multiple nodes, run rjobtop on each node separately (or via `srun -N... rjobtop --job ...`).
  * Short-lived workers: fork rate shows "births/sec". The table may not catch a worker that
    lived < the refresh interval, but the CPU/Memory aggregates *do*.
"""

import argparse
import curses
import functools
import logging
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from collections import defaultdict, deque, namedtuple
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple, TypeVar, Callable

# System constants
CLK_TCK = os.sysconf(os.sysconf_names['SC_CLK_TCK'])
PAGESIZE = os.sysconf('SC_PAGE_SIZE')
BOOT_TIME = None  # seconds since epoch

# Configuration constants
DEFAULT_INTERVAL = 1.0
MIN_INTERVAL = 0.1
MAX_INTERVAL = 5.0
HISTORY_SIZE = 180
MAX_SAMPLE_PIDS = 200
MAX_TABLE_ROWS = 30
DEFAULT_TERMINAL = 'xterm-256color'
DEFAULT_R_PATTERN = r'R|Rscript|callr|Rterm'
SPARK_CHARS = "▁▂▃▄▅▆▇█"
INTERVAL_MULTIPLIER = 0.5  # for speed decrease
INTERVAL_DIVISOR = 2.0  # for speed increase
FORK_RATE_EMA_NEW = 0.3  # weight for new samples
FORK_RATE_EMA_OLD = 0.7  # weight for old samples
MAX_RETRIES = 3  # Maximum retry attempts for transient failures
RETRY_DELAY = 0.01  # Delay between retries in seconds

# Setup logging
log_file = Path.home() / '.rjobtop.log'
logging.basicConfig(
    filename=str(log_file),
    level=logging.WARNING,
    format='%(asctime)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
)

# Type variable for decorator
T = TypeVar('T')

def retry_on_failure(max_retries: int = MAX_RETRIES, 
                     delay: float = RETRY_DELAY,
                     exceptions: tuple = (IOError, OSError)) -> Callable:
    """Decorator to retry function calls on transient failures."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logging.debug(f"Retry {attempt + 1}/{max_retries} for {func.__name__}: {e}")
                        time.sleep(delay)
                    else:
                        logging.debug(f"Final attempt failed for {func.__name__}: {e}")
            # If we get here, all retries failed
            if last_exception:
                raise last_exception
            return None
        return wrapper
    return decorator

def read_boot_time() -> float:
    global BOOT_TIME
    if BOOT_TIME is not None:
        return BOOT_TIME
    try:
        with open('/proc/stat','r') as f:
            for line in f:
                if line.startswith('btime '):
                    BOOT_TIME = float(line.split()[1])
                    return BOOT_TIME
    except (FileNotFoundError, PermissionError) as e:
        logging.warning(f"Cannot read /proc/stat: {e}")
    except Exception as e:
        logging.error(f"Error reading boot time from /proc/stat: {e}")
    
    # fallback: time.time() - uptime
    try:
        with open('/proc/uptime','r') as f:
            up = float(f.read().split()[0])
            BOOT_TIME = time.time() - up
            return BOOT_TIME
    except Exception as e:
        logging.error(f"Failed to determine boot time: {e}")
        BOOT_TIME = time.time()  # Better fallback than 0.0
        return BOOT_TIME

@dataclass
class ProcSample:
    pid: int
    ppid: int
    comm: str
    cpu_ticks: int  # utime+stime
    rss_bytes: int
    vms_bytes: int
    start_ticks: int  # since boot
    cmdline: str

def parse_stat(path: str) -> Optional[Tuple[int, str, int, int, int, int]]:
    """Return (pid, comm, ppid, utime, stime, starttime) from /proc/<pid>/stat"""
    try:
        with open(path, 'r') as f:
            s = f.read().rstrip()
        # comm may include spaces and is wrapped in parentheses
        lpar = s.find('(')
        rpar = s.rfind(')')
        if lpar < 0 or rpar < 0 or rpar < lpar:
            logging.debug(f"Invalid stat format in {path}")
            return None
        before = s[:lpar].strip().split()
        after = s[rpar+1:].strip().split()
        pid = int(before[0])
        comm = s[lpar+1:rpar]
        ppid = int(after[1])  # field 4
        utime = int(after[11])  # field 14
        stime = int(after[12])  # field 15
        starttime = int(after[19])  # field 22
        return pid, comm, ppid, utime, stime, starttime
    except FileNotFoundError:
        # Process disappeared - this is normal
        return None
    except (IndexError, ValueError) as e:
        logging.debug(f"Failed to parse stat {path}: {e}")
        return None
    except Exception as e:
        logging.error(f"Unexpected error parsing stat {path}: {e}")
        return None

def read_cmdline(pid: int) -> str:
    try:
        with open(f'/proc/{pid}/cmdline','rb') as f:
            data = f.read()
        if not data:
            return ""
        parts = data.split(b'\x00')
        return ' '.join(shlex.quote(p.decode('utf-8', 'replace')) for p in parts if p)
    except FileNotFoundError:
        # Process disappeared
        return ""
    except PermissionError:
        logging.debug(f"Permission denied reading cmdline for PID {pid}")
        return ""
    except Exception as e:
        logging.debug(f"Error reading cmdline for PID {pid}: {e}")
        return ""

@retry_on_failure(max_retries=2, exceptions=(IOError, OSError))
def read_status_rss_bytes(pid: int) -> int:
    # Prefer /proc/<pid>/statm or /proc/<pid>/stat (rss pages), converts to bytes.
    try:
        with open(f'/proc/{pid}/stat', 'r') as f:
            s = f.read().rstrip()
        rpar = s.rfind(')')
        after = s[rpar+1:].strip().split()
        rss_pages = int(after[21])  # field 24
        return rss_pages * PAGESIZE
    except Exception:
        # Fallback to parsing VmRSS in /proc/<pid>/status (kB)
        try:
            with open(f'/proc/{pid}/status','r') as f:
                for line in f:
                    if line.startswith('VmRSS:'):
                        kb = int(line.split()[1])
                        return kb * 1024
        except Exception:
            return 0
    return 0

@retry_on_failure(max_retries=2, exceptions=(IOError, OSError))
def read_vms_bytes(pid: int) -> int:
    try:
        with open(f'/proc/{pid}/stat','r') as f:
            s = f.read().rstrip()
        rpar = s.rfind(')')
        after = s[rpar+1:].strip().split()
        vsize = int(after[20])  # field 23 in bytes
        return vsize
    except Exception:
        return 0

def list_all_pids() -> List[int]:
    pids = []
    for name in os.listdir('/proc'):
        if name.isdigit():
            pids.append(int(name))
    return pids

def scontrol_available() -> bool:
    return shutil.which('scontrol') is not None

def scontrol_listpids(jobid: str) -> List[int]:
    # Output varies; we just extract all integers after "Pid=" or "PID=" and filter by /proc existence.
    if not scontrol_available():
        return []
    try:
        out = subprocess.check_output(['scontrol', 'listpids', jobid], text=True, stderr=subprocess.DEVNULL)
        # Catch both "Pid=" and "PID=" (cases differ by version).
        pids = set(int(x.split('=')[1]) for x in re.findall(r'(?:Pid|PID)=(\d+)', out))
        # Some versions print bare PIDs; capture those too:
        pids |= set(int(x) for x in re.findall(r'\b(\d{2,})\b', out) if x.isdigit())
        return [pid for pid in pids if os.path.exists(f'/proc/{pid}')]
    except subprocess.CalledProcessError as e:
        logging.debug(f"scontrol listpids failed for job {jobid}: {e}")
        return []
    except Exception as e:
        logging.error(f"Unexpected error in scontrol_listpids: {e}")
        return []

@retry_on_failure(max_retries=2, exceptions=(IOError, OSError))
def cgroup_paths_for_pid(pid: int) -> Dict[str, str]:
    """Map controller -> relative cgroup path, e.g. {'memory': '/slurm/uid_123/job_456/step_0'} or {'unified': '/user.slice/...'}"""
    paths = {}
    try:
        with open(f'/proc/{pid}/cgroup','r') as f:
            for line in f:
                parts = line.strip().split(':')
                if len(parts) == 3:
                    subsys, path = parts[1], parts[2]
                    if subsys == '':
                        # cgroup v2 unified
                        paths['unified'] = path
                    else:
                        for name in subsys.split(','):
                            paths[name] = path
    except Exception:
        pass
    return paths

def detect_job_cgroup(job_pids: List[int]) -> Optional[Tuple[str, str]]:
    """Return ('unified', path) for cgroup v2 or ('memory', path) for cgroup v1 most-common path across PIDs."""
    counter = defaultdict(int)
    for pid in job_pids[:MAX_SAMPLE_PIDS]:  # sample up to MAX_SAMPLE_PIDS
        paths = cgroup_paths_for_pid(pid)
        if 'unified' in paths:
            counter[('unified', paths['unified'])] += 1
        elif 'memory' in paths:
            counter[('memory', paths['memory'])] += 1
    if not counter:
        return None
    return max(counter.items(), key=lambda kv: kv[1])[0]

@retry_on_failure(max_retries=2, exceptions=(IOError, OSError))
def read_cgroup_memory_bytes(kind_path: Tuple[str, str]) -> Optional[int]:
    kind, path = kind_path
    base = '/sys/fs/cgroup'
    try:
        if kind == 'unified':
            fpath = os.path.join(base, path.lstrip('/'), 'memory.current')
            with open(fpath, 'r') as f:
                return int(f.read().strip())
        elif kind == 'memory':
            # cgroup v1
            fpath = os.path.join('/sys/fs/cgroup/memory', path.lstrip('/'), 'memory.usage_in_bytes')
            with open(fpath, 'r') as f:
                return int(f.read().strip())
    except Exception:
        return None
    return None

def show_job_summary_once(jobid: Optional[str], stepid: Optional[str], pid_root: Optional[int],
                          pattern: Optional[str], interval: float) -> int:
    pidset = set(resolve_target_pids(jobid, stepid, pid_root))
    if not pidset:
        print("No target PIDs found. Are you on the right node or did you pass --job/--pid?")
        return 2
    samples1 = sample_procs(pidset)
    time.sleep(interval)
    samples2 = sample_procs(pidset)
    if not samples1 or not samples2:
        print("Failed to sample processes.")
        return 3
    agg = aggregate(samples1, samples2, interval, pattern)
    # Print a textual snapshot
    print_text_snapshot(agg, jobid, stepid, pid_root, interval)
    return 0

def human_bytes(n: float) -> str:
    units = ['B','KiB','MiB','GiB','TiB']
    i = 0
    while n >= 1024 and i < len(units)-1:
        n /= 1024.0
        i += 1
    return f"{n:.1f} {units[i]}"

def short_age(seconds: float) -> str:
    if seconds < 60: return f"{int(seconds)}s"
    m, s = divmod(int(seconds), 60)
    if m < 60: return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"

def cpu_bar(cores_used: float, cores_total: float, width: int) -> str:
    frac = 0.0 if cores_total <= 0 else max(0.0, min(1.0, cores_used/cores_total))
    filled = int(frac * width)
    return '█'*filled + ' '*(width-filled)

def mem_bar(mem_used: float, mem_total: Optional[float], width: int) -> str:
    if mem_total and mem_total > 0:
        frac = max(0.0, min(1.0, mem_used/mem_total))
        filled = int(frac * width)
    else:
        # no total known -> scale to width but cap
        filled = min(width, int(width * 0.2 + (mem_used/ (8*1024**3)) * (width*0.8)))  # crude scaling around 8 GiB
    return '█'*filled + ' '*(width-filled)

def read_meminfo_total_bytes() -> Optional[int]:
    try:
        with open('/proc/meminfo','r') as f:
            for line in f:
                if line.startswith('MemTotal:'):
                    kb = int(line.split()[1])
                    return kb * 1024
    except Exception:
        return None
    return None

def get_alloc_cpus(jobid: Optional[str]) -> Optional[int]:
    if not jobid or not scontrol_available():
        return None
    try:
        out = subprocess.check_output(['scontrol','show','job','-o',str(jobid)], text=True, stderr=subprocess.DEVNULL)
        # Try AllocTRES=cpu=192 or NumCPUs=192
        m = re.search(r'AllocTRES=.*?cpu=(\d+)', out)
        if m:
            return int(m.group(1))
        m = re.search(r'NumCPUs=(\d+)', out)
        if m:
            return int(m.group(1))
    except Exception:
        return None
    return None

def resolve_target_pids(jobid: Optional[str], stepid: Optional[str], pid_root: Optional[int]) -> List[int]:
    # Priority: pid subtree > job+step > job > SLURM env > else: empty
    if pid_root:
        # collect descendants of pid_root (including root)
        return list(descendants_of(pid_root, include_root=True))
    if jobid:
        pids = scontrol_listpids(jobid if not stepid else f"{jobid}.{stepid}")
        if pids:
            return pids
        # fallback: cgroup search via /proc/<pid>/cgroup containing job_<jobid>
        target = f"job_{jobid}"
        pids = []
        for pid in list_all_pids():
            try:
                with open(f'/proc/{pid}/cgroup','r') as f:
                    txt = f.read()
                if target in txt:
                    pids.append(pid)
            except Exception:
                continue
        return pids
    # try env
    env_job = os.environ.get('SLURM_JOB_ID')
    env_step = os.environ.get('SLURM_STEP_ID')
    if env_job:
        return scontrol_listpids(env_job if not env_step else f"{env_job}.{env_step}")
    return []

def ppid_map() -> Dict[int, int]:
    m = {}
    for pid in list_all_pids():
        stat = parse_stat(f'/proc/{pid}/stat')
        if stat:
            m[stat[0]] = stat[2]  # pid -> ppid
    return m

def descendants_of(root_pid: int, include_root: bool = True) -> Set[int]:
    # BFS using current snapshot of PPIDs
    try:
        # If root doesn't exist, return empty
        if not os.path.exists(f'/proc/{root_pid}'):
            return set()
    except Exception:
        return set()
    m = ppid_map()
    children = defaultdict(set)
    for pid, parent in m.items():
        children[parent].add(pid)
    seen = set()
    q = [root_pid]
    while q:
        x = q.pop()
        if x in seen: continue
        seen.add(x)
        for ch in children.get(x, ()):
            q.append(ch)
    if include_root:
        return seen
    else:
        seen.discard(root_pid)
        return seen

def sample_procs(pidset: Set[int]) -> Dict[int, ProcSample]:
    samples = {}
    for pid in list(pidset):
        try:
            stat = parse_stat(f'/proc/{pid}/stat')
            if not stat:
                continue
            pid_i, comm, ppid, utime, stime, start = stat
            rss = read_status_rss_bytes(pid)
            vms = read_vms_bytes(pid)
            cmd = read_cmdline(pid)
            samples[pid] = ProcSample(pid=pid_i, ppid=ppid, comm=comm, cpu_ticks=utime+stime,
                                       rss_bytes=rss, vms_bytes=vms, start_ticks=start,
                                       cmdline=cmd)
        except Exception:
            continue
    return samples

@dataclass
class AggRow:
    pid: int
    ppid: int
    comm: str
    cpu_cores: float
    rss_bytes: int
    age_s: float
    cmdline: str

@dataclass
class Aggregates:
    now: float
    jobid: Optional[str]
    stepid: Optional[str]
    pid_root: Optional[int]
    pid_count: int
    new_pids: int
    died_pids: int
    fork_rate_hz: float
    total_cpu_cores: float
    total_rss_bytes: int
    cgroup_mem_bytes: Optional[int]
    cpu_hist: deque
    mem_hist: deque
    rows: List[AggRow]
    alloc_cpus: Optional[int]
    mem_total_bytes: Optional[int]

def validate_regex(pattern: str) -> bool:
    """Validate regex pattern for safety and compilability."""
    if not pattern:
        return True
    try:
        # Check for dangerous patterns that could cause ReDoS
        # Look for nested quantifiers and other problematic patterns
        dangerous_indicators = [
            r'\(\w\+\)\*',     # (x+)* pattern
            r'\(\w\*\)\*',     # (x*)* pattern
            r'\([^)]+\+\)\+',  # (something+)+ pattern
            r'\([^)]+\*\)\*',  # (something*)* pattern
            r'\([^)]+\+\)\*',  # (something+)* pattern
            r'\([^)]+\*\)\+',  # (something*)+ pattern
        ]
        
        # Check if pattern contains dangerous constructs
        for indicator in dangerous_indicators:
            if re.search(indicator, pattern):
                logging.warning(f"Potentially dangerous regex pattern detected: {pattern}")
                return False
        
        # Also check for excessive alternation depth
        if pattern.count('|') > 50:  # Arbitrary limit
            logging.warning(f"Pattern has too many alternations: {pattern}")
            return False
        
        # Try to compile it
        compiled = re.compile(pattern)
        # Test on a sample string to ensure it doesn't hang
        test_string = "test_R_Rscript_callr_process"
        compiled.search(test_string)
        return True
    except re.error as e:
        logging.warning(f"Invalid regex pattern: {pattern} - {e}")
        return False
    except Exception as e:
        logging.error(f"Error validating regex: {e}")
        return False

def aggregate(s1: Dict[int, ProcSample], s2: Dict[int, ProcSample], interval: float,
              pattern: Optional[str], compiled_regex: Optional[re.Pattern] = None) -> Aggregates:
    now = time.time()
    seen1 = set(s1.keys())
    seen2 = set(s2.keys())
    new_pids = len(seen2 - seen1)
    died_pids = len(seen1 - seen2)
    # EMWA for fork rate is handled in UI; here just compute per-interval rate
    fork_rate_hz = new_pids / max(interval, 1e-6)
    rows = []
    total_cpu = 0.0
    total_rss = 0
    
    # Use pre-compiled regex if provided, otherwise compile
    regex = compiled_regex
    if regex is None and pattern and validate_regex(pattern):
        try:
            regex = re.compile(pattern)
        except re.error:
            logging.warning(f"Failed to compile regex pattern: {pattern}")
            regex = None
    bt = read_boot_time()
    for pid, p2 in s2.items():
        p1 = s1.get(pid)
        if not p1:
            continue
        d_ticks = max(0, p2.cpu_ticks - p1.cpu_ticks)
        cpu_cores = (d_ticks / CLK_TCK) / max(interval, 1e-6)
        total_cpu += cpu_cores
        total_rss += p2.rss_bytes
        age = now - (bt + (p2.start_ticks / CLK_TCK))
        if (regex is None) or regex.search(p2.comm) or (p2.cmdline and regex.search(p2.cmdline)):
            rows.append(AggRow(pid=p2.pid, ppid=p2.ppid, comm=p2.comm, cpu_cores=cpu_cores,
                               rss_bytes=p2.rss_bytes, age_s=age, cmdline=p2.cmdline))
    # Sort rows by cpu desc, keep top 30 (UI will truncate further)
    rows.sort(key=lambda r: r.cpu_cores, reverse=True)
    return Aggregates(now=now, jobid=None, stepid=None, pid_root=None, pid_count=len(seen2),
                      new_pids=new_pids, died_pids=died_pids, fork_rate_hz=fork_rate_hz,
                      total_cpu_cores=total_cpu, total_rss_bytes=total_rss, cgroup_mem_bytes=None,
                      cpu_hist=deque(maxlen=HISTORY_SIZE), mem_hist=deque(maxlen=HISTORY_SIZE),
                      rows=rows, alloc_cpus=None, mem_total_bytes=read_meminfo_total_bytes())

def print_text_snapshot(agg: Aggregates, jobid: Optional[str], stepid: Optional[str], pid_root: Optional[int], interval: float):
    hdr = []
    if jobid:
        hdr.append(f"Job {jobid}" + (f".{stepid}" if stepid else ""))
    if pid_root:
        hdr.append(f"PID subtree {pid_root}")
    hdr = " | ".join(hdr) if hdr else "rjobtop snapshot"
    print(hdr)
    print("="*len(hdr))
    alloc = agg.alloc_cpus or os.cpu_count() or 0
    print(f"PIDs: {agg.pid_count} | CPU: {agg.total_cpu_cores:.1f} cores (~{int(100*agg.total_cpu_cores/max(alloc,1))}%) of {alloc}")
    mem_used = agg.cgroup_mem_bytes if agg.cgroup_mem_bytes is not None else agg.total_rss_bytes
    print(f"Memory: {human_bytes(mem_used)} (cgroup={agg.cgroup_mem_bytes is not None})")
    print(f"Forks: +{agg.new_pids} -{agg.died_pids} over {interval:.1f}s")
    print("\nTop processes (by CPU cores):")
    print(f"{'PID':>7} {'PPID':>7} {'CPU(cores)':>10} {'RSS':>10} {'AGE':>8}  COMM/CMD")
    for r in agg.rows[:15]:
        print(f"{r.pid:7d} {r.ppid:7d} {r.cpu_cores:10.2f} {human_bytes(r.rss_bytes):>10} {short_age(r.age_s):>8}  {r.comm}  ({r.cmdline[:80]})")

class UIState:
    def __init__(self, jobid: Optional[str], stepid: Optional[str], 
                 pid_root: Optional[int], interval: float, 
                 pattern: Optional[str], show_all: bool = False):
        self.jobid: Optional[str] = jobid
        self.stepid: Optional[str] = stepid
        self.pid_root: Optional[int] = pid_root
        self.interval: float = interval
        self.pattern: Optional[str] = pattern
        self.show_all: bool = show_all
        self.sort_by_rss: bool = False
        self.use_cgroup_mem: bool = True
        self.fork_rate_ema: Optional[float] = None
        self.alloc_cpus: Optional[int] = get_alloc_cpus(jobid) if jobid else None
        self.last_pidset: Set[int] = set()
        self.cgroup_kind_path: Optional[Tuple[str, str]] = None
        self.cpu_hist: deque = deque(maxlen=HISTORY_SIZE)
        self.mem_hist: deque = deque(maxlen=HISTORY_SIZE)
        self.compiled_pattern: Optional[re.Pattern] = None
        self._compile_pattern()

    def _compile_pattern(self) -> None:
        """Compile and cache the regex pattern."""
        if self.pattern and validate_regex(self.pattern):
            try:
                self.compiled_pattern = re.compile(self.pattern)
            except re.error as e:
                logging.warning(f"Failed to compile pattern: {e}")
                self.compiled_pattern = None
        else:
            self.compiled_pattern = None
    
    def update_pattern(self, new_pattern: Optional[str]) -> None:
        """Update pattern and recompile."""
        self.pattern = new_pattern
        self._compile_pattern()

def draw(stdscr, state: UIState) -> None:
    curses.curs_set(0)
    stdscr.nodelay(True)
    last_samples = {}
    last_time = time.time()
    # initial pidset
    pidset = set(resolve_target_pids(state.jobid, state.stepid, state.pid_root))
    state.last_pidset = pidset
    state.cgroup_kind_path = detect_job_cgroup(list(pidset)) if pidset else None

    while True:
        h, w = stdscr.getmaxyx()
        now = time.time()
        interval = max(0.1, state.interval)
        # refresh pidset occasionally (workers may move)
        pidset = set(resolve_target_pids(state.jobid, state.stepid, state.pid_root))
        if pidset:
            state.last_pidset = pidset
        else:
            pidset = state.last_pidset

        s1 = sample_procs(pidset)
        time.sleep(interval)
        s2 = sample_procs(pidset)
        pattern = state.pattern if not state.show_all else None
        compiled = state.compiled_pattern if not state.show_all else None
        agg = aggregate(s1, s2, interval, pattern, compiled)
        agg.alloc_cpus = state.alloc_cpus or os.cpu_count()
        # cgroup memory
        cg_mem = None
        if state.use_cgroup_mem and state.cgroup_kind_path:
            cg_mem = read_cgroup_memory_bytes(state.cgroup_kind_path)
        agg.cgroup_mem_bytes = cg_mem
        # update EMWA fork rate
        if state.fork_rate_ema is None:
            state.fork_rate_ema = agg.fork_rate_hz
        else:
            state.fork_rate_ema = FORK_RATE_EMA_NEW*agg.fork_rate_hz + FORK_RATE_EMA_OLD*state.fork_rate_ema
        # update history
        state.cpu_hist.append(agg.total_cpu_cores)
        mem_used = cg_mem if cg_mem is not None else agg.total_rss_bytes
        state.mem_hist.append(mem_used)

        stdscr.erase()
        # Header
        title = "rjobtop"
        ctx = []
        if state.jobid:
            ctx.append(f"job {state.jobid}" + (f".{state.stepid}" if state.stepid else ""))
        if state.pid_root:
            ctx.append(f"pid {state.pid_root}")
        ctx_str = " | ".join(ctx) if ctx else "auto"
        stdscr.addnstr(0, 0, f"{title} — {ctx_str}", w-1, curses.A_BOLD)

        # Line 1: CPU bar
        alloc = agg.alloc_cpus or os.cpu_count() or 1
        cpu_pct = 100.0 * agg.total_cpu_cores / max(alloc, 1)
        cpu_line = f"CPU: {agg.total_cpu_cores:6.1f} cores  of {alloc:3d}  ({cpu_pct:5.1f}%)"
        barw = max(10, w - len(cpu_line) - 8)
        bar = cpu_bar(agg.total_cpu_cores, alloc, barw)
        stdscr.addnstr(1, 0, cpu_line + "  " + bar, w-1)

        # Line 2: Memory bar
        mem_total = agg.mem_total_bytes
        mem_used_bar = cg_mem if cg_mem is not None else agg.total_rss_bytes
        mem_line = f"Mem: {human_bytes(mem_used_bar):>9}"
        if mem_total:
            mem_line += f" / {human_bytes(mem_total):>9}"
        mem_line += "  " + ("[cgroup]" if cg_mem is not None else "[sum RSS]")
        bar = mem_bar(mem_used_bar, mem_total, max(10, w - len(mem_line) - 8))
        stdscr.addnstr(2, 0, mem_line + "  " + bar, w-1)

        # Line 3: PIDs & forks
        fork_line = f"PIDs: {agg.pid_count:5d}   forks/sec: {state.fork_rate_ema:5.2f}   (+{agg.new_pids}/-{agg.died_pids} last {interval:.1f}s)"
        stdscr.addnstr(3, 0, fork_line, w-1)

        # Mini sparklines (CPU and Mem) on lines 4 and 5
        def render_spark(hist: deque, width: int, y: int, label: str, scale: float):
            # scale is max value to map to full height 8 chars
            chars = SPARK_CHARS
            if not hist:
                stdscr.addnstr(y, 0, f"{label}: (no data yet)", w-1)
                return
            # Take last width points
            data = list(hist)[-width:]
            if not data:
                return
            m = max(data) if scale is None else scale
            m = max(m, 1e-9)
            out = []
            for v in data:
                idx = int((len(chars)-1) * max(0.0, min(1.0, v / m)))
                out.append(chars[idx])
            stdscr.addnstr(y, 0, f"{label}: " + "".join(out), w-1)

        render_spark(state.cpu_hist, min(80, w-10), 4, "cpu", max(alloc,1))
        # For memory, scale by MemTotal
        render_spark(state.mem_hist, min(80, w-10), 5, "mem", agg.mem_total_bytes or max(state.mem_hist) or 1)

        # Table header
        table_y = 7
        stdscr.addnstr(table_y, 0,
                       f"{'PID':>7} {'PPID':>7} {'CPU(cores)':>11} {'RSS':>10} {'AGE':>8}  COMM",
                       w-1, curses.A_UNDERLINE)
        rows = agg.rows
        if state.sort_by_rss:
            rows = sorted(rows, key=lambda r: r.rss_bytes, reverse=True)
        # Show top rows fitting on screen
        max_rows = max(1, h - (table_y+2))
        for i, r in enumerate(rows[:max_rows]):
            y = table_y + 1 + i
            line = f"{r.pid:7d} {r.ppid:7d} {r.cpu_cores:11.2f} {human_bytes(r.rss_bytes):>10} {short_age(r.age_s):>8}  {r.comm}"
            # Indicate R processes
            if re.search(r'\b(R|Rscript|Rterm|callr)\b', r.comm):
                attr = curses.A_BOLD
            else:
                attr = curses.A_NORMAL
            stdscr.addnstr(y, 0, line[:w-1], w-1, attr)

        # Footer: hints
        hint = "[q] quit  [a] toggle all/pattern  [r] toggle R-only pattern  [c] toggle cgroup-mem  [1/2] speed  [p] sort by RSS"
        stdscr.addnstr(h-1, 0, hint[:w-1], w-1, curses.A_DIM)

        stdscr.refresh()

        # Handle keys (non-blocking)
        try:
            ch = stdscr.getch()
        except Exception:
            ch = -1
        if ch == ord('q'):
            break
        elif ch == ord('a'):
            state.show_all = not state.show_all
        elif ch == ord('r'):
            if state.pattern and state.pattern != DEFAULT_R_PATTERN:
                state.update_pattern(DEFAULT_R_PATTERN)
            else:
                state.update_pattern(None)
        elif ch == ord('c'):
            state.use_cgroup_mem = not state.use_cgroup_mem
        elif ch == ord('1'):
            state.interval = max(MIN_INTERVAL, state.interval*INTERVAL_MULTIPLIER)
        elif ch == ord('2'):
            state.interval = min(MAX_INTERVAL, state.interval*INTERVAL_DIVISOR)
        elif ch == ord('p'):
            state.sort_by_rss = not state.sort_by_rss

def main():
    # Check platform
    if not os.path.exists('/proc'):
        print("Error: rjobtop requires Linux with /proc filesystem")
        print("This tool is designed to run on Linux compute nodes in HPC clusters")
        sys.exit(1)
    
    parser = argparse.ArgumentParser(description="rjobtop — focus view of a Slurm job's CPU+Memory utilization (esp. R forks)")
    parser.add_argument('--job', help='Slurm JobID to monitor')
    parser.add_argument('--step', help='Optional Slurm StepID (e.g., 0 or batch); otherwise all steps')
    parser.add_argument('--pid', type=int, help='Monitor a PID subtree instead of Slurm job')
    parser.add_argument('--pattern', default=DEFAULT_R_PATTERN,
                        help='Regex to include rows in table (aggregates still use all processes); default focuses on R')
    parser.add_argument('--interval', type=float, default=DEFAULT_INTERVAL, help=f'Refresh interval in seconds (default {DEFAULT_INTERVAL})')
    parser.add_argument('--once', action='store_true', help='Print a single snapshot and exit (no curses UI)')

    args = parser.parse_args()

    # Sanity: some HPC nodes have TERM=unknown; set a safe default for curses
    if not os.environ.get('TERM'):
        os.environ['TERM'] = DEFAULT_TERMINAL

    if args.once:
        rc = show_job_summary_once(args.job, args.step, args.pid, args.pattern, args.interval)
        sys.exit(rc)

    state = UIState(jobid=args.job, stepid=args.step, pid_root=args.pid,
                    interval=args.interval, pattern=args.pattern, show_all=False)
    curses.wrapper(draw, state)

if __name__ == '__main__':
    main()
