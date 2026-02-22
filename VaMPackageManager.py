import os, sys, curses
from typing import Optional

from scanner import VaMPackageManager
from ui import (
    A, addstr, init_colors,
    C_ACCENT, C_BORDER, C_DIM, C_DANGER, C_HEADER, C_TITLE, C_WARN,
)
from app import App


# ─────────────────────────────────────────────────────────────────────────────
#  STARTUP SCREENS
# ─────────────────────────────────────────────────────────────────────────────

def welcome_screen(stdscr) -> Optional[str]:
    curses.curs_set(1)
    h, w = stdscr.getmaxyx()
    stdscr.erase()

    banner = [
        "=== VaM Package Manager ===",
        "    Virt-a-Mate .var manager     ",
    ]
    sy = max(1, h // 2 - 5)
    for i, line in enumerate(banner):
        x = max(0, (w - len(line)) // 2)
        addstr(stdscr, sy + i, x, line, A(C_TITLE, bold=(i == 0)))

    prompt = "Enter path to your VaM installation folder:"
    addstr(stdscr, sy + 4, max(0, (w - len(prompt)) // 2), prompt, A(C_ACCENT, bold=True))

    iw = min(64, w - 6)
    ix = (w - iw) // 2
    iy = sy + 6
    addstr(stdscr, iy, ix, "[" + " " * iw + "]", A(C_BORDER, bold=True))
    addstr(stdscr, iy + 2, ix, "Enter = open     Ctrl+C = quit", A(C_DIM))

    stdscr.move(iy, ix + 1)
    stdscr.refresh()

    curses.echo()
    try:
        raw = stdscr.getstr(iy, ix + 1, iw - 1).decode("utf-8").strip()
    except (KeyboardInterrupt, Exception):
        raw = ""
    finally:
        curses.noecho()
        curses.curs_set(0)

    return raw or None


def loading_screen(stdscr, path: str):
    h, w = stdscr.getmaxyx()
    stdscr.erase()
    msg = f"  Opening {path} ..."
    addstr(stdscr, h // 2, max(0, (w - len(msg)) // 2), msg, A(C_ACCENT, bold=True))
    stdscr.refresh()


def make_progress_cb(stdscr, vam_dir: str):
    def cb(scanned: int, cached: int, total: int, filename: str):
        h, w = stdscr.getmaxyx()
        stdscr.erase()

        stdscr.attron(A(C_HEADER, bold=True))
        stdscr.hline(0, 0, " ", w)
        addstr(stdscr, 0, 2, "  VaM Package Manager  |  Loading...", A(C_HEADER, bold=True))
        stdscr.attroff(A(C_HEADER, bold=True))

        cy = h // 2 - 3

        path_msg = f"  {vam_dir}"
        addstr(stdscr, cy, max(0, (w - len(path_msg)) // 2), path_msg, A(C_DIM))

        fname = filename[:w - 6] if len(filename) > w - 6 else filename
        addstr(stdscr, cy + 2, max(0, (w - len(fname)) // 2), fname, A(C_ACCENT, bold=True))

        done = scanned + cached
        bar_w = min(60, w - 8)
        filled = int(bar_w * done / max(1, total))
        bar = "█" * filled + "░" * (bar_w - filled)
        bx = max(0, (w - bar_w - 2) // 2)
        addstr(stdscr, cy + 4, bx, f"[{bar}]", A(C_BORDER, bold=True))

        pct = int(100 * done / max(1, total))
        count_msg = f"{done} / {total}  ({cached} cached, {scanned} scanned)  {pct}%"
        addstr(stdscr, cy + 5, max(0, (w - len(count_msg)) // 2), count_msg, A(C_DIM))

        stdscr.refresh()

    return cb


# ─────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def curses_main(stdscr):
    vam_dir = sys.argv[1] if len(sys.argv) > 1 else None

    init_colors()
    curses.curs_set(0)
    stdscr.keypad(True)

    if not vam_dir:
        vam_dir = welcome_screen(stdscr)
        if not vam_dir:
            return

    vam_dir = os.path.expanduser(vam_dir.strip())
    loading_screen(stdscr, vam_dir)

    try:
        progress_cb = make_progress_cb(stdscr, vam_dir)
        mgr = VaMPackageManager(vam_dir, progress_cb=progress_cb)
    except FileNotFoundError as e:
        h, w = stdscr.getmaxyx()
        stdscr.erase()
        err = f"  Error: {e}  "
        addstr(stdscr, h // 2, max(0, (w - len(err)) // 2), err, A(C_DANGER, bold=True))
        addstr(stdscr, h // 2 + 2, max(0, (w - 18) // 2), "  Press any key  ", A(C_DIM))
        stdscr.refresh()
        stdscr.getch()
        return

    App(stdscr, mgr).run()


def main():
    try:
        curses.wrapper(curses_main)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
