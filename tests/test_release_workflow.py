"""Minimal source-only GitHub workflow contracts; no service/container launch."""

from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReleaseWorkflowTests(unittest.TestCase):
    def test_manual_readonly_source_artifacts_without_tests_or_deployment(self):
        source = (ROOT / '.github/workflows/source-release.yml').read_text()
        self.assertIn('workflow_dispatch:', source)
        self.assertIn('contents: read', source)
        self.assertIn('persist-credentials: false', source)
        self.assertIn('submodules: false', source)
        self.assertIn('./tools/package_release.sh\n', source)
        self.assertIn('git archive --format=zip --prefix=finderlab/', source)
        self.assertIn('sha256sum "$name.zip" >> SHA256SUMS', source)
        self.assertIn('Tests were NOT RUN', source)
        self.assertIn('path: dist/releases/*/', source)
        self.assertIn('path: .tmp/package-logs/*.log', source)
        self.assertIn('if: always()', source)
        for forbidden in ('\n  pull_request:', '--check', 'tools/check.sh', 'unittest', 'contents: write',
                          'pull_request_target', 'secrets.', 'docker ', 'podman ', 'gh release'):
            self.assertNotIn(forbidden, source)

    def test_all_tag_pushes_trigger_but_branch_push_and_tag_deletion_do_not_package(self):
        source = (ROOT / '.github/workflows/source-release.yml').read_text()
        self.assertIn("  push:\n    tags:\n      - '**'", source)
        self.assertNotIn('branches:', source)
        self.assertIn("github.event_name != 'push' || github.event.deleted == false", source)
        self.assertIn('workflow_dispatch:', source)

    @unittest.skipUnless(shutil.which('bash'), 'Bash syntax check')
    def test_embedded_packaging_shell_syntax(self):
        source = (ROOT / '.github/workflows/source-release.yml').read_text()
        block = source.split('        run: |\n', 1)[1].split('\n      - name:', 1)[0]
        script = '\n'.join(line[10:] for line in block.splitlines())
        result = subprocess.run(['bash', '-n'], input=script, text=True,
                                capture_output=True, cwd=ROOT, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
