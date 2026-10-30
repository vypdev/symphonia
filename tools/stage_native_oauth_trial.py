"""Build bounded source artifacts and the self-contained HA helper installer."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import textwrap
import zipfile

REPO = Path(__file__).resolve().parents[1]
HELPER = "custom_components/symphonia_native_oauth_trial"
APP = "symphonia_native_oauth_trial"
HELPER_FILES = ("__init__.py", "manifest.json", "config_flow.py", "bridge.py", "keys.py", "strings.json", "translations/en.json", "translations/es.json")
APP_FILES = ("config.yaml", "Dockerfile", "requirements.txt", "README.md", "run.py", "policy.py", "application.py", "keys.py", "store.py", "provider.py", "tls.py", "server.py")


def source(path: Path):
    for parent in (path, *path.parents):
        if parent == REPO.parent:
            break
        if parent.is_symlink():
            raise ValueError("source_symlink_refused")
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= 262144:
        raise ValueError("bounded_regular_source_required")
    return path.read_bytes()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def source_manifest(files):
    return ("# SYMPHONIA_NATIVE_OAUTH_TRIAL_SOURCE_V1\n" + "".join(digest(raw)+"  "+name+"\n" for name,raw in files.items())).encode()


def installer(files):
    manifest = source_manifest(files)
    shell = r'''#!/bin/sh
# Generated from reviewed helper sources; regenerate with stage_native_oauth_trial.py.
set -eu
umask 077
trial_mode=${1:-}
trial_root=${2:-/homeassistant}
trial_expected=@MANIFEST_SHA@
trial_namespace=symphonia_native_oauth_trial
trial_stage=
refuse() { printf '%s\n' 'Refused: preserve existing, modified or unowned trial files.' >&2; exit 1; }
case "$trial_mode" in install|remove) ;; *) printf '%s\n' 'Usage: sh installer.sh install|remove [Core-config-root]'; exit 2;; esac
case "$trial_root" in /*) ;; *) refuse;; esac
case "$trial_root" in *[!A-Za-z0-9_./@-]*|*/../*|*/./*|*/..|*//*) refuse;; esac
for trial_tool in base64 sha256sum stat id mkdir mktemp mv chmod rm rmdir tail; do command -v "$trial_tool" >/dev/null 2>&1 || refuse; done
test -d "$trial_root" && test ! -L "$trial_root" && test -f "$trial_root/.HA_VERSION" && test ! -L "$trial_root/.HA_VERSION" || refuse
trial_parent=$trial_root/custom_components
trial_target=$trial_parent/$trial_namespace
if test -L "$trial_parent"; then refuse; fi
if test -e "$trial_parent" && test ! -d "$trial_parent"; then refuse; fi
owned_file() {
    test -f "$1" && test ! -L "$1" || refuse
    test "$(stat -c '%h' "$1")" = 1 || refuse
    test "$(stat -c '%u' "$1")" = "$(id -u)" || refuse
}
file_hash() { trial_hash=$(sha256sum "$1"); printf '%s' "${trial_hash%% *}"; }
cleanup_stage() {
    if test -n "$trial_stage" && test -d "$trial_stage" && test ! -L "$trial_stage"; then
        # Only this process's mktemp directory and its fixed decoded files.
        @CLEAN_STAGE@
        rmdir "$trial_stage/translations" 2>/dev/null || true
        rmdir "$trial_stage" 2>/dev/null || true
    fi
}
trap cleanup_stage EXIT HUP INT TERM
if test "$trial_mode" = install; then
    test ! -e "$trial_target" && test ! -L "$trial_target" || refuse
    if test ! -d "$trial_parent"; then mkdir "$trial_parent"; chmod 755 "$trial_parent"; fi
    trial_stage=$(mktemp -d "$trial_parent/.symphonia-native-stage.XXXXXX")
    mkdir "$trial_stage/translations"
@PAYLOAD@
    cat > "$trial_stage/.source-owned.sha256" <<'SYMPHONIA_SOURCE_MANIFEST'
@MANIFEST@SYMPHONIA_SOURCE_MANIFEST
    test "$(file_hash "$trial_stage/.source-owned.sha256")" = "$trial_expected" || refuse
    (cd "$trial_stage" && tail -n +2 .source-owned.sha256 | sha256sum -c - >/dev/null 2>&1) || refuse
    chmod 755 "$trial_stage" "$trial_stage/translations"
    @CHMOD_SOURCE@
    test ! -e "$trial_target" && test ! -L "$trial_target" || refuse
    mv -Tn "$trial_stage" "$trial_target"
    test ! -e "$trial_stage" || refuse
    trial_stage=
    printf '%s\n' 'Installed verified trial helper. Check Core configuration, then restart Core.'
    exit 0
fi
test -d "$trial_target" && test ! -L "$trial_target" || refuse
owned_file "$trial_target/.source-owned.sha256"
test "$(file_hash "$trial_target/.source-owned.sha256")" = "$trial_expected" || refuse
@VERIFY_SOURCE@
(cd "$trial_target" && tail -n +2 .source-owned.sha256 | sha256sum -c - >/dev/null 2>&1) || refuse
for trial_entry in "$trial_target"/* "$trial_target"/.[!.]* "$trial_target"/..?*; do
    test -e "$trial_entry" || test -L "$trial_entry" || continue
    case "${trial_entry##*/}" in __init__.py|manifest.json|config_flow.py|bridge.py|keys.py|strings.json|translations|.source-owned.sha256|.cache-owned.sha256|__pycache__) ;; *) refuse;; esac
done
test -d "$trial_target/translations" && test ! -L "$trial_target/translations" || refuse
for trial_entry in "$trial_target/translations"/* "$trial_target/translations"/.[!.]* "$trial_target/translations"/..?*; do
    test -e "$trial_entry" || test -L "$trial_entry" || continue
    case "${trial_entry##*/}" in en.json|es.json) ;; *) refuse;; esac
done
if test -e "$trial_target/.cache-owned.sha256" || test -L "$trial_target/.cache-owned.sha256"; then
    owned_file "$trial_target/.cache-owned.sha256"
    trial_first=1
    trial_seen_cache='|'
    while IFS=' ' read -r trial_hash trial_name; do
        if test "$trial_first" = 1; then
            test "$trial_hash $trial_name" = "# SYMPHONIA_NATIVE_OAUTH_TRIAL_CACHE_V1 $trial_expected" || refuse
            trial_first=0
            continue
        fi
        case "$trial_name" in __pycache__/__init__.cpython-314.pyc|__pycache__/config_flow.cpython-314.pyc|__pycache__/bridge.cpython-314.pyc|__pycache__/keys.cpython-314.pyc) ;; *) refuse;; esac
        case "$trial_seen_cache" in *"|$trial_name|"*) refuse;; esac
        trial_seen_cache="${trial_seen_cache}${trial_name}|"
        case "$trial_hash" in ''|*[!0-9a-f]*) refuse;; esac
        test "${#trial_hash}" = 64 || refuse
        owned_file "$trial_target/$trial_name"
    done < "$trial_target/.cache-owned.sha256"
    test "$trial_first" = 0 || refuse
    # Header-only cache records are valid when Core disables bytecode writes.
    if test -d "$trial_target/__pycache__"; then
        test ! -L "$trial_target/__pycache__" || refuse
        for trial_entry in "$trial_target/__pycache__"/* "$trial_target/__pycache__"/.[!.]* "$trial_target/__pycache__"/..?*; do
            test -e "$trial_entry" || test -L "$trial_entry" || continue
            owned_file "$trial_entry"
            trial_recorded=0
            while IFS=' ' read -r trial_hash trial_name; do
                if test "$trial_name" = "__pycache__/${trial_entry##*/}"; then
                    test "$(file_hash "$trial_entry")" = "$trial_hash" || refuse
                    trial_recorded=1
                fi
            done < "$trial_target/.cache-owned.sha256"
            test "$trial_recorded" = 1 || refuse
        done
    fi
elif test -e "$trial_target/__pycache__" || test -L "$trial_target/__pycache__"; then
    refuse
fi
# Every source and additional path was checked before any removal.
@REMOVE_SOURCE@
if test -f "$trial_target/.cache-owned.sha256"; then
    trial_first=1
    while IFS=' ' read -r trial_hash trial_name; do
        if test "$trial_first" = 1; then trial_first=0; continue; fi
        rm "$trial_target/$trial_name"
    done < "$trial_target/.cache-owned.sha256"
    rm "$trial_target/.cache-owned.sha256"
fi
if test -d "$trial_target/__pycache__"; then rmdir "$trial_target/__pycache__"; fi
rm "$trial_target/.source-owned.sha256"
rmdir "$trial_target/translations" "$trial_target"
printf '%s\n' 'Removed hash-matching trial source only. Check configuration and restart Core. Provider revocation is separate.'
'''
    payload=[]
    for index,(name,raw) in enumerate(files.items()):
        tag="SYMPHONIA_FILE_"+str(index)
        payload.append('    base64 -d > "$trial_stage/'+name+'" <<\''+tag+'\'\n'+"\n".join(textwrap.wrap(base64.b64encode(raw).decode(),76))+"\n"+tag)
    replacements={"@MANIFEST_SHA@":digest(manifest), "@MANIFEST@":manifest.decode(), "@PAYLOAD@":"\n".join(payload),
        "@CHMOD_SOURCE@":"\n    ".join('chmod 644 "$trial_stage/'+name+'"' for name in files),
        "@CLEAN_STAGE@":"\n        ".join('rm -f "$trial_stage/'+name+'"' for name in (*files,".source-owned.sha256")),
        "@VERIFY_SOURCE@":"\n".join('owned_file "$trial_target/'+name+'"' for name in files),
        "@REMOVE_SOURCE@":"\n".join('rm "$trial_target/'+name+'"' for name in files)}
    for marker,value in replacements.items():
        shell=shell.replace(marker,value)
    return shell.encode()


def generate():
    files={name:source(REPO/HELPER/name) for name in HELPER_FILES}
    raw=installer(files)
    target=REPO/"tools/install_native_oauth_trial_helper.sh"
    if target.is_symlink():
        raise ValueError("installer_output_symlink_refused")
    target.write_bytes(raw)
    target.chmod(0o755)
    app={name:source(REPO/APP/name) for name in APP_FILES}
    manifest="".join(digest(raw)+"  "+name+"\n" for name,raw in app.items()).encode()
    target=REPO/APP/"SHA256SUMS"
    if target.is_symlink():
        raise ValueError("app_manifest_symlink_refused")
    target.write_bytes(manifest)
    return files,raw,app,manifest


def stage(output: Path):
    if output.is_symlink() or output.exists() or any(p.is_symlink() for p in output.parents):
        raise ValueError("fresh_real_output_required")
    files,script,app,app_manifest=generate()
    output.mkdir(mode=0o700)
    (output/".owned").write_text("symphonia-native-trial-artifacts-v1\n")
    (output/"install-helper.sh").write_bytes(script)
    with zipfile.ZipFile(output/"helper.zip","w",compression=zipfile.ZIP_DEFLATED) as archive:
        for name,raw in {**files,".source-owned.sha256":source_manifest(files)}.items():
            info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.external_attr=(stat.S_IFREG|0o644)<<16
            archive.writestr(info,raw)
    target=output/"app";target.mkdir()
    for name,raw in {**app,"SHA256SUMS":app_manifest}.items():
        (target/name).write_bytes(raw)
    revision=subprocess.check_output(["git","rev-parse","HEAD"],cwd=REPO,text=True).strip()
    dirty=bool(subprocess.check_output(["git","status","--porcelain"],cwd=REPO))
    receipt={"format":"symphonia-native-trial-artifacts-v1","revision":revision,"dirty":dirty,
        "installer_sha256":digest(script),"helper_zip_sha256":digest((output/"helper.zip").read_bytes()),
        "helper_manifest_sha256":digest(source_manifest(files)),"app_manifest_sha256":digest(app_manifest),
        "files":{HELPER+"/"+name:digest(raw) for name,raw in files.items()}}
    receipt["files"].update({APP+"/"+name:digest(raw) for name,raw in app.items()})
    (output/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
    return receipt


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    if args.output:
        value=stage(args.output)
        print(json.dumps({key:value[key] for key in ("revision","dirty","installer_sha256","helper_zip_sha256","app_manifest_sha256")}))
    else:
        files,script,app,manifest=generate()
        print(json.dumps({"helper_files":len(files),"app_files":len(app),"installer_sha256":digest(script),"app_manifest_sha256":digest(manifest)}))
