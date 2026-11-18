"""Capture the generated HTML result report using local Chrome or Chromium."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]


def positive_int(value: str) -> int:
    """Accept a strictly positive viewport dimension."""
    result = int(value)
    if result <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return result


def positive_float(value: str) -> float:
    """Accept a strictly positive capture scale."""
    result = float(value)
    if not 0 < result < float("inf"):
        raise argparse.ArgumentTypeError("must be a finite number greater than zero")
    return result


def find_browser(explicit: str | None) -> str | None:
    """Resolve an explicit browser, CHROME_BIN, or a common installation."""
    candidates = (
        [explicit]
        if explicit
        else [
            os.environ.get("CHROME_BIN", ""),
            "google-chrome",
            "chromium",
            "chromium-browser",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    )
    return next((found for candidate in candidates if candidate and (found := shutil.which(candidate))), None)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html", type=Path, default=REPOSITORY / "docs/results/index.html")
    parser.add_argument("--output", type=Path, default=REPOSITORY / "docs/results/snapshot.png")
    parser.add_argument("--browser", help="Chrome/Chromium executable; otherwise use CHROME_BIN or auto-discovery")
    parser.add_argument("--width", type=positive_int, default=1440)
    parser.add_argument("--height", type=positive_int, default=1700)
    parser.add_argument("--scale", type=positive_float, default=2.0)
    args = parser.parse_args()
    source = args.html.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if not source.is_file():
        parser.error(f"Report not found: {source}. Run python -m src.inspection first.")
    if source == output:
        parser.error("--output must differ from --html")
    browser = find_browser(args.browser)
    if browser is None:
        parser.error("Chrome/Chromium not found. Install it, pass --browser, or set CHROME_BIN.")

    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="gold-rule-snapshot-") as temporary:
            capture = Path(temporary) / "snapshot.png"
            command = [
                browser,
                "--headless",
                "--disable-gpu",
                "--hide-scrollbars",
                "--no-first-run",
                "--no-default-browser-check",
                "--allow-file-access-from-files",
                f"--force-device-scale-factor={args.scale}",
                f"--window-size={args.width},{args.height}",
                f"--user-data-dir={Path(temporary) / 'browser'}",
                f"--screenshot={capture}",
                source.as_uri(),
            ]
            result = subprocess.run(command, capture_output=True, text=True, timeout=45)
            if result.returncode:
                detail = result.stderr.strip() or result.stdout.strip() or "No browser error output"
                parser.exit(1, f"Snapshot failed (browser exit {result.returncode}):\n{detail[-3000:]}\n")
            if not capture.is_file() or capture.stat().st_size == 0:
                parser.exit(1, "Chrome exited without creating a non-empty screenshot.\n")
            shutil.copyfile(capture, output)
    except (OSError, subprocess.TimeoutExpired) as exc:
        parser.exit(1, f"Snapshot failed: {exc}\n")
    print(f"Snapshot saved to {output}")


if __name__ == "__main__":
    main()
