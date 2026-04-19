# VarLens

![Imgur Image](https://i.imgur.com/RkxYOk7.png)

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

## Installation

### From PyPI (Recommended)
If you have [pipx](https://github.com/pypa/pipx) installed:
```bash
pipx install varlens-tui
```

or just using pip:
```bash
pip install varlens-tui
```

### From Source (Run without installing)
```bash
git clone https://github.com/y2kaug27th/VarLens.git
cd VarLens
python -m varlens
```

> [!IMPORTANT]
> **Windows Users**: If running from source, you must manually install the curses library:
> ```bash
> pip install windows-curses
> ```

---

## Usage

If installed via **PyPI**:
```bash
varlens                     # Launches the app
varlens /path/to/VaM        # Launches with a specific path
```

If running from **Source**:
```bash
python -m varlens           # Launches the app from the project root
python -m varlens /path/to/VaM
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

## Detail Panel

- **Creator, license, size, and file path**
- **Direct dependencies** — packages this `.var` explicitly requires to work, each tagged with a status:
  - `[ok | only you]` — safe to remove alongside this package
  - `[ok | +N others]` — shared with N other packages, will be kept
  - `[MISSING]` — referenced but not installed
- **All transitive dependencies** — packages pulled in indirectly through direct dependencies
- **Used by** — which packages depend on this one, none means it's safe to delete
