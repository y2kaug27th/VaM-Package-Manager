import os, json, zipfile, re, sqlite3
from pathlib import Path
from collections import defaultdict
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
#  BACKEND
# ─────────────────────────────────────────────────────────────────────────────

PACKAGE_REF_PATTERN = re.compile(
    r'([A-Za-z0-9][A-Za-z0-9_\- ]*\.[A-Za-z0-9_\-]+\.(?:\d+|latest)):/',
    re.IGNORECASE,
)


def is_valid_package_ref(ref: str) -> bool:
    parts = ref.strip().split(".")
    if len(parts) < 3:
        return False
    author = parts[0].strip()
    pkg = ".".join(parts[1:-1])
    version = parts[-1]

    # Version must be digits or 'latest'
    if not (version.isdigit() or version.lower() == "latest"):
        return False

    # Author: reject single-char names
    if len(author) < 2:
        return False
    # Author: reject all-digit (e.g. "1", "19")
    if author.isdigit():
        return False
    # Author: reject version-like prefixes — 'v' or '-' followed by only digits/dots
    if author[0] in ("v", "-") and all(c.isdigit() or c == "." for c in author[1:]):
        return False
    # Author: reserved keywords that cannot be used as author
    if author in ("entries"):
        return False

    # Package: must be non-empty and start with a letter
    if not pkg or not pkg[0].isalpha():
        return False

    return True


def parse_package_name(filename: str) -> Optional[str]:
    name = Path(filename).stem
    parts = name.split(".")
    if len(parts) < 3:
        return None
    author = parts[0]
    pkg = ".".join(parts[1:-1])
    version = parts[-1]
    if not (version.isdigit() or version.lower() == "latest"):
        return None
    version_norm = "latest" if version.lower() == "latest" else version
    return f"{author}.{pkg}.{version_norm}"


def find_all_vars(vam_dir: str) -> dict:
    packages = {}
    duplicates = {}  # pid -> [Path, ...] of all paths seen
    for root, _, files in os.walk(vam_dir):
        for f in files:
            if f.lower().endswith(".var"):
                pid = parse_package_name(f)
                if not pid:
                    continue
                path = Path(root) / f
                if pid not in packages:
                    packages[pid] = path
                else:
                    # Track every collision
                    if pid not in duplicates:
                        duplicates[pid] = [packages[pid]]
                    duplicates[pid].append(path)
                    # Keep the largest file
                    if path.stat().st_size > packages[pid].stat().st_size:
                        packages[pid] = path

    if duplicates:
        import logging
        for pid, paths in duplicates.items():
            kept = packages[pid]
            others = [str(p) for p in paths if p != kept]
            logging.warning(
                "Duplicate package ID %r — keeping %s, ignoring: %s",
                pid, kept, ", ".join(others),
            )

    return packages


def resolve_ref(ref: str, packages: dict) -> str:
    parts = ref.split(".")
    if len(parts) < 3:
        return ref

    version = parts[-1]
    base = ".".join(parts[:-1])

    # --- fast path: exact match (or .latest that is already resolved) ---
    if ref in packages:
        return ref

    # --- collect all installed versions for this Author.PackName base ---
    candidates = []
    for pid in packages:
        pid_parts = pid.split(".")
        if len(pid_parts) < 3:
            continue
        pid_base = ".".join(pid_parts[:-1])
        pid_ver = pid_parts[-1]
        if pid_base == base and pid_ver.isdigit():
            candidates.append((int(pid_ver), pid))

    if not candidates:
        return ref  # nothing installed under this base at all

    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def resolve_latest(ref: str, packages: dict) -> str:
    return resolve_ref(ref, packages)


def latest_alias(pid: str) -> str:
    parts = pid.split(".")
    if len(parts) < 3 or not parts[-1].isdigit():
        return ""
    return ".".join(parts[:-1]) + ".latest"


def read_meta_json(var_path: Path) -> Optional[dict]:
    try:
        with zipfile.ZipFile(var_path, "r") as z:
            if "meta.json" in z.namelist():
                with z.open("meta.json") as f:
                    return json.load(f)
    except Exception:
        pass
    return None


