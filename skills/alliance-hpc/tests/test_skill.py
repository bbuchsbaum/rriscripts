#!/usr/bin/env python3
"""Offline tests: no cluster access, submissions, downloads, or external packages."""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASH = '/usr/bin/bash' if Path('/usr/bin/bash').exists() else '/bin/bash'


def executable(path: Path, body: str) -> Path:
    path.write_text(textwrap.dedent(body).lstrip(), encoding='utf-8')
    path.chmod(0o755)
    return path


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix='alliance-skill-test-')
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.bin = self.work / 'bin'
        self.bin.mkdir()
        self.env = dict(os.environ)
        for key in list(self.env):
            if key.startswith(('SLURM_', 'SBATCH_', 'ALLIANCE_PROBE_')) or key == 'THREADS_PER_WORKER':
                del self.env[key]
        self.env.update(PATH=str(self.bin) + os.pathsep + self.env.get('PATH', ''),
                        HOME=str(self.work), TEST_WORK=str(self.work))

    def run_script(self, name: str, *args: object, **overrides: str) -> subprocess.CompletedProcess[str]:
        env = self.env | overrides
        return subprocess.run([BASH, str(ROOT / name), *map(str, args)], env=env,
                              text=True, capture_output=True, timeout=25)

    def recorder(self) -> Path:
        return executable(self.bin / 'record', r'''
            #!/usr/bin/env python3
            import json, os, sys
            from pathlib import Path
            Path(os.environ['TEST_WORK'], 'payload.json').write_text(json.dumps(sys.argv[1:]))
            raise SystemExit(int(os.environ.get('PAYLOAD_EXIT', '0')))
        ''')


class ArrayTests(Fixture):
    def setUp(self) -> None:
        super().setUp()
        self.record = self.recorder()
        self.manifest = self.work / 'ids with spaces.txt'
        self.manifest.write_text('subject 01\nsubject-02\n', encoding='utf-8')

    def dispatch(self, index: str = '1', **kw: str) -> subprocess.CompletedProcess[str]:
        return self.run_script('scripts/array-task.sh', self.manifest, self.record,
                               'fixed argument', SLURM_ARRAY_TASK_ID=index, **kw)

    def test_first_row_preserves_spaces(self) -> None:
        p = self.dispatch()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads((self.work/'payload.json').read_text()), ['fixed argument', 'subject 01'])

    def test_second_row(self) -> None:
        self.assertEqual(self.dispatch('2').returncode, 0)
        self.assertEqual(json.loads((self.work/'payload.json').read_text())[-1], 'subject-02')

    def test_no_trailing_newline(self) -> None:
        self.manifest.write_text('last-item')
        self.assertEqual(self.dispatch().returncode, 0)

    def test_metacharacters_are_data(self) -> None:
        attack = f'$(touch {self.work}/SHOULD_NOT_EXIST); `echo fail` "quotes" *'
        self.manifest.write_text(attack + '\n')
        p = self.dispatch()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads((self.work/'payload.json').read_text())[-1], attack)
        self.assertFalse((self.work/'SHOULD_NOT_EXIST').exists())

    def test_payload_failure_propagates(self) -> None:
        self.assertEqual(self.dispatch(PAYLOAD_EXIT='23').returncode, 23)

    def test_bad_indices_rejected(self) -> None:
        for index in ('', '0', '-1', '01', '1;exit', '999999999999'):
            with self.subTest(index=index):
                self.assertEqual(self.dispatch(index).returncode, 64)

    def test_missing_row_rejected(self) -> None:
        self.assertEqual(self.dispatch('3').returncode, 64)

    def test_blank_row_rejected(self) -> None:
        self.manifest.write_text(' \t\n')
        self.assertEqual(self.dispatch().returncode, 64)

    def test_crlf_rejected(self) -> None:
        self.manifest.write_bytes(b'subject-01\r\n')
        self.assertEqual(self.dispatch().returncode, 64)

    def test_relative_path_rejected(self) -> None:
        p = self.run_script('scripts/array-task.sh', 'relative.txt', self.record, SLURM_ARRAY_TASK_ID='1')
        self.assertEqual(p.returncode, 64)

    def test_missing_manifest_rejected(self) -> None:
        self.manifest.unlink()
        self.assertEqual(self.dispatch().returncode, 64)

    def test_missing_payload_rejected(self) -> None:
        self.assertEqual(self.run_script('scripts/array-task.sh', self.manifest).returncode, 64)


