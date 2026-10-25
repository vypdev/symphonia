"""Export an immutable, hash-verified local HA research App and staging script."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile


PROJECT = Path(__file__).resolve().parents[1]
FILES = ("Dockerfile", "config.yaml", "server.py", "README.md")
SOURCE = "tools/ha_oauth_trial/"


def prepare(revision, destination):
    if re.fullmatch(r"[a-f0-9]{40}", revision) is None:
        raise ValueError("an exact 40-character commit is required")
    # No worktree input enters an export of an immutable revision.
    contents = {name: subprocess.run(["git", "show", revision + ":" + SOURCE + name],
        cwd=PROJECT, check=True, capture_output=True).stdout for name in FILES}
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    manifest = {"source_commit": revision, "files": {
        name: hashlib.sha256(body).hexdigest() for name, body in contents.items()}}
    tar_bytes = io.BytesIO()
    with tarfile.open(fileobj=tar_bytes, mode="w") as archive:
        for name, body in contents.items():
            item = tarfile.TarInfo("symphonia_oauth_trial/" + name)
            item.size, item.mode, item.mtime = len(body), 0o644, 0
            archive.addfile(item, io.BytesIO(body))
    with (destination / "symphonia-oauth-trial.tar.gz").open("wb") as output:
        with gzip.GzipFile(filename="", fileobj=output, mode="wb", mtime=0) as zipped:
            zipped.write(tar_bytes.getvalue())
    lines = ["#!/bin/sh", "set -eu", "test -d /addons && test ! -L /addons",
        "test ! -e /addons/symphonia_oauth_trial && test ! -L /addons/symphonia_oauth_trial",
        'trial_tmp="$(mktemp -d /tmp/symphonia-oauth-trial.XXXXXX)"',
        "trap 'rm -rf \"$trial_tmp\"' EXIT HUP INT TERM"]
    for name in FILES:
        url = "https://raw.githubusercontent.com/vypdev/symphonia/" + revision + "/" + SOURCE + name
        lines += [f'curl --proto "=https" --tlsv1.2 --fail --silent --show-error --max-time 60 "{url}" -o "$trial_tmp/{name}"',
            f'printf "%s  %s\\n" "{manifest["files"][name]}" "$trial_tmp/{name}" | sha256sum -c - >/dev/null']
    lines += ["mkdir /addons/symphonia_oauth_trial"]
    lines += [f'cp "$trial_tmp/{name}" /addons/symphonia_oauth_trial/{name}' for name in FILES]
    lines += ["ha store reload", f"printf '%s\\n' 'Staged reviewed trial source {revision}; install manually from Local Apps.'"]
    (destination / "stage-in-home-assistant.sh").write_text("\n".join(lines) + "\n")
    manifest["archive_sha256"] = hashlib.sha256((destination / "symphonia-oauth-trial.tar.gz").read_bytes()).hexdigest()
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = prepare(args.revision, args.output)
    print(json.dumps({"source_commit": result["source_commit"], "archive_sha256": result["archive_sha256"]}))
