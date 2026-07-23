#!/usr/bin/env python3
"""Durable manifest-managed sync/restore transactions."""
from __future__ import annotations

import fcntl
import json
import os
import shutil
import stat
import sys
import time
from pathlib import Path, PurePosixPath
from typing import Any

OPENCLAW_FILES = ("docker-compose.yml", "entrypoint.sh", "Dockerfile.mira", "toolchain.lock.json")


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def mkdir_durable(path: Path) -> None:
    missing: list[Path] = []
    current = path
    while not current.exists():
        missing.append(current)
        current = current.parent
    path.mkdir(parents=True, exist_ok=True)
    for created in reversed(missing):
        fsync_dir(created)
        fsync_dir(created.parent)


def durable_json(path: Path, value: dict[str, Any]) -> None:
    mkdir_durable(path.parent)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    fsync_dir(path.parent)


def copy_durable(source: Path, destination: Path) -> None:
    mkdir_durable(destination.parent)
    shutil.copy2(source, destination, follow_symlinks=False)
    with destination.open("rb") as stream:
        os.fsync(stream.fileno())
    fsync_dir(destination.parent)


def validate_root(path: Path, label: str, *, create: bool = False) -> Path:
    absolute = path.expanduser().absolute()
    if create:
        current = absolute
        while not current.exists() and current != current.parent:
            current = current.parent
        if current.is_symlink() or current.resolve(strict=True) != current:
            raise RuntimeError(f"{label} must be a canonical non-symlink directory: {absolute}")
        mkdir_durable(absolute)
    try:
        info = absolute.lstat()
    except OSError as exc:
        raise RuntimeError(f"{label} does not exist: {absolute}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise RuntimeError(f"{label} must be a canonical non-symlink directory: {absolute}")
    canonical = absolute.resolve(strict=True)
    if canonical != absolute:
        raise RuntimeError(f"{label} must be a canonical non-symlink directory: {absolute}")
    return canonical


def regular(path: Path, label: str) -> None:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise RuntimeError(f"{label} must be a regular non-symlink file: {path}")


def relative(value: str) -> Path:
    pure = PurePosixPath(value)
    if pure.is_absolute() or not pure.parts or any(part in ("", ".", "..") for part in pure.parts):
        raise RuntimeError(f"unsafe manifest path: {value!r}")
    normalized = PurePosixPath(*pure.parts)
    if normalized.as_posix() != value:
        raise RuntimeError(f"manifest path is not normalized: {value!r}")
    return Path(*normalized.parts)


def beneath(path: Path, root: Path, label: str, *, must_exist: bool) -> Path:
    absolute = path.absolute()
    probe = absolute.resolve(strict=must_exist)
    if probe != root and root not in probe.parents:
        raise RuntimeError(f"{label} escapes managed root {root}: {path}")
    current = absolute if must_exist else absolute.parent
    while current != root:
        if current.is_symlink():
            raise RuntimeError(f"{label} contains a symlink component: {current}")
        if current == current.parent:
            raise RuntimeError(f"{label} is not beneath managed root {root}: {path}")
        current = current.parent
    return probe


def manifest_paths(manifest: Path) -> list[Path]:
    regular(manifest, "workspace manifest")
    values: list[Path] = []
    normalized: set[str] = set()
    for raw in manifest.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        item = relative(line)
        key = item.as_posix()
        if key in normalized:
            raise RuntimeError(f"duplicate normalized manifest entry: {key}")
        normalized.add(key)
        values.append(item)
    return values


def recover(transaction: Path) -> None:
    metadata_path = transaction / "metadata.json"
    if not metadata_path.exists():
        shutil.rmtree(transaction)
        fsync_dir(transaction.parent)
        return
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("state") in {"complete", "rolled_back"}:
        return
    entries = metadata.get("entries")
    if not isinstance(entries, list):
        raise RuntimeError(f"invalid transaction metadata: {metadata_path}")
    for entry in reversed(entries):
        if entry.get("status") not in {"intent", "applied"}:
            continue
        destination = Path(entry["destination"])
        backup = Path(entry["backup"])
        if entry.get("had_prior"):
            regular(backup, "transaction backup")
            mkdir_durable(destination.parent)
            recovery_copy = destination.with_name(
                f".{destination.name}.recovery-{os.getpid()}.tmp"
            )
            copy_durable(backup, recovery_copy)
            os.replace(recovery_copy, destination)
            with destination.open("rb") as stream:
                os.fsync(stream.fileno())
            fsync_dir(destination.parent)
        elif destination.exists() or destination.is_symlink():
            regular(destination, "new transaction destination")
            destination.unlink()
            fsync_dir(destination.parent)
        entry["status"] = "rolled_back"
        durable_json(metadata_path, metadata)
    metadata["state"] = "rolled_back"
    metadata["recovered_at"] = int(time.time())
    durable_json(metadata_path, metadata)


def build_entries(
    operation: str,
    root: Path,
    workspace: Path,
    source: Path,
    manifest: Path,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for rel in manifest_paths(manifest):
        if operation == "sync":
            src, dst = workspace / rel, root / "workspace" / rel
        else:
            src, dst = root / "workspace" / rel, workspace / rel
        entries.append({"source": src, "destination": dst, "label": f"workspace/{rel.as_posix()}"})
    for name in OPENCLAW_FILES:
        if operation == "sync":
            src, dst = source / name, root / "openclaw" / name
        else:
            src, dst = root / "openclaw" / name, source / name
        entries.append({"source": src, "destination": dst, "label": f"openclaw/{name}"})
    labels = [entry["label"] for entry in entries]
    if len(labels) != len(set(labels)):
        raise RuntimeError("duplicate normalized managed destination")
    return entries


def run(operation: str, root_arg: str, home_arg: str, workspace_arg: str, source_arg: str, manifest_arg: str) -> None:
    if operation not in {"sync", "restore"}:
        raise RuntimeError("operation must be sync or restore")
    root = validate_root(Path(root_arg), "blueprint root")
    create_targets = operation == "restore"
    home = validate_root(Path(home_arg), "OpenClaw home", create=create_targets)
    workspace = validate_root(Path(workspace_arg), "workspace root", create=create_targets)
    source = validate_root(Path(source_arg), "OpenClaw source root", create=create_targets)
    manifest = Path(manifest_arg).expanduser().absolute()
    regular(manifest, "workspace manifest")

    transaction_parent = (root / ".sync-rollback") if operation == "sync" else (home / ".restore-rollback")
    mkdir_durable(transaction_parent)
    lock_path = transaction_parent / ".transaction.lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for prior in sorted(transaction_parent.iterdir()):
            if prior.is_dir():
                recover(prior)

        entries = build_entries(operation, root, workspace, source, manifest)
        source_roots = {
            "workspace": workspace if operation == "sync" else root / "workspace",
            "openclaw": source if operation == "sync" else root / "openclaw",
        }
        destination_roots = {
            "workspace": root / "workspace" if operation == "sync" else workspace,
            "openclaw": root / "openclaw" if operation == "sync" else source,
        }
        for label, candidate in list(source_roots.items()):
            source_roots[label] = validate_root(candidate, f"{label} source root")
        for label, candidate in list(destination_roots.items()):
            destination_roots[label] = validate_root(candidate, f"{label} destination root", create=True)

        transaction = transaction_parent / f"{time.time_ns()}-{os.getpid()}"
        mkdir_durable(transaction)
        stage, backup = transaction / "stage", transaction / "backup"
        metadata: dict[str, Any] = {
            "schema_version": 1,
            "operation": operation,
            "state": "staging",
            "entries": [],
        }
        durable_json(transaction / "metadata.json", metadata)
        for entry in entries:
            kind = entry["label"].split("/", 1)[0]
            src = beneath(entry["source"], source_roots[kind], "managed source", must_exist=True)
            regular(src, "managed source")
            dst = entry["destination"].absolute()
            beneath(dst, destination_roots[kind], "managed destination", must_exist=False)
            if dst.exists() or dst.is_symlink():
                regular(dst, "managed destination")
            staged = stage / entry["label"]
            prior = backup / entry["label"]
            metadata_entry = {
                "label": entry["label"],
                "kind": kind,
                "destination": str(dst),
                "stage": str(staged),
                "backup": str(prior),
                "had_prior": None,
                "status": "staging",
            }
            metadata["entries"].append(metadata_entry)
            durable_json(transaction / "metadata.json", metadata)
            copy_durable(src, staged)
            metadata_entry["status"] = "staged"
            durable_json(transaction / "metadata.json", metadata)

        try:
            metadata["state"] = "applying"
            durable_json(transaction / "metadata.json", metadata)
            fail_after = int(os.environ.get(
                "MIRA_RESTORE_FAIL_AFTER" if operation == "restore" else "MIRA_SYNC_FAIL_AFTER", "0"
            ))
            kill_after = int(os.environ.get("MIRA_TRANSACTION_KILL_AFTER", "0"))
            for index, entry in enumerate(metadata["entries"], 1):
                destination = Path(entry["destination"])
                beneath(
                    destination,
                    destination_roots[entry["kind"]],
                    "managed destination",
                    must_exist=destination.exists(),
                )
                mkdir_durable(destination.parent)
                had_prior = destination.exists()
                entry["had_prior"] = had_prior
                if had_prior:
                    copy_durable(destination, Path(entry["backup"]))
                entry["status"] = "intent"
                durable_json(transaction / "metadata.json", metadata)
                os.replace(entry["stage"], destination)
                with destination.open("rb") as stream:
                    os.fsync(stream.fileno())
                fsync_dir(destination.parent)
                if kill_after and index >= kill_after:
                    os.kill(os.getpid(), 9)
                entry["status"] = "applied"
                durable_json(transaction / "metadata.json", metadata)
                if fail_after and index >= fail_after:
                    raise RuntimeError(f"injected {operation} failure")
        except BaseException:
            recover(transaction)
            raise

        metadata["state"] = "complete"
        metadata["completed_at"] = int(time.time())
        durable_json(transaction / "metadata.json", metadata)
        verb = "synced" if operation == "sync" else "restored"
        print(f"{verb} {len(entries)} managed files; rollback metadata: {transaction}")


def main() -> None:
    if len(sys.argv) != 7:
        raise SystemExit("usage: managed_transaction.py OP ROOT HOME WORKSPACE SOURCE MANIFEST")
    run(*sys.argv[1:])


if __name__ == "__main__":
    main()