class CpuTests(Fixture):
    def setUp(self) -> None:
        super().setUp()
        self.record = self.recorder()
        self.environment = self.work/'environment.sh'
        self.environment.write_text('# frozen environment for test\nexport TEST_ENV_LOADED=yes\n')
        self.env.update(SLURM_JOB_ID='123', SLURM_NTASKS='1', SLURM_JOB_NUM_NODES='1',
                        SLURM_CPUS_PER_TASK='8')
        executable(self.bin/'srun', r'''
            #!/usr/bin/env python3
            import json, os, subprocess, sys
            from pathlib import Path
            names=['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','BLIS_NUM_THREADS',
                   'NUMEXPR_NUM_THREADS','NUMEXPR_MAX_THREADS','VECLIB_MAXIMUM_THREADS',
                   'TEST_ENV_LOADED','SLURM_EXPORT_ENV']
            Path(os.environ['TEST_WORK'],'launch.json').write_text(json.dumps({
                'argv':sys.argv[1:], 'env':{k:os.environ.get(k) for k in names}}))
            args=sys.argv[1:]
            assert args[0]=='--ntasks=1' and args[1].startswith('--cpus-per-task=')
            raise SystemExit(subprocess.run(args[2:]).returncode)
        ''')

    def launch(self, **kw: str) -> subprocess.CompletedProcess[str]:
        return self.run_script('templates/cpu.sbatch', self.environment, self.record,
                               'arg with space', '$(not code)', **kw)

    def test_one_task_and_argument_boundaries(self) -> None:
        p = self.launch()
        self.assertEqual(p.returncode, 0, p.stderr)
        record = json.loads((self.work/'launch.json').read_text())
        self.assertEqual(record['argv'][:2], ['--ntasks=1', '--cpus-per-task=8'])
        self.assertEqual(json.loads((self.work/'payload.json').read_text()), ['arg with space', '$(not code)'])
        self.assertEqual(record['env']['TEST_ENV_LOADED'], 'yes')

    def test_library_threads_default_one(self) -> None:
        self.assertEqual(self.launch(OPENBLAS_NUM_THREADS='99').returncode, 0)
        values = json.loads((self.work/'launch.json').read_text())['env']
        for key, value in values.items():
            if key.endswith('THREADS'):
                self.assertEqual(value, '1', key)
        self.assertEqual(values['SLURM_EXPORT_ENV'], 'ALL')

    def test_intentional_threads(self) -> None:
        self.environment.write_text('THREADS_PER_WORKER=4\n')
        self.assertEqual(self.launch().returncode, 0)
        values = json.loads((self.work/'launch.json').read_text())['env']
        self.assertEqual(values['OPENBLAS_NUM_THREADS'], '4')

    def test_thread_oversubscription_rejected(self) -> None:
        self.assertEqual(self.launch(THREADS_PER_WORKER='9').returncode, 64)
        self.assertFalse((self.work/'launch.json').exists())

    def test_invalid_threads_rejected(self) -> None:
        self.assertEqual(self.launch(THREADS_PER_WORKER='8;false').returncode, 64)

    def test_no_allocation_rejected(self) -> None:
        self.assertEqual(self.launch(SLURM_JOB_ID='').returncode, 64)

    def test_missing_cpu_request_rejected(self) -> None:
        self.assertEqual(self.launch(SLURM_CPUS_PER_TASK='').returncode, 64)

    def test_multinode_rejected(self) -> None:
        self.assertEqual(self.launch(SLURM_JOB_NUM_NODES='2').returncode, 64)

    def test_multitask_rejected(self) -> None:
        self.assertEqual(self.launch(SLURM_NTASKS='2').returncode, 64)

    def test_payload_failure_propagates(self) -> None:
        self.assertEqual(self.launch(PAYLOAD_EXIT='17').returncode, 17)

    def test_environment_failure_propagates(self) -> None:
        self.environment.write_text('false\nexport SHOULD_NOT_CONTINUE=yes\n')
        self.assertNotEqual(self.launch().returncode, 0)
        self.assertFalse((self.work/'launch.json').exists())

    def test_environment_required(self) -> None:
        self.environment.unlink()
        self.assertEqual(self.launch().returncode, 64)


