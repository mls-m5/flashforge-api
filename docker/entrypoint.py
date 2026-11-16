#!/usr/bin/env python3
"""Map fixed container environment settings to CLI argv without shell or probes."""

from collections.abc import Mapping
import ipaddress
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from finderlab.web_access import validate_listener

Environment = Mapping[str, str]


def boolean(env: Environment, key: str, default: bool = False) -> bool:
    """Accept the existing explicit boolean spellings; never guess on typos."""
    value = env.get(key, str(default)).strip().lower()
    if value in ("1", "true", "yes", "on"):
        return True
    if value in ("0", "false", "no", "off", ""):
        return False
    raise ValueError(key + " must be true or false")


def integer(env: Environment, key: str, default: int, low: int, high: int) -> int:
    raw = env.get(key, str(default))
    if not raw.isascii() or not raw.isdecimal() or len(raw) > 10:
        raise ValueError(key + " must be a bounded integer")
    result = int(raw)
    if not low <= result <= high:
        raise ValueError(f"{key} must be in [{low},{high}]")
    return result


def proxy_command(env: Environment) -> list[str]:
    """Configure the optional relay; target selection never connects or scans."""
    raw = env.get("FINDER_PRINTER_HOST", "").strip()
    if not raw:
        raise ValueError(
            "Set FINDER_PRINTER_HOST explicitly before starting the printer profile; "
            "no printer is discovered"
        )
    target = ipaddress.ip_address(raw)
    if target.is_unspecified or target.is_multicast:
        raise ValueError("Printer target must be a unicast literal IP")
    if not target.is_loopback and not boolean(env, "FINDER_ALLOW_HARDWARE"):
        raise ValueError(
            "Bundled proxy to hardware requires FINDER_ALLOW_HARDWARE=true "
            "and deliberate operator selection"
        )

    port = integer(env, "FINDER_PROXY_PORT", 9000, 1, 65535)
    target_port = integer(env, "FINDER_PRINTER_PORT", 8899, 1, 65535)
    if target.is_loopback and port == target_port:
        raise ValueError("Refusing a proxy loop to its own listener")
    return [
        "-m", "finderlab", "proxy",
        "--host", "127.0.0.1", "--port", str(port),
        "--target-host", str(target), "--target-port", str(target_port),
        "--capture-dir", "/app/proxy-captures",
    ]


def slicing_arguments(profile_dir: Path, orca: Path) -> list[str]:
    """Use only the fixed image paths or a deliberate server-side custom mount."""
    if not orca.is_file() or not os.access(orca, os.X_OK):
        raise ValueError("Slicing runtime absent; rebuild the slicer image target")

    arguments = []
    for kind in ("machine", "process", "filament"):
        path = profile_dir / (kind + ".json")
        if not path.is_file() or not 0 < path.stat().st_size <= 1024 * 1024:
            raise ValueError(
                "Missing/bounded trusted " + str(path)
                + "; use the bundled Finder2 profiles or a complete trusted custom mount"
            )
        arguments.extend(["--" + kind, str(path)])
    arguments.extend(["--orca", str(orca), "--check-priming"])
    return arguments


def capability_arguments(env: Environment, mode: str, *, slicing: bool) -> list[str]:
    """Keep owned-dummy permissions distinct from explicit configured-target flags."""
    upload = boolean(env, "FINDER_ENABLE_UPLOAD")
    jobs = boolean(env, "FINDER_ENABLE_JOB_CONTROLS")
    generated = boolean(env, "FINDER_ALLOW_SLICED_UPLOAD")
    monitor = boolean(env, "FINDER_ENABLE_MONITOR")
    automatic_monitor = boolean(env, "FINDER_AUTO_MONITOR")

    if mode != "proxy" and any((upload, jobs, generated, monitor, automatic_monitor)):
        raise ValueError(
            "Printer capability flags require FINDER_MODE=proxy; "
            "dummy owns virtual permissions and offline stays disconnected"
        )
    if mode == "dummy":
        return ["--dummy"]
    if mode == "offline":
        return []

    if jobs and not upload:
        raise ValueError("Combined workflow job controls require FINDER_ENABLE_UPLOAD=true")
    if generated and (not slicing or not upload):
        raise ValueError("Generated output saving requires configured slicing and enabled upload")
    if automatic_monitor and not monitor:
        raise ValueError("Automatic status requires FINDER_ENABLE_MONITOR=true")

    arguments = [
        "--target-host", "127.0.0.1",
        "--target-port", str(integer(env, "FINDER_PROXY_PORT", 9000, 1, 65535)),
    ]
    flags = (
        (upload, "--enable-upload"),
        (jobs, "--enable-job-controls"),
        (generated, "--allow-sliced-upload"),
        (monitor, "--enable-monitor"),
        (automatic_monitor, "--auto-monitor"),
    )
    for enabled, flag in flags:
        if enabled:
            arguments.append(flag)
    return arguments


def web_command(env: Environment, *, profile_dir: Path, orca: Path) -> list[str]:
    mode = env.get("FINDER_MODE", "dummy")
    if mode not in ("dummy", "offline", "proxy"):
        raise ValueError("FINDER_MODE must be dummy, offline or proxy")

    host = env.get("FINDER_LISTEN_HOST", "127.0.0.1").strip()
    address = ipaddress.ip_address(host)
    lan = not address.is_loopback
    network = env.get("FINDER_LAN_NETWORK", "192.168.0.0/16")
    # Specific192.168 interface, password and peer policy; never wildcard.
    validate_listener(host, lan, network)
    port = integer(env, "FINDER_WEB_PORT", 8000, 1, 65535)
    storage_mib = integer(env, "FINDER_STORAGE_MIB", 256, 128, 2048)
    arguments = [
        "-m", "finderlab", "web", "--listen-host", host, "--listen-port", str(port),
        "--data-dir", "/app/web-data", "--storage-limit-mib", str(storage_mib),
    ]
    if lan:
        arguments.extend(["--lan", "--lan-network", network])
    if not boolean(env, "FINDER_AUTO_ARCHIVE", True):
        arguments.append("--no-auto-archive")

    slicing = boolean(env, "FINDER_ENABLE_SLICING")
    if slicing:
        arguments.extend(slicing_arguments(profile_dir, orca))
    arguments.extend(capability_arguments(env, mode, slicing=slicing))
    return arguments


def command(
    env: Environment,
    *,
    profile_dir: Path = Path("/profiles"),
    orca: Path = Path("/opt/orca/AppRun"),
) -> list[str]:
    """Build argv only; default dummy ownership is established by the backend."""
    service = env.get("FINDER_SERVICE", "web")
    if service == "proxy":
        return proxy_command(env)
    if service != "web":
        raise ValueError("FINDER_SERVICE must be web or proxy")
    return web_command(env, profile_dir=profile_dir, orca=orca)


def main():
    try:
        if len(sys.argv) > 1:
            raise ValueError(
                "Use FINDER_* environment settings, or override the entrypoint "
                "explicitly for raw CLI arguments"
            )
        args = command(os.environ)
    except (ValueError, OSError) as exc:
        sys.exit("Container configuration error: " + str(exc))

    print(
        "Finderlab container: explicit configuration, no discovery; LAN login "
        "password is printed by the web process. Proxy is not a safety filter.",
        flush=True,
    )
    os.chdir(ROOT)
    os.execv(sys.executable, [sys.executable, *args])


if __name__ == "__main__":
    main()
