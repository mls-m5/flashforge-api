"""Pure LAN policy tests. No LAN listeners or hardware connections."""

import base64
import unittest

from finderlab.web import WebConfig
from finderlab.web_access import WebAccess


class WebAccessTests(unittest.TestCase):
    def test_default_stays_loopback_and_private_bind_requires_opt_in(self):
        access = WebAccess("127.0.0.1")
        self.assertTrue(access.allows_peer(("127.0.0.1", 1234)))
        self.assertFalse(access.allows_peer(("192.168.1.2", 1234)))
        self.assertIsNone(access.password)
        with self.assertRaises(ValueError): WebConfig(host="192.168.1.2")
        WebConfig(host="192.168.1.2", lan=True)
        WebConfig(host="::1")

    def test_private_ipv4_only_and_narrower_subnet(self):
        access = WebAccess("192.168.1.2", True, "192.168.1.0/24")
        for ip in ("192.168.1.3", "127.0.0.1"):
            self.assertTrue(access.allows_peer((ip, 1234)))
        for ip in ("192.168.2.3", "10.0.0.1", "172.16.0.1", "203.0.113.1", "::1", "::ffff:192.168.1.3", "garbage"):
            self.assertFalse(access.allows_peer((ip, 1234)), ip)
        self.assertFalse(access.allows_peer(None))
        for host, network in (("0.0.0.0", "192.168.0.0/16"), ("::", "192.168.0.0/16"),
                              ("192.168.2.2", "192.168.1.0/24"), ("10.0.0.1", "192.168.0.0/16"),
                              ("192.168.1.2", "0.0.0.0/0"), ("192.168.1.2", "192.168.1.2/24")):
            with self.subTest(host=host, network=network), self.assertRaises(ValueError):
                WebConfig(host=host, lan=True, lan_network=network)

    def test_auth_is_mandatory_even_for_local_peers_in_lan_mode_and_rotates(self):
        first = WebAccess("127.0.0.1", True)
        second = WebAccess("127.0.0.1", True)
        self.assertNotEqual(first.password, second.password)
        self.assertGreaterEqual(len(first.password), 32)
        valid = "Basic " + base64.b64encode(("finder:" + first.password).encode()).decode()
        self.assertTrue(first.authenticated(valid))
        for auth in ("", "Bearer " + first.password, "Basic invalid", valid + "extra"):
            self.assertFalse(first.authenticated(auth))
        self.assertFalse(second.authenticated(valid))
