"""Configuration for the Hirist Scraper. Everything can be set with an
environment variable; the defaults work out of the box.

    PORT           port the API listens on (default 8000)
    HIRIST_PROXY   proxy URL for every request, e.g. http://user:pass@host:port
                   (default: none — direct). Hirist's job API did not rate-limit
                   or challenge plain requests in testing, so you very likely
                   don't need this. Set it only if you start seeing failures at
                   high volume.

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors and blocks (every request).
MAX_RETRIES = 3
HIRIST_MAX_ATTEMPTS = MAX_RETRIES

# Parallel upstream calls inside one request (search with include_details, batch).
HIRIST_WORKERS = 6

HIRIST_PROXY = os.environ.get("HIRIST_PROXY") or None


def hirist_proxy(fallback=False):
    """The proxy for a hirist request (None = direct). The same proxy serves
    the first attempt and every retry."""
    return os.environ.get("HIRIST_PROXY") or None
