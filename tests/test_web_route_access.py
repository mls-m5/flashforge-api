"""A route adapter must never be constructed before common access gates pass."""

from dataclasses import replace
import json
from unittest.mock import patch

from finderlab.web import STATIC_FILES, WebServer
from web_helpers import WebTestCase

READS = (
    "/api/config", "/api/state", "/api/printer-status", "/api/manual-state",
    "/api/model", "/api/model?model=part", "/api/artifact", "/api/gx-thumbnail?v=old",
)
POSTS = (
    "/api/file?name=part.stl", "/api/slice", "/api/save", "/api/start", "/api/stop",
    "/api/gx", "/api/discard", "/api/model-remove", "/api/manual", "/api/monitor",
)


class WebRouteAccessTests(WebTestCase):
    async def test_all_assets_and_routes_reject_missing_login_before_adapter_construction(self):
        await self.server.__aexit__(None, None, None)
        self.server = await WebServer(replace(self.config, lan=True)).__aenter__()
        with patch("finderlab.web.WebRoutes") as routes, patch("finderlab.web.FinderClient") as client:
            for path in (*STATIC_FILES, *READS):
                with self.subTest(path=path):
                    status, _ = await self.request("GET", path)
                    self.assertEqual(status, 401)
            for path in POSTS:
                with self.subTest(path=path):
                    status, _ = await self.request("POST", path, b"{}")
                    self.assertEqual(status, 401)
            routes.assert_not_called()
            client.assert_not_called()
        self.assertIsNone(self.server.work.task)
        self.assertEqual(list(self.server.work.folder.glob("captures/*")), [])

    async def test_host_origin_token_length_and_peer_rejection_do_not_enter_routes(self):
        with patch("finderlab.web.WebRoutes") as routes:
            for headers, expected in (
                ({"Host": "wrong"}, 403),
                ({"Origin": "http://wrong"}, 403),
                ({"X-Finder-Token": "wrong"}, 403),
                ({"Content-Length": "-1"}, 411),
            ):
                for path in POSTS:
                    with self.subTest(headers=headers, path=path):
                        status, _ = await self.request("POST", path, b"{}", headers)
                        self.assertEqual(status, expected)
            with patch.object(self.server.access, "allows_peer", return_value=False):
                status, _ = await self.request("GET", "/api/state")
                self.assertEqual(status, 403)
            routes.assert_not_called()
        self.assertEqual(self.server.work.state["phase"], "empty")

    async def test_each_request_binds_current_server_config_not_a_startup_snapshot(self):
        # The backend's work config is separate; GET config must reflect the same
        # current server dependency used before route extraction.
        for enabled in (True, False, True):
            self.server.config = replace(self.server.config, enable_upload=enabled)
            status, body = await self.request("GET", "/api/config")
            self.assertEqual(status, 200)
            self.assertIs(json.loads(body)["upload_enabled"], enabled)
        self.assertFalse(self.server.work.state["busy"])
