import curses, textwrap
from typing import Optional

from scanner import VaMPackageManager


# ─────────────────────────────────────────────────────────────────────────────
#  COLORS
# ─────────────────────────────────────────────────────────────────────────────

C_NORMAL = 0
C_HEADER = 1
C_SEL    = 2
C_ACCENT = 3
C_DANGER = 4
C_OK     = 5
C_DIM    = 6
C_TITLE  = 7
C_BORDER = 8
C_WARN   = 9


def init_colors():
    curses.start_color()
    curses.use_default_colors()
    bg = -1
    curses.init_pair(C_HEADER, curses.COLOR_BLACK, curses.COLOR_CYAN)
    curses.init_pair(C_SEL,    curses.COLOR_BLACK, curses.COLOR_WHITE)
    curses.init_pair(C_ACCENT, curses.COLOR_CYAN,   bg)
    curses.init_pair(C_DANGER, curses.COLOR_RED,    bg)
    curses.init_pair(C_OK,     curses.COLOR_GREEN,  bg)
    curses.init_pair(C_DIM,    curses.COLOR_WHITE,  bg)
    curses.init_pair(C_TITLE,  curses.COLOR_CYAN,   bg)
    curses.init_pair(C_BORDER, curses.COLOR_CYAN,   bg)
    curses.init_pair(C_WARN,   curses.COLOR_YELLOW, bg)


# ─────────────────────────────────────────────────────────────────────────────
#  DRAWING HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def A(pair, bold=False):
    a = curses.color_pair(pair)
    if bold:
        a |= curses.A_BOLD
    return a


def addstr(win, y, x, text, attr=0):
    h, w = win.getmaxyx()
    if y < 0 or y >= h or x < 0 or x >= w:
        return
    avail = w - x
    if avail <= 0:
        return
    try:
        win.addstr(y, x, text[:avail], attr)
    except curses.error:
        pass


