# VaM Package Manager

![Imgur Image](https://i.imgur.com/bP3fHX2.png)

An interactive terminal UI for managing Virt-A-Mate `.var` packages — browse your library, inspect dependencies, find unused packages, and safely delete them.

![Python](https://img.shields.io/badge/python-3.8+-blue) ![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)

---

## Features

- **Browse** and filter your package library
- **Inspect** dependencies for any package
- **Safely delete** packages and their exclusive dependencies
- **Orphan finder** — Identify packages not used by anything else
- **Missing Packages** — Identify missing packages needed by others
- **SQLite cache** — Only re-scans packages that have changed, keeping startup fast on large libraries

---

## Usage

```bash
python VaMPackageManager.py                     # Prompts for your VaM directory on launch
python VaMPackageManager.py /path/to/VaM        # Or pass the path directly
```

---

## Controls

| Key | Action |
|-----|--------|
| `↑ / ↓` | Navigate |
| `/` | Filter |
| `j / k` | Scroll detail panel |
| `I` | Package info |
| `D` | Delete package + dependencies |
| `O` | Orphan finder |
| `M` | Missing Packages |
| `Q` | Quit |

---

## Direct & Transitive Dependencies

- **Direct dependencies** — packages this `.var` explicitly requires to work.
- **Transitive dependencies** — packages pulled in indirectly through direct dependencies.
