"""Execute the workflow release shell with fake gh, never contact GitHub."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

from helpers import workspace_tempdir

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(all(shutil.which(tool) for tool in ('bash', 'sha256sum', 'find')), 'Release shell tools')
class ReleasePublishTests(unittest.TestCase):
    def setUp(self):
        self.temp = workspace_tempdir()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assets = self.root / '.tmp/release-assets/nested'
        self.assets.mkdir(parents=True)
        self.name = 'finderlab-synthetic'
        sums = []
        for suffix in ('.tar.gz', '.zip'):
            filename = self.name + suffix
            payload = b'synthetic reviewed source archive fixture'
            (self.assets / filename).write_bytes(payload)
            sums.append(hashlib.sha256(payload).hexdigest() + '  ' + filename)
        (self.assets / 'SHA256SUMS').write_text('\n'.join(sums) + '\n')
        (self.assets / 'release.json').write_text('{}\n')
        binary = self.root / 'bin'
        binary.mkdir()
        gh = binary / 'gh'
        gh.write_text(f'#!{sys.executable}\n'
                      'import json,os,sys\n'
                      'with open(os.environ["GH_CALLS_FILE"],"a") as log: log.write(json.dumps(sys.argv[1:])+"\\n")\n'
                      'if sys.argv[1:3]==["release","create"] and os.environ.get("FAIL_CREATE"): sys.exit(17)\n')
        gh.chmod(0o700)
        self.calls_file = self.root / 'calls.jsonl'
        self.env = {**os.environ, 'PATH': str(binary) + os.pathsep + os.environ['PATH'],
                    'TMPDIR': str(self.root), 'GH_CALLS_FILE': str(self.calls_file),
                    'GH_TOKEN': 'synthetic-secret-not-in-arguments', 'FAIL_CREATE': '',
                    'GITHUB_REPOSITORY': 'fixture/source', 'RELEASE_TAG': 'v1.0.0'}
        source = (ROOT / '.github/workflows/source-release.yml').read_text()
        block = source.split('\n  release:\n', 1)[1].split('        run: |\n', 1)[1]
        self.script = '\n'.join(line[10:] for line in block.splitlines())

    def run_release(self, **env):
        return subprocess.run(['bash', '-c', self.script], cwd=self.root,
                              env={**self.env, **env}, capture_output=True, text=True, timeout=10)

    def calls(self):
        return [json.loads(line) for line in self.calls_file.read_text().splitlines()] if self.calls_file.exists() else []

    def test_verified_archives_upload_to_draft_then_publish_without_shell_interpolation(self):
        tag = 'v1.0; must-not-be-a-command'
        result = self.run_release(RELEASE_TAG=tag)
        self.assertEqual(result.returncode, 0, result.stderr)
        create, publish = self.calls()
        self.assertEqual(create[:2], ['release', 'create'])
        self.assertIn('--verify-tag', create)
        self.assertIn('--draft', create)
        self.assertEqual(create[create.index('--') + 1:],
                         [tag, self.name + '.tar.gz', self.name + '.zip', 'SHA256SUMS', 'release.json'])
        self.assertEqual(publish, ['release', 'edit', '--repo', 'fixture/source', '--draft=false', '--', tag])
        self.assertNotIn(self.env['GH_TOKEN'], self.calls_file.read_text())

    def test_corrupt_checksum_or_ambiguous_archives_prevent_any_release_call(self):
        (self.assets / (self.name + '.zip')).write_bytes(b'changed')
        self.assertNotEqual(self.run_release().returncode, 0)
        self.assertEqual(self.calls(), [])
        (self.assets / 'second.tar.gz').write_bytes(b'other')
        self.assertNotEqual(self.run_release().returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_create_failure_never_publishes_or_retries(self):
        self.assertEqual(self.run_release(FAIL_CREATE='1').returncode, 17)
        self.assertEqual(len(self.calls()), 1)
        self.assertEqual(self.calls()[0][:2], ['release', 'create'])
