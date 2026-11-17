"""Explicit private-IPv4 sharing policy. Not TLS or an Internet-facing gateway."""

import base64
import binascii
import hmac
import ipaddress
import secrets

from . import web_password
from .web_http import WebError

PRIVATE_LAN = ipaddress.ip_network("192.168.0.0/16")


def validate_listener(host, lan, network):
    address = ipaddress.ip_address(host)
    subnet = ipaddress.ip_network(network, strict=True)
    if subnet.version != 4 or not subnet.subnet_of(PRIVATE_LAN):
        raise ValueError("LAN subnet must be within 192.168.0.0/16 (use an exact CIDR network)")
    if not lan:
        if not address.is_loopback:
            raise ValueError("Non-loopback sharing requires explicit --lan and a 192.168 interface")
        if subnet != PRIVATE_LAN:
            raise ValueError("--lan-network requires --lan")
    elif address.version != 4 or (not address.is_loopback and address not in subnet):
        raise ValueError("LAN bind must be a specific allowed 192.168 address (or loopback for rehearsal), not a wildcard")
    return subnet


class WebAccess:
    def __init__(self, host, lan=False, network="192.168.0.0/16"):
        self.lan = lan
        self.network = validate_listener(host, lan, network)
        self.password = secrets.token_urlsafe(24) if lan else None
        self._record = web_password.make_record(self.password) if lan else None
        self._path = None
        self._cache_key = secrets.token_bytes(32)
        self._cached = None

    def initialize_password(self, path):
        """Called only under Workbench's exclusive lock, before listening."""
        if not self.lan:
            return
        if path.exists() or path.is_symlink():
            record = web_password.load(path)
            self.password = None  # A hash cannot recover/reprint the old password.
        else:
            record = self._record
            web_password.save(path, record)
        self._record = record
        self._path = path
        self._cached = None

    def change_password(self, data):
        if not self.lan or self._path is None:
            raise WebError(409, "Persistent password settings require LAN login mode")
        if set(data) != {"confirm", "current_password", "new_password"} or data.get("confirm") is not True:
            raise WebError(400, "Password change requires confirmation, current_password and new_password only")
        if not web_password.verify(self._record, data["current_password"]):
            raise WebError(403, "Current password is incorrect")
        try:
            candidate = web_password.make_record(data["new_password"])
        except ValueError as exc:
            raise WebError(400, str(exc)) from exc
        # Publish atomically before updating memory; failed persistence cannot
        # silently switch the running credential or invalidate its cache.
        web_password.save(self._path, candidate)
        self._record = candidate
        self._cached = None
        self.password = None
        return {"password_changed": True, "message": "Password saved. Use the new password if your browser asks you to log in again."}

    def allows_peer(self, peer):
        try:
            address = ipaddress.ip_address(peer[0])
        except (ValueError, TypeError, IndexError):
            return False
        if not self.lan:
            return address.is_loopback
        return address.version == 4 and (address.is_loopback or address in self.network)

    def authenticated(self, authorization):
        if not self.lan:
            return True
        scheme, separator, credential = authorization.partition(" ")
        if not separator or scheme.lower() != "basic" or not credential.isascii() or len(credential) > 1024:
            return False
        fingerprint = hmac.digest(self._cache_key, credential.encode("ascii"), "sha256")
        if self._cached is not None and secrets.compare_digest(fingerprint, self._cached):
            return True
        try:
            decoded = base64.b64decode(credential, validate=True)
            username, colon, encoded = decoded.partition(b":")
            password = encoded.decode("utf-8")
        except (ValueError, UnicodeError, binascii.Error):
            return False
        if username != b"finder" or not colon or not web_password.verify(self._record, password):
            return False
        # Cache one keyed fingerprint, never Basic/plaintext credentials. This
        # avoids a slow KDF for every asset/poll and invalidates on password change.
        self._cached = fingerprint
        return True