def draw_box(win, y, x, h, w, title="", color=C_BORDER):
    a = A(color, bold=True)
    try:
        win.attron(a)
        win.addch(y, x, curses.ACS_ULCORNER)
        win.addch(y, x + w - 1, curses.ACS_URCORNER)
        win.addch(y + h - 1, x, curses.ACS_LLCORNER)
        win.addch(y + h - 1, x + w - 1, curses.ACS_LRCORNER)
        for i in range(1, w - 1):
            win.addch(y, x + i, curses.ACS_HLINE)
            win.addch(y + h - 1, x + i, curses.ACS_HLINE)
        for i in range(1, h - 1):
            win.addch(y + i, x, curses.ACS_VLINE)
            win.addch(y + i, x + w - 1, curses.ACS_VLINE)
        win.attroff(a)
    except curses.error:
        pass
    if title:
        label = f" {title} "
        tx = x + max(1, (w - len(label)) // 2)
        addstr(win, y, tx, label, A(C_TITLE, bold=True))


def draw_header(win, subtitle=""):
    h, w = win.getmaxyx()
    win.attron(A(C_HEADER, bold=True))
    win.hline(0, 0, " ", w)
    text = "  VaM Package Manager"
    if subtitle:
        text += f"  |  {subtitle}"
    addstr(win, 0, 1, text[: w - 2], A(C_HEADER, bold=True))
    win.attroff(A(C_HEADER, bold=True))


def draw_footer(win, keys: list, status=""):
    h, w = win.getmaxyx()
    win.attron(A(C_HEADER))
    win.hline(h - 1, 0, " ", w)
    x = 1
    for k, desc in keys:
        label = f" {k} "
        if x + len(label) + len(desc) + 3 >= w:
            break
        try:
            win.addstr(h - 1, x, label, A(C_SEL, bold=True))
        except curses.error:
            pass
        x += len(label)
        try:
            win.addstr(h - 1, x, f" {desc}  ", A(C_HEADER))
        except curses.error:
            pass
        x += len(desc) + 3
    if status:
        msg = f" {status} "
        sx = max(x, w - len(msg) - 1)
        addstr(win, h - 1, sx, msg[: w - sx], A(C_SEL, bold=True))
    win.attroff(A(C_HEADER))


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


# ─────────────────────────────────────────────────────────────────────────────
#  POPUPS
# ─────────────────────────────────────────────────────────────────────────────

def popup(stdscr, title: str, lines: list, color=C_ACCENT):
    h, w = stdscr.getmaxyx()
    dw = min(max((len(l) for l in lines), default=20) + 8, w - 4)
    dw = max(dw, 42)
    dh = min(len(lines) + 5, h - 2)
    dy = (h - dh) // 2
    dx = (w - dw) // 2
    win = curses.newwin(dh, dw, dy, dx)
    win.bkgd(" ")
    draw_box(win, 0, 0, dh, dw, title, color=color)
    for i, line in enumerate(lines[: dh - 4]):
        addstr(win, i + 2, 3, line[: dw - 6], A(C_DIM))
    addstr(win, dh - 2, 3, "[ Press any key ]", A(color, bold=True))
    win.refresh()
    win.getch()


def confirm_popup(stdscr, title: str, lines: list, danger=False) -> bool:
    h, w = stdscr.getmaxyx()
    dw = min(max((len(l) for l in lines), default=20) + 8, w - 4)
    dw = max(dw, 48)
    dh = min(len(lines) + 6, h - 2)
    dy = (h - dh) // 2
    dx = (w - dw) // 2
    win = curses.newwin(dh, dw, dy, dx)
    win.bkgd(" ")
    col = C_DANGER if danger else C_ACCENT
    draw_box(win, 0, 0, dh, dw, title, color=col)
    for i, line in enumerate(lines[: dh - 5]):
        c = C_DANGER if (i == 0 and danger) else C_DIM
        b = i == 0
        addstr(win, i + 2, 3, line[: dw - 6], A(c, bold=b))
    addstr(win, dh - 2, 3, "[ Y ] Confirm    [ N ] Cancel", A(C_WARN, bold=True))
    win.refresh()
    while True:
        k = win.getch()
        if k in (ord("y"), ord("Y")):
            return True
        if k in (ord("n"), ord("N"), 27, ord("q")):
            return False


# ─────────────────────────────────────────────────────────────────────────────
#  LIST PANEL
# ─────────────────────────────────────────────────────────────────────────────

class ListPanel:
    def __init__(self, items, y, x, h, w, title=""):
        self.all_items = list(items)
        self.items = list(items)
        self.cursor = 0
        self.scroll = 0
        self.y, self.x, self.h, self.w = y, x, h, w
        self.title = title
        self.filter_str = ""
        self.focused = True
        self._ih = h - 4  # inner rows (box top + bottom + filter bar)

    def apply_filter(self, s: str):
        self.filter_str = s.lower()
        self.items = [i for i in self.all_items if self.filter_str in i.lower()]
        self.cursor = 0
        self.scroll = 0

    def reload(self, items):
        self.all_items = list(items)
        self.apply_filter(self.filter_str)

    def move(self, delta: int):
        n = len(self.items)
        if n == 0:
            return
        self.cursor = clamp(self.cursor + delta, 0, n - 1)
        if self.cursor < self.scroll:
            self.scroll = self.cursor
        elif self.cursor >= self.scroll + self._ih:
            self.scroll = self.cursor - self._ih + 1

    def selected(self) -> Optional[str]:
        return self.items[self.cursor] if self.items else None

    def draw(self, win, filter_typing=False, filter_buf=""):
        bc = C_ACCENT if self.focused else C_BORDER
        t = f"{self.title} ({len(self.items)}/{len(self.all_items)})"
        draw_box(win, self.y, self.x, self.h, self.w, t, color=bc)

        fy = self.y + self.h - 2
        if filter_typing:
            fb = f" /{filter_buf}_"
        elif self.filter_str:
            fb = f" /{self.filter_str}"
        else:
            fb = " (/ to filter)"
        addstr(win, fy, self.x + 2, fb[: self.w - 4], A(C_WARN if filter_typing else C_DIM))

        for i in range(self._ih):
            idx = self.scroll + i
            row = self.y + 2 + i
            if idx >= len(self.items):
                addstr(win, row, self.x + 1, " " * (self.w - 2))
                continue
            item = self.items[idx]
            is_sel = idx == self.cursor
            prefix = " > " if is_sel else "   "
            text = prefix + item
            at = (
                A(C_SEL, bold=True) if (is_sel and self.focused)
                else A(C_DIM, bold=True) if is_sel
                else A(C_DIM)
            )
            addstr(win, row, self.x + 1, " " * (self.w - 2))
            addstr(win, row, self.x + 1, text[: self.w - 2], at)

        n = len(self.items)
        if n > self._ih:
            pct = int((self.scroll / max(1, n - self._ih)) * (self._ih - 1))
            addstr(win, self.y + 2 + pct, self.x + self.w - 1, "#", A(C_ACCENT))


# ─────────────────────────────────────────────────────────────────────────────
#  DETAIL PANEL
# ─────────────────────────────────────────────────────────────────────────────

class DetailPanel:
    def __init__(self, y, x, h, w):
        self.y, self.x, self.h, self.w = y, x, h, w
        self.lines: list = []  # list of (text, color_id, bold)
        self.scroll = 0
        self._ih = h - 2

    def set_content(self, lines):
        self.lines = lines
        self.scroll = 0

    def scroll_by(self, d):
        self.scroll = clamp(self.scroll + d, 0, max(0, len(self.lines) - self._ih))

    def draw(self, win):
        draw_box(win, self.y, self.x, self.h, self.w, "Details")
        for i, (text, col, bold) in enumerate(
            self.lines[self.scroll : self.scroll + self._ih]
        ):
            addstr(win, self.y + 1 + i, self.x + 2, text[: self.w - 4], A(col, bold=bold))
        n = len(self.lines)
        if n > self._ih:
            pct = int((self.scroll / max(1, n - self._ih)) * (self._ih - 1))
            addstr(win, self.y + 1 + pct, self.x + self.w - 1, "#", A(C_ACCENT))


# ─────────────────────────────────────────────────────────────────────────────
#  DETAIL CONTENT BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_detail(mgr: VaMPackageManager, pid: str) -> list:
    info = mgr.package_info(pid)
    if not info:
        return [("Package not found.", C_DANGER, True)]

    lines = []

    def row(t, c=C_DIM, b=False):
        lines.append((t, c, b))

    def sep():
        lines.append(("-" * 48, C_BORDER, False))

    def blank():
        lines.append(("", C_DIM, False))

    row(f"  {info['id']}", C_ACCENT, True)
    sep()
    row(f"  Creator  : {info['creator']}")
    row(f"  License  : {info['license']}")
    row(f"  Size     : {info['size_mb']:.2f} MB")
    row(f"  Path     : {info['path']}")
    if info["description"]:
        blank()
        for chunk in textwrap.wrap(info["description"], 44):
            row(f"  {chunk}")
    blank()
    sep()

    owned: set = set(info["all_deps"]) | {pid}

    # ── Direct dependencies ───────────────────────────────────────────────
    row(f"  Direct dependencies ({len(info['direct_deps'])}):", C_ACCENT, True)
    if info["direct_deps"]:
        for d in info["direct_deps"]:
            present = d in mgr.packages
            if not present:
                status = "[MISSING]"
                col = C_DANGER
            else:
                users = mgr.get_dependents(d)
                others = users - owned
                n = len(others)
                if n == 0:
                    status = "[ok | only you]"
                    col = C_OK
                else:
                    status = f"[ok | +{n} others]"
                    col = C_WARN
            row(f"    {status} {d}", col)
    else:
        row("    (none)")
    blank()
    sep()

    # ── All transitive dependencies (tree view) ──────────────────────────
    row(f"  All transitive dependencies ({len(info['all_deps'])}):", C_ACCENT, True)
    tree = mgr.get_dep_tree(pid)
    if tree:
        prev_via = {}  # dep -> via, to detect repeated via lines
        last_depth = 0
        for dep, depth, via in tree:
            present = dep in mgr.packages
            if not present:
                tag = "[MISSING]"
                col = C_DANGER
            else:
                others = mgr.get_dependents(dep) - owned
                n = len(others)
                tag = "[ok | only you]" if n == 0 else f"[ok | +{n} others]"
                col = C_OK if n == 0 else C_WARN
            if depth == 1:
                row(f"    {tag} {dep}", col)
            else:
                indent = "  " * depth
                # tree branch characters
                prefix = indent + "└─ "
                row(f"  {prefix}{tag} {dep}", col)
    else:
        row("    (none)")
    blank()
    sep()

    # ── Used by ───────────────────────────────────────────────────────────
    row(f"  Used by ({len(info['dependents'])}):", C_ACCENT, True)
    if info["dependents"]:
        for d in info["dependents"]:
            row(f"    ^ {d}", C_WARN)
    else:
        row("    (none)  --  safe to delete", C_OK, True)

    return lines
