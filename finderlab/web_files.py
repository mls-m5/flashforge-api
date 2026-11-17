"""One workbench file slot: paths, byte receipt, preview cache and local cleanup.

No routing, workbench state dictionary, quota/archival policy, slicer or printer
client. Workbench owns admission/busy/identity/job policy and calls these I/O
primitives only after validation. Historical captures live outside this slot.
"""

import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import uuid

from .web_http import WebError


class SlotFiles:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.directory = None
        self.source = None
        self.artifact = None
        self.model_cache = None
        self.model_paths = {}
        self.gx_geometry = None

    def begin_source(self, suffix):
        """Allocate a private name; caller installs its receiving state first."""
        self.directory = self.folder / ("file-" + uuid.uuid4().hex)
        return self.directory / ("source" + suffix)

    async def receive_source(self, reader, path, length):
        self.directory.mkdir(mode=0o700)
        return await self._receive_bytes(reader, path, length, "File body ended early")

    def accept_source(self, path, *, model):
        self.source = path
        self.artifact = None if model else path

    def register_first_model(self, identifier):
        self.model_paths = {identifier: self.source}

    def new_model_path(self):
        identifier = uuid.uuid4().hex
        return identifier, self.directory / (identifier + ".stl")

    async def receive_model(self, reader, path, length):
        return await self._receive_bytes(
            reader, path, length, "Additional STL body ended early; existing plate preserved",
        )

    @staticmethod
    async def _receive_bytes(reader, path, length, early_eof_message):
        digest = hashlib.sha256()
        async with asyncio.timeout(60):
            with path.open("xb") as output:
                remaining = length
                while remaining:
                    data = await reader.read(min(65536, remaining))
                    if not data:
                        raise WebError(400, early_eof_message)
                    output.write(data)
                    digest.update(data)
                    remaining -= len(data)
        return digest.hexdigest()

    def register_model(self, identifier, path):
        self.model_paths[identifier] = path

    def remove_model(self, identifier):
        self.model_paths[identifier].unlink()
        del self.model_paths[identifier]

    def select_source(self, identifier):
        self.source = self.model_paths[identifier]

    def select_artifact(self, path):
        """Select only an already-produced artifact; never convert/save/start."""
        self.artifact = path

    def select_slice(self, path, geometry):
        self.gx_geometry = geometry
        self.artifact = path

    def abort_source_receive(self):
        # Preserve the original initial-receipt cleanup/error behavior. State
        # restoration belongs to Workbench, not a second copy stored here.
        shutil.rmtree(self.directory, ignore_errors=True)
        self.directory = None

    @staticmethod
    def abort_model_receive(path):
        path.unlink(missing_ok=True)

    def discard(self):
        if self.directory:
            shutil.rmtree(self.directory)
        # Reset pointers only after deletion succeeds. Never delete captures or
        # the parent workspace, nor clear state after an unsuccessful deletion.
        self.source = self.artifact = self.directory = None
        self.model_cache = None
        self.model_paths = {}
        self.gx_geometry = None

    def cached_preview(self):
        if self.model_cache and self.model_cache[0].is_file():
            return self.model_cache
        self.model_cache = None
        return None

    async def prepare_preview(self, max_derived):
        """Prepare/cache private core3MF geometry after caller's quota/busy gate.

        Keep the converter's process/resource behavior unchanged. Generic child
        process abstraction and creation-race changes belong to later R4 work.
        The caller restores busy/phase even if cleanup itself raises.
        """
        destination = self.directory / "model-preview.stl"
        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "finderlab.model_3mf", str(self.source), str(destination),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                start_new_session=True, cwd=Path(__file__).resolve().parents[1],
            )
            async with asyncio.timeout(20):
                output, _ = await process.communicate()
            if process.returncode != 0 or len(output) > 512 * 1024:
                raise WebError(
                    422, "3MF model preview failed or exceeded resources; export mesh-only STL if unsupported",
                )
            info = json.loads(output)
            if not destination.is_file() or not 0 < destination.stat().st_size <= max_derived:
                raise WebError(422, "Invalid geometry preview output")
            self.model_cache = destination, info["zero_area_facets_skipped"]
            return self.model_cache
        finally:
            if process is not None and process.returncode is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await process.wait()
            if self.model_cache is None:
                destination.unlink(missing_ok=True)