class ProbeTests(Fixture):
    def setUp(self) -> None:
        super().setUp()
        mock = r'''
            #!/usr/bin/env python3
            import json, os, sys
            from pathlib import Path
            name=Path(sys.argv[0]).name
            a=sys.argv[1:]
            with Path(os.environ['TEST_WORK'],'calls.jsonl').open('a') as f:
                f.write(json.dumps([name,*a])+'\n')
            if name==os.environ.get('FAIL_TOOL'): raise SystemExit(1)
            if name=='hostname': print('nibi-login.example')
            elif name=='sbatch':
                assert a==['--version'], 'NO SUBMISSION PERMITTED IN TEST'
                print('slurm fixture')
            elif name=='sacctmgr':
                assert 'show' in a and not {'add','modify','delete'}.intersection(a)
                print('nibi|authorized-test-account|fixture|normal|normal')
            elif name=='scontrol':
                assert 'show' in a
                if 'config' in a:
                    print('ClusterName = nibi\nMaxArraySize = 1001\nSelectType = select/cons_tres\nSecretUnused = DO_NOT_PRINT_CONFIG')
                else: print('PartitionName=normal MaxTime=1-00:00:00')
            elif name=='sinfo': print('normal*|up|1-00:00:00|10|192|750000|2:96:1|(null)|fixture')
            elif name=='squeue': print('123|pilot|authorized-test-account|normal|PENDING|0:00|1:00:00|8|Priority')
            elif name=='sshare': print('authorized-test-account fairshare fixture')
            elif name=='df': print('fixture filesystem report')
            elif name=='findmnt': print('/scratch fixturefs fixture')
            elif name=='diskusage_report': print('fixture quota report')
            else: raise SystemExit(99)
        '''
        for name in ('hostname', 'sbatch', 'sacctmgr', 'scontrol', 'sinfo', 'squeue',
                     'sshare', 'df', 'findmnt', 'diskusage_report'):
            executable(self.bin/name, mock)
        self.env.update(CC_CLUSTER='nibi', SCRATCH=str(self.work), ALLIANCE_PROBE_TIMEOUT='2')

    def probe(self, **kw: str) -> subprocess.CompletedProcess[str]:
        return self.run_script('scripts/probe.sh', self.work, **kw)

    def test_only_read_calls(self) -> None:
        p = self.probe()
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        calls=[json.loads(x) for x in (self.work/'calls.jsonl').read_text().splitlines()]
        self.assertEqual([x for x in calls if x[0]=='sbatch'], [['sbatch','--version']])
        self.assertTrue(all(x[0] not in ('scancel','salloc','srun') for x in calls))
        self.assertIn('MaxArraySize = 1001', p.stdout)
        self.assertNotIn('DO_NOT_PRINT_CONFIG', p.stdout)

    def test_no_secret_values(self) -> None:
        p = self.probe(SBATCH_CONSTRAINT='SECRET_SCHEDULER_VALUE', PASSWORD='SECRET_PASSWORD_VALUE')
        self.assertEqual(p.returncode, 0)
        self.assertIn('SBATCH_CONSTRAINT', p.stdout)
        self.assertNotIn('SECRET_SCHEDULER_VALUE', p.stdout)
        self.assertNotIn('SECRET_PASSWORD_VALUE', p.stdout)

    def test_unavailable_evidence_reported(self) -> None:
        p = self.probe(FAIL_TOOL='sacctmgr')
        self.assertEqual(p.returncode, 2)
        self.assertIn('INCOMPLETE: exit=1', p.stdout)
        self.assertIn('UNVERIFIED', p.stdout)

    def test_qos_scoped_when_requested(self) -> None:
        self.assertEqual(self.probe(ALLIANCE_PROBE_QOS='normal').returncode, 0)
        calls=[json.loads(x) for x in (self.work/'calls.jsonl').read_text().splitlines()]
        qos=[x for x in calls if 'qos' in x]
        self.assertEqual(len(qos), 1)
        self.assertIn('name=normal', qos[0])

    def test_invalid_qos_rejected(self) -> None:
        self.assertEqual(self.probe(ALLIANCE_PROBE_QOS='x;rm -rf /').returncode, 64)
        self.assertFalse((self.work/'calls.jsonl').exists())

    def test_truncated_evidence_is_incomplete(self) -> None:
        executable(self.bin/'sinfo', '''
            #!/usr/bin/env python3
            for i in range(150): print('profile-' + str(i))
        ''')
        p = self.probe()
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertIn('INCOMPLETE: output truncated', p.stdout)
        self.assertIn('profile-119\n', p.stdout)
        self.assertNotIn('profile-120\n', p.stdout)

    def test_slow_query_times_out_and_other_queries_continue(self) -> None:
        executable(self.bin/'sinfo', '#!/bin/sh\nexec sleep 10\n')
        p = self.probe()
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertIn('INCOMPLETE: exit=124', p.stdout)
        self.assertIn('fixture quota report', p.stdout)

    def test_invalid_timeout_rejected(self) -> None:
        self.assertEqual(self.probe(ALLIANCE_PROBE_TIMEOUT='100').returncode, 64)

    def test_missing_workdir_rejected(self) -> None:
        p=self.run_script('scripts/probe.sh', self.work/'missing')
        self.assertEqual(p.returncode, 64)
        self.assertFalse((self.work/'calls.jsonl').exists())


