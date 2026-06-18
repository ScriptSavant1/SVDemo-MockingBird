"""EC2 stub engine health check poller.

Polls the Spring Boot Actuator health endpoint until the stub is ready
or the timeout is exceeded.
"""
from __future__ import annotations

import time
import urllib.error
import urllib.request


def wait_for_ec2_healthy(
    ip_address: str,
    port: int = 8080,
    timeout_seconds: int = 300,
    poll_interval: int = 10,
) -> bool:
    """Poll http://{ip}:{port}/actuator/health until 200 or timeout.

    Returns True if healthy within the timeout, False if timed out.
    """
    url = f"http://{ip_address}:{port}/actuator/health"
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(poll_interval)
    return False
