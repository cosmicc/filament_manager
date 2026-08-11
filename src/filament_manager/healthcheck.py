"""Container readiness probe for the Filament Manager web process."""

from __future__ import annotations

import os
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

READINESS_URL = "http://127.0.0.1:8080/health/ready"
HEALTHCHECK_TIMEOUT_SECONDS = 4


def configured_public_hostname() -> str:
    """Return the public hostname that the application accepts as trusted."""

    base_url = os.environ.get("FILAMENT_MANAGER_BASE_URL", "")
    hostname = urlsplit(base_url).hostname
    if hostname is None:
        raise RuntimeError("FILAMENT_MANAGER_BASE_URL must contain a hostname")
    return hostname


def check_readiness() -> None:
    """Raise when the loopback readiness endpoint does not return success."""

    request = Request(
        READINESS_URL,
        headers={"Host": configured_public_hostname()},
        method="GET",
    )
    # The URL is a fixed loopback endpoint; only the validated public Host header is configurable.
    with urlopen(request, timeout=HEALTHCHECK_TIMEOUT_SECONDS) as response:  # noqa: S310
        response.read()


def main() -> None:
    """Run the container readiness probe."""

    check_readiness()


if __name__ == "__main__":
    main()