def bash_blocks(path: Path) -> list[str]:
    return re.findall(r'```bash\n(.*?)\n```', path.read_text(), re.S)


class InstallationTests(Fixture):
    def install(self, block: int, cwd: Path, home: Path) -> subprocess.CompletedProcess[str]:
        code = bash_blocks(ROOT/'README.md')[block]
        return subprocess.run([BASH], input=code, cwd=cwd,
                              env=self.env | {'HOME': str(home)},
                              text=True, capture_output=True, timeout=25)

    def test_personal_links_share_canonical_directory(self) -> None:
        p = self.install(0, ROOT, self.work)
        self.assertEqual(p.returncode, 0, p.stderr)
        for agent in ('.agents', '.claude'):
            link = self.work/agent/'skills/alliance-hpc'
            self.assertTrue(link.is_symlink())
            self.assertEqual(link.resolve(), ROOT)

    def test_existing_entries_prevent_all_link_creation(self) -> None:
        for kind in ('directory', 'file', 'dangling-symlink'):
            with self.subTest(kind=kind):
                home = self.work/kind
                conflict = home/'.claude/skills/alliance-hpc'
                conflict.parent.mkdir(parents=True)
                if kind == 'directory':
                    conflict.mkdir()
                elif kind == 'file':
                    conflict.write_text('keep me')
                else:
                    conflict.symlink_to(home/'missing')
                p = self.install(0, ROOT, home)
                self.assertNotEqual(p.returncode, 0)
                self.assertIn('Already exists', p.stderr)
                self.assertFalse(os.path.lexists(home/'.agents/skills/alliance-hpc'))
                if kind == 'directory':
                    self.assertTrue(conflict.is_dir())
                elif kind == 'file':
                    self.assertEqual(conflict.read_text(), 'keep me')
                else:
                    self.assertEqual(os.readlink(conflict), str(home/'missing'))

    def test_repository_links_are_relative_and_resolve(self) -> None:
        skill = self.work/'skills/alliance-hpc'
        skill.mkdir(parents=True)
        (skill/'SKILL.md').write_text('fixture')
        p = self.install(1, self.work, self.work)
        self.assertEqual(p.returncode, 0, p.stderr)
        for agent in ('.agents', '.claude'):
            link = self.work/agent/'skills/alliance-hpc'
            self.assertEqual(os.readlink(link), '../../skills/alliance-hpc')
            self.assertEqual(link.resolve(), skill.resolve())