def extract_refs_from_meta(var_path: Path) -> set:
    refs = set()
    self_id = parse_package_name(var_path.name)
    meta = read_meta_json(var_path)
    if not meta:
        return refs

    raw_deps = meta.get("dependencies", {})

    # Support both { "Pkg": "URL" } AND [ "Pkg1", "Pkg2" ]
    items = raw_deps.keys() if isinstance(raw_deps, dict) else raw_deps
    if not isinstance(items, (list, dict, set, type(dict().keys()))):
        return refs

    for key in items:
        if not isinstance(key, str):
            continue

        # Normalise .latest
        parts = key.split(".")
        if len(parts) >= 3 and parts[-1].lower() == "latest":
            key = ".".join(parts[:-1]) + ".latest"

        # Relaxed validation: If it's in meta.json, it's probably a real dep
        if key != self_id:
            refs.add(key)

    return refs


def extract_refs_from_var(var_path: Path) -> set:
    TEXT_EXTS = {
        ".scene", ".person", ".json",
        ".vap", ".vab", ".vac", ".vps", ".vmp", ".vms",
        ".skin", ".uip",
        ".cslist", ".cs",
    }

    refs = set()
    self_id = parse_package_name(var_path.name)
    try:
        with zipfile.ZipFile(var_path, "r") as z:
            for entry in z.namelist():
                ext = Path(entry).suffix.lower()
                if ext not in TEXT_EXTS:
                    continue
                try:
                    content = z.open(entry).read().decode("utf-8", errors="ignore")
                    for m in PACKAGE_REF_PATTERN.finditer(content):
                        r = m.group(1).strip()
                        # Normalise .Latest / .LATEST -> .latest
                        rparts = r.split(".")
                        if rparts[-1].lower() == "latest":
                            rparts[-1] = "latest"
                            r = ".".join(rparts)
                        if not is_valid_package_ref(r):
                            continue
                        if r != self_id:
                            refs.add(r)
                except Exception:
                    pass
    except Exception:
        pass
    return refs


# ─────────────────────────────────────────────────────────────────────────────
#  SQLITE CACHE
# ─────────────────────────────────────────────────────────────────────────────


class PackageCache:

    def __init__(self, vam_dir: Path):
        cache_dir = vam_dir / "Cache"
        cache_dir.mkdir(exist_ok=True)
        db_path = cache_dir / "vam_pkg_cache.db"
        try:
            self._con = sqlite3.connect(str(db_path))
            self._con.execute("PRAGMA journal_mode=WAL")
            self._con.execute(
                """
                CREATE TABLE IF NOT EXISTS package_refs (
                    filename  TEXT PRIMARY KEY,
                    mtime     REAL NOT NULL,
                    size      INTEGER NOT NULL,
                    refs      TEXT NOT NULL
                )
                """
            )
            self._con.commit()
            self._ok = True
        except Exception:
            self._con = None
            self._ok = False

    def lookup(self, path: Path) -> Optional[set]:
        """Return cached refs for path if mtime+size match, else None."""
        if not self._ok:
            return None
        try:
            st = path.stat()
            row = self._con.execute(
                "SELECT mtime, size, refs FROM package_refs WHERE filename = ?",
                (path.name,),
            ).fetchone()
            if row and abs(row[0] - st.st_mtime) < 0.001 and row[1] == st.st_size:
                return set(json.loads(row[2]))
        except Exception:
            pass
        return None

    def store(self, path: Path, refs: set):
        """Persist refs for path."""
        if not self._ok:
            return
        try:
            st = path.stat()
            self._con.execute(
                """
                INSERT OR REPLACE INTO package_refs (filename, mtime, size, refs)
                VALUES (?, ?, ?, ?)
                """,
                (path.name, st.st_mtime, st.st_size, json.dumps(sorted(refs))),
            )
            self._con.commit()
        except Exception:
            pass

    def prune(self, known_filenames: set):
        """Remove rows for packages that no longer exist on disk."""
        if not self._ok:
            return
        try:
            rows = self._con.execute("SELECT filename FROM package_refs").fetchall()
            stale = [r[0] for r in rows if r[0] not in known_filenames]
            if stale:
                self._con.executemany(
                    "DELETE FROM package_refs WHERE filename = ?",
                    [(f,) for f in stale],
                )
                self._con.commit()
        except Exception:
            pass

    def close(self):
        if self._con:
            try:
                self._con.close()
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
#  PACKAGE MANAGER
# ─────────────────────────────────────────────────────────────────────────────


