#!/usr/bin/env python3
"""Download a verified NetworkShare release and launch its interactive setup."""
import argparse
import hashlib
import json
import re
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
from urllib.request import Request, urlopen


DEFAULT_MANIFEST = "https://johnnylragland-beep.github.io/networkshare-update/update-manifest.json"


def open_url(url):
    if urlparse(url).scheme != "https":
        raise ValueError("Download URLs must use HTTPS.")
    response = urlopen(Request(url, headers={"User-Agent": "NetworkShare-Installer"}), timeout=60)
    if urlparse(response.geturl()).scheme != "https":
        response.close()
        raise ValueError("Download redirected to a non-HTTPS URL.")
    return response


def download_release(manifest_url, archive):
    with open_url(manifest_url) as response:
        manifest = json.load(response)
    checksum = manifest.get("sha256", "")
    if not isinstance(checksum, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", checksum):
        raise ValueError("Release manifest must contain a SHA-256 checksum.")
    print("Downloading NetworkShare {}...".format(manifest["version"]), flush=True)
    digest = hashlib.sha256()
    with open_url(manifest["package_url"]) as response, archive.open("wb") as output:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            output.write(chunk)
    if digest.hexdigest() != checksum.lower():
        raise ValueError("Release checksum mismatch; installation stopped.")
    return manifest


def extract_release(archive, staging):
    with zipfile.ZipFile(archive) as package:
        members = package.infolist()
        if not members:
            raise ValueError("Release archive is empty.")
        roots = set()
        # Validate everything before writing any archive contents.
        for member in members:
            path = PurePosixPath(member.filename)
            if (path.is_absolute() or ".." in path.parts or not path.parts
                    or "\\" in member.filename or ":" in member.filename
                    or stat.S_ISLNK(member.external_attr >> 16)):
                raise ValueError("Unsafe release archive path: {}".format(member.filename))
            roots.add(path.parts[0])
        if len(roots) != 1:
            raise ValueError("Expected one project folder in the release archive.")
        package.extractall(staging)
    project = staging / roots.pop()
    for required in ("Main-Server/setup-main.py", "Agent/setup-agent.py", "setup_common.py", "requirements.txt"):
        if not (project / required).is_file():
            raise ValueError("Release is missing {}.".format(required))
    if sys.platform != "win32":
        for script in project.rglob("*.sh"):
            script.chmod(script.stat().st_mode | 0o111)
    return project


def install(destination, manifest_url):
    if destination.exists():
        raise ValueError("Destination already exists: {}. Choose a new --directory; use the app updater for an existing install.".format(destination))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".networkshare-install-", dir=str(destination.parent)) as temporary:
        staging = Path(temporary)
        archive = staging / "release.zip"
        download_release(manifest_url, archive)
        project = extract_release(archive, staging / "unpacked")
        # Check again after downloading, so an existing install is never merged.
        if destination.exists():
            raise ValueError("Destination was created during download: {}".format(destination))
        project.rename(destination)
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=("main", "agent"), help="Which setup wizard to start (prompts if omitted).")
    parser.add_argument("--directory", type=Path, default=Path.cwd() / "networkshare", help="New install folder (default: ./networkshare).")
    parser.add_argument("--manifest-url", default=DEFAULT_MANIFEST, help="HTTPS release manifest URL.")
    parser.add_argument("--download-only", action="store_true", help="Download and verify without running setup.")
    args = parser.parse_args(argv)
    try:
        project = install(args.directory.expanduser().resolve(), args.manifest_url)
        print("Installed files to {}".format(project), flush=True)
        role = args.role
        if not role and not args.download_only:
            print("\nWhat would you like to install?\n  1) Main server\n  2) Agent")
            while role not in ("main", "agent"):
                answer = input("Choose [1/2]: ").strip().lower()
                role = {"1": "main", "2": "agent"}.get(answer, answer)
        if args.download_only:
            print("Run Python on Main-Server/setup-main.py or Agent/setup-agent.py inside that folder to configure it.")
            return 0
        setup = project / ("Main-Server/setup-main.py" if role == "main" else "Agent/setup-agent.py")
        print("Starting {} setup...".format(role), flush=True)
        return subprocess.call([sys.executable, str(setup)], cwd=str(project))
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, EOFError) as exc:
        print("Installation failed: {}".format(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInstallation cancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