class SubmissionTests(Fixture):
    def setUp(self) -> None:
        super().setUp()
        self.run = self.work/'run with spaces'
        self.run.mkdir()
        for name in ('cpu.sbatch', 'environment.sh'):
            (self.run/name).write_text('#!/bin/bash\ntrue\n')
        self.env.update(ACCOUNT='fixture-account', RUN=str(self.run),
                        RUN_ID='pilot-001', CLUSTER='fixture-cluster')
        executable(self.bin/'sbatch', r'''
            #!/usr/bin/env python3
            import json, os, sys
            from pathlib import Path
            with Path(os.environ['TEST_WORK'], 'submissions.jsonl').open('a') as f:
                f.write(json.dumps(sys.argv[1:]) + '\n')
            if '--test-only' in sys.argv:
                raise SystemExit(int(os.environ.get('PREFLIGHT_EXIT', '0')))
            assert '--parsable' in sys.argv
            assert Path(os.environ['RUN'], 'submission-intents.tsv').is_file()
            print(os.environ.get('SUBMIT_RECEIPT', '12345;fixture-cluster'))
            raise SystemExit(int(os.environ.get('SUBMIT_EXIT', '0')))
        ''')

    def submit(self, **kw: str) -> subprocess.CompletedProcess[str]:
        blocks = bash_blocks(ROOT/'references/submission.md')
        # Exercise the actual documented preflight and submit sequence under mocks.
        return subprocess.run([BASH], input='\n'.join(blocks[:2]),
                              env=self.env | kw, text=True, capture_output=True, timeout=25)

    def calls(self) -> list[list[str]]:
        return [json.loads(line) for line in
                (self.work/'submissions.jsonl').read_text().splitlines()]

    def test_failed_preflight_does_not_submit(self) -> None:
        p = self.submit(PREFLIGHT_EXIT='1')
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(len(self.calls()), 1)
        self.assertIn('--test-only', self.calls()[0])
        self.assertFalse((self.run/'jobs.tsv').exists())

    def test_success_submits_once_and_records_receipt(self) -> None:
        p = self.submit()
        self.assertEqual(p.returncode, 0, p.stderr)
        calls = self.calls()
        self.assertEqual(len(calls), 2)
        self.assertIn('--parsable', calls[1])
        self.assertIn(str(self.run/'environment.sh'), calls[1])
        self.assertEqual((self.run/'jobs.tsv').read_text(),
                         'fixture-cluster\t12345\t12345;fixture-cluster\n')

    def test_ambiguous_submit_is_not_retried(self) -> None:
        p = self.submit(SUBMIT_EXIT='1')
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('reconcile before retrying', p.stderr)
        self.assertEqual(len(self.calls()), 2)
        self.assertFalse((self.run/'jobs.tsv').exists())

    def test_invalid_receipt_is_not_recorded_as_job(self) -> None:
        p = self.submit(SUBMIT_RECEIPT='unexpected output')
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('reconcile before retrying', p.stderr)
        self.assertEqual(len(self.calls()), 2)
        self.assertFalse((self.run/'jobs.tsv').exists())

    def test_intent_write_failure_does_not_submit(self) -> None:
        (self.run/'submission-intents.tsv').mkdir()
        p = self.submit()
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(len(self.calls()), 1)


class StaticTests(unittest.TestCase):
    def test_shell_syntax(self) -> None:
        for path in [*ROOT.glob('scripts/*.sh'), *ROOT.glob('templates/*.sbatch')]:
            with self.subTest(path=path.name):
                p=subprocess.run([BASH,'-n',str(path)], capture_output=True, text=True)
                self.assertEqual(p.returncode,0,p.stderr)

    def test_portable_frontmatter_and_small_core(self) -> None:
        skill=(ROOT/'SKILL.md').read_text()
        front=skill.split('---',2)[1].strip().splitlines()
        self.assertEqual({x.split(':',1)[0] for x in front},{'name','description'})
        self.assertIn('name: alliance-hpc',front)
        self.assertLessEqual(len(skill.split()),1000)
        self.assertNotIn('!`',skill)
        for cluster in ('Trillium','Nibi','Fir','Rorqual','Narval'):
            self.assertIn(cluster,skill)

    def test_relative_markdown_links_exist(self) -> None:
        for path in ROOT.rglob('*.md'):
            for target in re.findall(r'\]\(([^)]+)\)',path.read_text()):
                target=target.split('#',1)[0]
                if not target or '://' in target: continue
                self.assertTrue((path.parent/target).resolve().exists(),f'{path}: {target}')

    def test_embedded_bash_recipe_syntax(self) -> None:
        for path in ROOT.rglob('*.md'):
            for i, code in enumerate(re.findall(r'```bash\n(.*?)\n```',path.read_text(),re.S)):
                p=subprocess.run([BASH,'-n'],input=code,text=True,capture_output=True)
                self.assertEqual(p.returncode,0,f'{path.name} block {i}: {p.stderr}')


if __name__=='__main__':
    unittest.main(verbosity=2)
