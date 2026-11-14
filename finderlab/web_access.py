"""Explicit private-IPv4 sharing policy. Not TLS or an Internet-facing gateway."""

import base64
import ipaddress
import secrets

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
        self._credential = base64.b64encode(("finder:" + self.password).encode()).decode() if lan else None

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
        return bool(separator and scheme.lower() == "basic" and credential.isascii() and
                    secrets.compare_digest(credential, self._credential))
