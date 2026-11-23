"""Real directory workspace; Git commits are immutable catalog/plan revisions.

Only service-owned workspaces are supported. Writers use one exclusive lock;
all reads take the same lock so partially applied batches cannot be observed.
"""
import json
import os
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
import re
import subprocess

from .models import ProcessPlan, Resource

SECTIONS = ("general", "equipment", "workplaces", "tooling", "materials", "capabilities", "quality", "subcontractors")
MAX_FILE = 64_000


class Store:
    def __init__(self, root: str | Path):
        self.root = Path(root).absolute()

    def git(self, *args: str) -> str:
        result = subprocess.run(["git", "-C", str(self.root), *args], stdin=subprocess.DEVNULL,
                                capture_output=True, encoding="utf-8", timeout=30)
        if result.returncode:
            raise ValueError(result.stderr.strip() or "git operation failed")
        return result.stdout.strip()

    @contextmanager
    def locked(self):
        self.root.mkdir(parents=True, exist_ok=True)
        lock = self.root / ".planning.lock"
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise ValueError("workspace_busy: another request is active; stale locks require operator inspection") from None
        try:
            os.close(fd)
            yield
        finally:
            lock.unlink()

    def initialize(self) -> dict:
        with self.locked():
            if (self.root / ".git").exists():
                if not (self.root / ".planning-workspace").exists():
                    raise ValueError("not a service-owned workspace")
                return {"revision": self.git("rev-parse", "HEAD")}
            if any(p.name != ".planning.lock" for p in self.root.iterdir()):
                raise ValueError("initialization requires an empty directory")
            self.git("init", "-b", "main")
            self.git("config", "user.name", "Process Planning")
            self.git("config", "user.email", "process-planning@localhost")
            self.git("config", "core.quotePath", "false")
            (self.root / ".gitignore").write_text(".planning.lock\n", encoding="utf-8")
            (self.root / ".planning-workspace").write_text("1\n", encoding="utf-8")
            for section in SECTIONS:
                self.path(f"factory/{section}").mkdir(parents=True)
                self.path(f"factory/{section}/.keep").touch()
            self.path("processes").mkdir()
            self.path("processes/.keep").touch()
            self.git("add", "--all")
            self.git("commit", "-m", "Initialize production catalog")
            return {"revision": self.git("rev-parse", "HEAD")}

    def path(self, value: str) -> Path:
        parts = PurePosixPath(value).parts
        if (not parts or parts[0] not in ("factory", "processes") or "\\" in value or any(ord(c) < 32 for c in value)
                or any(p in (".", "..") or p.startswith(".") and p != ".keep" or ":" in p for p in parts)
                or value != "/".join(parts)):
            raise ValueError("invalid workspace path; use factory/... or processes/...")
        target = self.root.joinpath(*parts)
        if not target.resolve().is_relative_to(self.root.resolve()):
            raise ValueError("path escapes workspace")
        if any(p.is_symlink() or getattr(p, "is_junction", lambda: False)() for p in [target, *target.parents] if p != self.root.parent):
            raise ValueError("symlinks and junctions are not supported")
        return target

    def revision(self, value: str | None = None) -> str:
        if not (self.root / ".planning-workspace").is_file():
            raise ValueError("workspace not initialized")
        if value is not None and not re.fullmatch(r"[0-9a-f]{40}", value):
            raise ValueError("revision must be a full commit hash")
        return self.git("rev-parse", "--verify", f"{value or 'HEAD'}^{{commit}}")

    def files(self, revision: str) -> list[str]:
        return self.git("ls-tree", "-r", "--name-only", revision, "--", "factory", "processes").splitlines()

    def load(self, path: str, revision: str) -> dict:
        self.path(path)
        return json.loads(self.git("show", f"{revision}:{path}"))

    def read(self, path: str, revision: str | None = None) -> dict:
        with self.locked():
            rev = self.revision(revision)
            return {"revision": rev, "path": path, "record": self.load(path, rev)}

    def browse(self, path: str = "factory", revision: str | None = None, offset: int = 0, limit: int = 30, text: str = "") -> dict:
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("limit 1..100, offset >= 0")
        self.path(path)
        with self.locked():
            rev = self.revision(revision)
            entries = {}
            for filename in self.files(rev):
                if not filename.startswith(path + "/") or filename.endswith("/.keep"):
                    continue
                relative = filename[len(path) + 1:]
                if text:
                    record = self.load(filename, rev)
                    if text.casefold() not in json.dumps(record, ensure_ascii=False).casefold():
                        continue
                    entries[filename] = {"path": filename, "type": "record", "id": record["id"], "name": record["name"]}
                else:
                    child = relative.split("/")[0]
                    key = path + "/" + child
                    entries[key] = {"path": key, "type": "directory" if "/" in relative else "record"}
            # Git tracks empty directories with explicit markers.
            if not text:
                for filename in self.files(rev):
                    if filename.startswith(path + "/") and filename.endswith("/.keep"):
                        child = filename[len(path) + 1:].split("/")[0]
                        if child != ".keep":
                            entries[path + "/" + child] = {"path": path + "/" + child, "type": "directory"}
            values = sorted(entries.values(), key=lambda x: x["path"])
            more = offset + limit < len(values)
            return {"truncated": more, "revision": rev, "matched": len(values), "entries": values[offset:offset + limit], "next_offset": offset + limit if more else None}

    def apply(self, expected_revision: str, label: str, changes: list[dict]) -> dict:
        if not label.strip() or len(label) > 300 or not 1 <= len(changes) <= 100:
            raise ValueError("provide a label (1..300 chars) and 1..100 changes")
        with self.locked():
            before = self.revision()
            if expected_revision != before:
                raise ValueError(f"revision_conflict: current revision {before}")
            if self.git("status", "--porcelain"):
                raise ValueError("workspace_dirty: reconcile external edits before using MCP")
            # Keep a full pre-change snapshot for rollback; Git never resets user files.
            snapshot = {p: self.path(p).read_bytes() for p in self.files(before)}
            try:
                for change in changes:
                    self._change(change)
                self._check_records()
                self.git("add", "--", "factory", "processes")
                if not self.git("diff", "--cached", "--name-only"):
                    return {"revision": before, "changed": False}
                self.git("commit", "-m", label)
                return {"revision": self.revision(), "previous_revision": before, "changed": True}
            except Exception:
                for base in ("factory", "processes"):
                    for p in sorted(self.path(base).rglob("*"), key=lambda x: len(x.parts), reverse=True):
                        if p.is_file():
                            p.unlink()
                        elif p.is_dir():
                            p.rmdir()
                for name, data in snapshot.items():
                    p = self.path(name)
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(data)
                self.git("reset", "--mixed", before)
                raise

    def _change(self, change: dict):
        op = change.get("op")
        keys = {"mkdir": {"op", "path"}, "put": {"op", "path", "record"}, "move": {"op", "path", "destination"}, "delete": {"op", "path"}}
        if op not in keys or set(change) != keys[op]:
            raise ValueError("invalid change; use mkdir/put/move/delete with documented fields")
        p = self.path(change["path"])
        if len(PurePosixPath(change["path"]).parts) < 2 or p.name == ".keep":
            raise ValueError("cannot mutate workspace roots or internal markers")
        if op == "mkdir":
            p.mkdir(parents=True, exist_ok=False)
            (p / ".keep").touch()
        elif op == "put":
            if p.suffix != ".json":
                raise ValueError("records must use .json")
            schema = Resource if change["path"].startswith("factory/") else ProcessPlan
            normalized = schema.model_validate(change["record"]).model_dump()
            if p.is_file() and json.loads(p.read_text(encoding="utf-8"))["id"] != normalized["id"]:
                raise ValueError("stable_id: an existing record ID cannot be changed")
            data = json.dumps(normalized, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
            if len(data.encode("utf-8")) > MAX_FILE:
                raise ValueError("record exceeds 64 KB")
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(data, encoding="utf-8")
        elif op == "move":
            target = self.path(change["destination"])
            if target.parts[len(self.root.parts)] != p.parts[len(self.root.parts)]:
                raise ValueError("cannot move between factory and processes")
            if target.exists() or target.suffix != p.suffix or target.is_relative_to(p):
                raise ValueError("invalid move destination")
            target.parent.mkdir(parents=True, exist_ok=True)
            p.rename(target)
        else:
            if p.is_dir():
                if any(x.name != ".keep" for x in p.iterdir()):
                    raise ValueError("directory_not_empty: delete individual records first")
                (p / ".keep").unlink(missing_ok=True)
                p.rmdir()
            else:
                p.unlink()

    def _check_records(self):
        for base, schema in (("factory", Resource), ("processes", ProcessPlan)):
            ids = set()
            for p in self.path(base).rglob("*"):
                if not p.is_file() or p.name == ".keep":
                    continue
                self.path(p.relative_to(self.root).as_posix())
                if p.suffix != ".json" or p.stat().st_size > MAX_FILE:
                    raise ValueError("unsupported record file")
                record = schema.model_validate_json(p.read_bytes())
                if record.id in ids:
                    raise ValueError(f"duplicate_id: {record.id}")
                ids.add(record.id)
                if isinstance(record, ProcessPlan):
                    self.revision(record.passport_revision)
                    op_ids = [o.id for o in record.operations]
                    if len(op_ids) != len(set(op_ids)):
                        raise ValueError("duplicate operation IDs")

    def history(self, limit: int = 20) -> dict:
        if not 1 <= limit <= 100:
            raise ValueError("limit 1..100")
        with self.locked():
            self.revision()
            lines = self.git("log", f"-{limit}", "--format=%H%x09%aI%x09%s").splitlines()
            return {"commits": [dict(zip(("revision", "date", "label"), line.split("\t", 2))) for line in lines]}

    def impact(self, resource_id: str) -> dict:
        with self.locked():
            rev = self.revision()
            paths = []
            for path in self.files(rev):
                if path.startswith("processes/") and path.endswith(".json"):
                    plan = self.load(path, rev)
                    if any(resource_id in op["resource_ids"] for op in plan["operations"]):
                        paths.append({"path": path, "id": plan["id"], "passport_revision": plan["passport_revision"]})
            return {"revision": rev, "resource_id": resource_id, "processes": paths, "note": "Plans retain their pinned passport revision; current catalog changes do not rewrite them."}