class VaMPackageManager:
    def __init__(self, vam_dir: str, progress_cb=None):
        self.vam_dir = Path(vam_dir)
        self.packages: dict = find_all_vars(str(self.vam_dir))
        self._rdeps_cache: Optional[dict] = None

        cache = PackageCache(self.vam_dir)
        known_filenames = {p.name for p in self.packages.values()}
        cache.prune(known_filenames)

        total = len(self.packages)
        scanned = 0
        cached = 0

        self._deps_cache: dict = {}
        for pid, path in self.packages.items():
            refs = cache.lookup(path)
            if refs is not None:
                cached += 1
            else:
                meta_refs = extract_refs_from_meta(path)
                if meta_refs:
                    refs = meta_refs - {pid}
                else:
                    refs = extract_refs_from_var(path) - {pid}
                cache.store(path, refs)
                scanned += 1

            if progress_cb:
                progress_cb(scanned, cached, total, path.name)

            direct: set = set()
            for ref in refs:
                if ref != pid:
                    direct.add(resolve_ref(ref, self.packages))
            self._deps_cache[pid] = direct

        cache.close()

    # ── forward deps ──────────────────────────────────────────────────────────

    def get_dependencies(self, pid: str, recursive: bool = True) -> set:
        if pid not in self.packages:
            return set()

        if not recursive:
            return set(self._deps_cache.get(pid, set()))

        visited: set = set()
        queue = list(self._deps_cache.get(pid, set()))
        while queue:
            dep = queue.pop()
            if dep in visited:
                continue
            visited.add(dep)
            for s in self._deps_cache.get(dep, set()):
                if s not in visited:
                    queue.append(s)
        return visited

    # ── reverse deps ──────────────────────────────────────────────────────────

    def _build_reverse_deps(self) -> dict:
        if self._rdeps_cache is not None:
            return self._rdeps_cache
        rdeps: dict = defaultdict(set)
        for pid in self.packages:
            for dep in self.get_dependencies(pid, recursive=False):
                rdeps[dep].add(pid)
        self._rdeps_cache = dict(rdeps)
        return self._rdeps_cache

    def get_dependents(self, pid: str) -> set:
        rdeps = self._build_reverse_deps()
        alias = latest_alias(pid)
        seed = set(rdeps.get(pid, [])) | set(rdeps.get(alias, []) if alias else [])
        visited: set = set()
        queue = list(seed)
        while queue:
            p = queue.pop()
            if p in visited:
                continue
            visited.add(p)
            for x in rdeps.get(p, []):
                if x not in visited:
                    queue.append(x)
        return visited

    # ── queries ───────────────────────────────────────────────────────────────

    def get_dep_tree(self, pid: str, max_depth: int = 6) -> list:
        all_deps = self.get_dependencies(pid, recursive=True)
        best_version: dict = {}  # base -> best (installed version int or -1 for latest)
        for dep in all_deps:
            parts = dep.split(".")
            if len(parts) < 3:
                continue
            base = ".".join(parts[:-1])
            ver = parts[-1]
            if ver == "latest":
                # .latest always wins — it resolves to the highest installed
                best_version[base] = float("inf")
            elif ver.isdigit():
                v = int(ver)
                if base not in best_version or (
                    best_version[base] != float("inf") and v > best_version[base]
                ):
                    best_version[base] = v

        def is_superseded(dep: str) -> bool:
            parts = dep.split(".")
            if len(parts) < 3:
                return False
            base = ".".join(parts[:-1])
            ver = parts[-1]
            if ver == "latest":
                return False  # latest is never superseded
            if not ver.isdigit():
                return False
            best = best_version.get(base)
            if best is None:
                return False
            return int(ver) < best

        result = []
        def walk(node, depth, visited):
            if depth > max_depth:
                return
            for dep in sorted(self._deps_cache.get(node, set())):
                if is_superseded(dep):
                    continue
                result.append((dep, depth, node))
                if dep not in visited:
                    walk(dep, depth + 1, visited | {dep})
        walk(pid, 1, {pid})
        return result

    def package_info(self, pid: str) -> dict:
        if pid not in self.packages:
            return {}
        path = self.packages[pid]
        size_mb = path.stat().st_size / (1024 * 1024)
        meta = read_meta_json(path)
        direct = self.get_dependencies(pid, recursive=False)
        all_deps = self.get_dependencies(pid, recursive=True)
        dependents = self.get_dependents(pid)
        return {
            "id": pid,
            "path": str(path),
            "size_mb": size_mb,
            "creator": (meta or {}).get("creatorName", "N/A"),
            "license": (meta or {}).get("licenseType", "N/A"),
            "description": (meta or {}).get("description", "").strip(),
            "direct_deps": sorted(direct),
            "all_deps": sorted(all_deps),
            "dependents": sorted(dependents),
            "missing_deps": sorted(d for d in all_deps if d not in self.packages),
        }

    def find_missing(self) -> list:
        missing: dict = {}  # missing_pid -> set of installed packages that need it
        for pid, deps in self._deps_cache.items():
            for dep in deps:
                if dep not in self.packages:
                    missing.setdefault(dep, set()).add(pid)
        result = [
            (mid, sorted(dependents))
            for mid, dependents in missing.items()
        ]
        result.sort(key=lambda x: len(x[1]), reverse=True)
        return result

    def find_orphans(self) -> list:
        orphans = []
        for pid in self.packages:
            parts = pid.split(".")
            base = ".".join(parts[:-1])       # e.g. "AshAuryn.Sexpressions"
            version = parts[-1]               # e.g. "6"

            used = False
            for other_pid, deps in self._deps_cache.items():
                if other_pid == pid:
                    continue
                for dep in deps:
                    dep_parts = dep.split(".")
                    dep_base = ".".join(dep_parts[:-1])
                    dep_ver = dep_parts[-1]
                    if dep_base != base:
                        continue
                    # exact match
                    if dep_ver == version:
                        used = True
                        break
                    # .latest match — this dep could resolve to our pid
                    if dep_ver == "latest" and version.isdigit():
                        # only counts if our version is the highest installed
                        highest = resolve_ref(dep, self.packages)
                        if highest == pid:
                            used = True
                            break
                if used:
                    break

            if not used:
                size_mb = self.packages[pid].stat().st_size / (1024 * 1024)
                orphans.append((pid, size_mb))

        orphans.sort(key=lambda x: x[1], reverse=True)
        return orphans

    # ── deletion ──────────────────────────────────────────────────────────────

    def plan_delete(self, pid: str, with_deps: bool = False) -> dict:
        if pid not in self.packages:
            return {}
        dependents = self.get_dependents(pid)
        to_delete = [pid]
        keep_deps = []
        delete_deps_list = []
        if with_deps:
            for dep in self.get_dependencies(pid, recursive=True):
                if dep not in self.packages:
                    continue
                others = self.get_dependents(dep) - {pid}
                if others:
                    keep_deps.append((dep, sorted(others)))
                else:
                    delete_deps_list.append(dep)
                    to_delete.append(dep)
        total_mb = sum(
            self.packages[p].stat().st_size / (1024 * 1024)
            for p in to_delete
            if p in self.packages
        )
        return {
            "target": pid,
            "dependents": sorted(dependents),
            "to_delete": sorted(to_delete),
            "keep_deps": keep_deps,
            "delete_deps": sorted(delete_deps_list),
            "total_mb": total_mb,
        }

    def execute_delete(self, plan: dict) -> list:
        results = []
        for pid in plan["to_delete"]:
            path = self.packages.get(pid)
            if path and path.exists():
                try:
                    path.unlink()
                    del self.packages[pid]
                    self._deps_cache.pop(pid, None)
                    self._rdeps_cache = None
                    results.append((pid, True, "Deleted"))
                except Exception as e:
                    results.append((pid, False, str(e)))
            else:
                results.append((pid, False, "File not found"))
        return results
