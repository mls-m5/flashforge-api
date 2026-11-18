"""CI/source workflow contracts; no hosted job, service or container launch."""

from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReleaseWorkflowTests(unittest.TestCase):
    def source(self):
        return (ROOT / '.github/workflows/source-release.yml').read_text()

    def test_readonly_packaging_is_gated_and_does_not_rerun_tests_or_deploy(self):
        source = self.source()
        package = source.split('\n  package:\n', 1)[1].split('\n  release:\n', 1)[0]
        self.assertIn('contents: read', source)
        self.assertEqual(source.count('persist-credentials: false'), 2)
        self.assertEqual(source.count('submodules: false'), 2)
        self.assertIn('needs: tests', package)
        self.assertIn('./tools/package_release.sh\n', package)
        self.assertIn('git archive --format=zip --prefix=finderlab/', package)
        self.assertIn('sha256sum "$name.zip" >> SHA256SUMS', package)
        self.assertIn('path: dist/releases/*/', package)
        self.assertIn('path: .tmp/package-logs/*.log', package)
        self.assertIn('if: always()', package)
        for forbidden in ('--check', 'tools/check.sh', 'unittest'):
            self.assertNotIn(forbidden, package)
        unprivileged = source.split('\n  release:\n', 1)[0]
        self.assertNotIn('contents: write', unprivileged)
        self.assertNotIn('gh release', unprivileged)
        for forbidden in ('\n  pull_request:', 'pull_request_target', 'secrets.', 'docker ', 'podman '):
            self.assertNotIn(forbidden, source)

    def test_branch_and_tag_pushes_trigger_but_deleted_refs_do_not_run(self):
        source = self.source()
        self.assertIn("  push:\n    branches:\n      - '**'\n    tags:\n      - '**'", source)
        self.assertEqual(source.count("github.event_name != 'push' || github.event.deleted == false"), 2)
        self.assertIn('workflow_dispatch:', source)

    def test_both_python_versions_and_node_are_checked_before_selective_source_upload(self):
        source = self.source()
        tests = source.split('\n  tests:\n', 1)[1].split('\n  package:\n', 1)[0]
        self.assertIn("python: ['3.11', '3.12']", tests)
        self.assertIn("node-version: '24'", tests)
        self.assertIn('fail-fast: false', tests)
        self.assertIn('set -euo pipefail', tests)
        self.assertIn('./tools/check.sh --jobs 4 2>&1 | tee .tmp/ci-checks.log', tests)
        self.assertIn('path: .tmp/ci-checks.log', tests)
        self.assertIn('if: always()', tests)
        upload = source.split('      - name: Upload source archives and checksums\n', 1)[1].split('\n      - name:', 1)[0]
        self.assertIn("if: ${{ github.ref_type == 'tag' || github.event_name == 'workflow_dispatch' }}", upload)
        self.assertIn('uses: actions/upload-artifact@v4', upload)
        self.assertIn('Branch push: ZIP built for validation only; source archives are not uploaded.', source)

    def test_release_is_in_same_pipeline_only_for_new_tags_after_packaging(self):
        release = self.source().split('\n  release:\n', 1)[1]
        self.assertIn('needs: package', release)
        self.assertIn("github.event_name == 'push' && github.ref_type == 'tag' && github.event.created == true && github.event.deleted == false", release)
        self.assertIn('contents: write', release)
        self.assertIn('uses: actions/download-artifact@v4', release)
        self.assertIn('name: finderlab-source-${{ github.sha }}', release)
        self.assertIn('RELEASE_TAG: ${{ github.ref_name }}', release)
        self.assertIn('GH_TOKEN: ${{ github.token }}', release)
        self.assertIn('sha256sum -c SHA256SUMS', release)
        self.assertIn('--verify-tag --draft', release)
        self.assertIn('--draft=false', release)
        self.assertNotIn('--clobber', release)
        self.assertNotIn('actions/checkout', release)

    @unittest.skipUnless(shutil.which('bash'), 'Bash syntax check')
    def test_all_embedded_shell_blocks_have_valid_syntax(self):
        blocks = self.source().split('        run: |\n')[1:]
        self.assertEqual(len(blocks), 3)
        for block in blocks:
            block = block.split('\n      - name:', 1)[0]
            script = '\n'.join(line[10:] for line in block.splitlines())
            with self.subTest(script=script):
                result = subprocess.run(['bash', '-n'], input=script, text=True,
                                        capture_output=True, cwd=ROOT, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
