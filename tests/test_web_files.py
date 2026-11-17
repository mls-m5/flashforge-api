"""Slot-owned I/O with synthetic project-local files; no printer/native slicer."""

import asyncio
import hashlib
import json
from pathlib import Path
import signal
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from finderlab.web import WebConfig, Workbench
from finderlab.web_files import SlotFiles
from finderlab.web_http import WebError
from helpers import workspace_tempdir


def reader_for(data):
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()
    return reader


class SlotFilesTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = workspace_tempdir()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.files = SlotFiles(self.root)

    async def receive(self, data=b"solid synthetic\nendsolid synthetic", suffix=".stl"):
        path = self.files.begin_source(suffix)
        digest = await self.files.receive_source(reader_for(data), path, len(data))
        self.files.accept_source(path, model=suffix in (".stl", ".3mf"))
        return path, digest

    async def test_receipt_hash_limit_surplus_and_publication_are_separate(self):
        self.assertEqual(list(self.root.iterdir()), [])
        path = self.files.begin_source(".gx")
        payload = b"\x00ok\r\n~M29" + bytes(range(256)) * 600
        reader = reader_for(payload + b"unread")
        original = asyncio.timeout
        with patch("finderlab.web_files.asyncio.timeout", wraps=original) as timeout:
            digest = await self.files.receive_source(reader, path, len(payload))
        timeout.assert_called_once_with(60)
        self.assertEqual(digest, hashlib.sha256(payload).hexdigest())
        self.assertEqual(path.read_bytes(), payload)
        self.assertEqual(await reader.read(), b"unread")
        self.assertIsNone(self.files.source, "writing bytes is not successful receipt publication")
        self.files.accept_source(path, model=False)
        self.assertEqual(self.files.source, path)
        self.assertEqual(self.files.artifact, path)
        self.assertFalse(hasattr(self.files, "state"), "no competing workbench state dictionary")

    async def test_initial_eof_cleanup_removes_only_its_private_slot(self):
        history = self.root / "captures"
        history.mkdir()
        (history / "record").write_bytes(b"keep unchanged")
        path = self.files.begin_source(".stl")
        with self.assertRaisesRegex(WebError, "File body ended early"):
            await self.files.receive_source(reader_for(b"short"), path, 100)
        self.assertTrue(path.exists())
        self.files.abort_source_receive()
        self.assertIsNone(self.files.directory)
        self.assertIsNone(self.files.source)
        self.assertEqual((history / "record").read_bytes(), b"keep unchanged")
        self.assertEqual(list(self.root.glob("file-*")), [])

    async def test_failed_append_does_not_register_or_remove_prior_source(self):
        source, _ = await self.receive()
        original = source.read_bytes()
        self.files.register_first_model("first")
        identifier, path = self.files.new_model_path()
        with self.assertRaisesRegex(WebError, "Additional STL body ended early; existing plate preserved"):
            await self.files.receive_model(reader_for(b"partial"), path, 100)
        self.files.abort_model_receive(path)
        self.assertEqual(self.files.model_paths, {"first": source})
        self.assertEqual(source.read_bytes(), original)
        self.assertNotIn(identifier, self.files.model_paths)
        self.assertFalse(path.exists())

    async def test_cancelled_append_cleans_only_partial_file_after_reaping_reader_task(self):
        source, _ = await self.receive()
        self.files.register_first_model("first")
        identifier, path = self.files.new_model_path()
        entered = asyncio.Event()

        async def blocked_read(_):
            entered.set()
            await asyncio.Event().wait()

        task = asyncio.create_task(self.files.receive_model(SimpleNamespace(read=blocked_read), path, 10))
        try:
            await asyncio.wait_for(entered.wait(), 1)
            self.assertTrue(path.exists())
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.files.abort_model_receive(path)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.assertTrue(source.exists())
        self.assertFalse(path.exists())
        self.assertEqual(self.files.model_paths, {"first": source})
        self.assertNotIn(identifier, self.files.model_paths)

    async def test_remove_only_registered_source_and_preserve_mapping_on_io_failure(self):
        first, _ = await self.receive()
        self.files.register_first_model("first")
        identifier, second = self.files.new_model_path()
        await self.files.receive_model(reader_for(b"second"), second, 6)
        self.files.register_model(identifier, second)
        with patch.object(Path, "unlink", side_effect=OSError("read-only")):
            with self.assertRaises(OSError):
                self.files.remove_model(identifier)
        self.assertEqual(self.files.model_paths[identifier], second)
        self.files.remove_model("first")
        self.files.select_source(identifier)
        self.assertFalse(first.exists())
        self.assertEqual(self.files.source.read_bytes(), b"second")
        self.assertEqual(self.files.model_paths, {identifier: second})

    async def test_selected_code_gx_and_compound_share_one_owner_without_overwrite(self):
        source, _ = await self.receive()
        original = source.read_bytes()
        code = self.files.directory / "result.gcode"
        code.write_bytes(b"; synthetic code\n")
        compound = self.files.directory / "result.plate.stl"
        compound.write_bytes(b"synthetic compound")
        geometry = {"path": str(compound), "sha256": "stored compound identity"}
        self.files.select_slice(code, geometry)
        gx = self.files.directory / "result.gx"
        gx.write_bytes(b"synthetic container")
        self.files.select_artifact(gx)
        self.assertEqual(self.files.artifact, gx)
        self.assertIs(self.files.gx_geometry, geometry)
        self.assertEqual(self.files.source.read_bytes(), original)
        self.assertEqual(code.read_bytes(), b"; synthetic code\n")
        self.assertEqual(compound.read_bytes(), b"synthetic compound")

    async def test_workbench_inspection_uses_one_owner_without_mirrored_paths_or_state(self):
        work = Workbench(WebConfig(data_dir=self.root / "workbench"))
        try:
            await work.receive(reader_for(b"synthetic bytes"), 15, "part.stl")
            self.assertFalse({"source", "artifact", "slot", "model_cache", "model_paths", "gx_geometry"} & vars(work).keys())
            self.assertIs(work.source, work.files.source)
            self.assertIs(work.model_paths, work.files.model_paths)
            self.assertFalse(hasattr(work.files, "state"))
            self.assertIs(work.source, work.files.source)
            self.assertIs(work.slot, work.files.directory)
            self.assertIs(work.model_paths, work.files.model_paths)
            self.assertIs(work.artifact, work.files.artifact)
            for name in ("source", "slot", "model_paths", "model_cache", "artifact", "gx_geometry"):
                self.assertNotIn(name, vars(work))
            self.assertFalse(hasattr(work.files, "state"))
            self.assertEqual(work.source.read_bytes(), b"synthetic bytes")
            original = work.files
            work.discard()
            self.assertIs(work.files, original)
            self.assertIsNone(work.source)
            self.assertEqual(work.state["phase"], "empty")
        finally:
            await work.close()

    async def test_workbench_capacity_rejection_occurs_before_slot_io_or_busy_state(self):
        work = Workbench(WebConfig(data_dir=self.root / "workbench"))
        try:
            before = dict(work.state)
            with (
                patch.object(work, "capacity", side_effect=WebError(507, "full")),
                patch.object(work.files, "begin_source") as begin,
            ):
                with self.assertRaises(WebError) as error:
                    await work.receive(reader_for(b"model"), 5, "part.stl")
            self.assertEqual(error.exception.status, 507)
            begin.assert_not_called()
            self.assertEqual(work.state, before)
            self.assertEqual(list(work.folder.glob("file-*")), [])
        finally:
            await work.close()

    async def test_discard_resets_references_only_after_success_and_keeps_captures(self):
        source, _ = await self.receive()
        self.files.register_first_model("first")
        history = self.root / "captures"
        history.mkdir()
        (history / "record").write_bytes(b"history")
        self.files.select_slice(source, {"path": str(source)})
        self.files.model_cache = (source, 0)
        with patch("finderlab.web_files.shutil.rmtree", side_effect=OSError("denied")):
            with self.assertRaises(OSError):
                self.files.discard()
        self.assertEqual(self.files.source, source)
        self.assertTrue(source.exists())
        self.files.discard()
        for name in ("source", "artifact", "directory", "gx_geometry", "model_cache"):
            self.assertIsNone(getattr(self.files, name))
        self.assertEqual(self.files.model_paths, {})
        self.assertFalse(source.exists())
        self.assertEqual((history / "record").read_bytes(), b"history")

    async def test_missing_cached_derivative_is_invalidated_not_relabelled_as_source(self):
        source, _ = await self.receive(suffix=".3mf")
        derivative = self.files.directory / "model-preview.stl"
        derivative.write_bytes(b"geometry")
        self.files.model_cache = (derivative, 2)
        self.assertEqual(self.files.cached_preview(), (derivative, 2))
        derivative.unlink()
        self.assertIsNone(self.files.cached_preview())
        self.assertEqual(self.files.source, source)
        self.assertIsNone(self.files.model_cache)

    async def test_preview_success_owns_cache_without_touching_source_or_artifact(self):
        source, _ = await self.receive(b"synthetic archive", ".3mf")
        destination = self.files.directory / "model-preview.stl"

        async def communicate():
            destination.write_bytes(b"geometry")
            return json.dumps({"zero_area_facets_skipped": 3}).encode(), None

        process = SimpleNamespace(returncode=0, communicate=communicate)
        with patch("finderlab.web_files.asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)) as spawn:
            result = await self.files.prepare_preview(100)
        self.assertEqual(result, (destination, 3))
        self.assertEqual(self.files.cached_preview(), result)
        self.assertIn("finderlab.model_3mf", spawn.call_args.args)
        self.assertTrue(spawn.call_args.kwargs["start_new_session"])
        self.assertEqual(source.read_bytes(), b"synthetic archive")
        self.assertIsNone(self.files.artifact)
        self.assertFalse((self.root / "captures").exists())

    async def test_preview_failure_and_cancel_remove_partial_and_reap_process(self):
        await self.receive(b"synthetic archive", ".3mf")
        destination = self.files.directory / "model-preview.stl"
        process = SimpleNamespace(returncode=1, communicate=AsyncMock(return_value=(b"{}", None)))
        destination.write_bytes(b"partial")
        with patch("finderlab.web_files.asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)):
            with self.assertRaises(WebError):
                await self.files.prepare_preview(100)
        self.assertFalse(destination.exists())
        self.assertIsNone(self.files.model_cache)
        entered = asyncio.Event()

        async def blocked():
            destination.write_bytes(b"partial again")
            entered.set()
            await asyncio.Event().wait()

        process = SimpleNamespace(pid=123456, returncode=None, communicate=blocked, wait=AsyncMock())
        with (
            patch("finderlab.web_files.asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)),
            patch("finderlab.web_files.os.killpg") as kill,
        ):
            task = asyncio.create_task(self.files.prepare_preview(100))
            try:
                await asyncio.wait_for(entered.wait(), 1)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        kill.assert_called_once_with(123456, signal.SIGKILL)
        process.wait.assert_awaited_once()
        self.assertFalse(destination.exists())
        self.assertIsNone(self.files.model_cache)
