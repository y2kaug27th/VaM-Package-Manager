import curses
from typing import Optional

from scanner import VaMPackageManager
from ui import (
    A, addstr, build_detail, clamp, confirm_popup, C_ACCENT, C_BORDER,
    C_DANGER, C_DIM, C_OK, C_SEL, C_WARN, DetailPanel, draw_box, draw_footer,
    draw_header, ListPanel, popup,
)


class App:
    def __init__(self, stdscr, mgr: VaMPackageManager):
        self.stdscr = stdscr
        self.mgr = mgr
        self.running = True
        self.status = ""
        self.filter_typing = False
        self.filter_buf = ""

        stdscr.timeout(100)
        self._build()

    def _build(self):
        h, w = self.stdscr.getmaxyx()
        lw = max(30, w // 3)
        dw = w - lw - 1
        self.lp = ListPanel(
            sorted(self.mgr.packages.keys()), y=1, x=0, h=h - 2, w=lw, title="Packages"
        )
        self.dp = DetailPanel(y=1, x=lw + 1, h=h - 2, w=dw)
        self._refresh_detail()

    def _refresh_detail(self):
        pid = self.lp.selected()
        if pid:
            self.dp.set_content(build_detail(self.mgr, pid))
        else:
            self.dp.set_content([("No packages found.", C_DIM, False)])

    # ── Draw ──────────────────────────────────────────────────────────────────

    def draw(self):
        h, w = self.stdscr.getmaxyx()
        self.stdscr.erase()

        lw = self.lp.w
        draw_header(self.stdscr, str(self.mgr.vam_dir))

        for r in range(1, h - 1):
            addstr(self.stdscr, r, lw, "|", A(C_BORDER))

        self.lp.draw(self.stdscr, self.filter_typing, self.filter_buf)
        self.dp.draw(self.stdscr)

        if self.filter_typing:
            fkeys = [
                ("/", f"Filter: {self.filter_buf}"),
                ("Enter", "Apply"),
                ("ESC", "Clear"),
            ]
        else:
            fkeys = [
                ("^v", "Nav"),
                ("/", "Filter"),
                ("jk", "Detail"),
                ("I", "Info"),
                ("D", "Del+Deps"),
                ("O", "Orphans"),
                ("M", "Missing"),
                ("Q", "Quit"),
            ]
        draw_footer(self.stdscr, fkeys, status=self.status)
        self.stdscr.noutrefresh()
        curses.doupdate()

    # ── Event loop ────────────────────────────────────────────────────────────

    def run(self):
        while self.running:
            self.draw()
            key = self.stdscr.getch()
            if key == -1:
                continue
            if self.filter_typing:
                self._filter_key(key)
            else:
                self._key(key)

    def _filter_key(self, key):
        if key in (curses.KEY_ENTER, 10, 13):
            self.filter_typing = False
            self.lp.apply_filter(self.filter_buf)
            self._refresh_detail()
        elif key == 27:
            self.filter_typing = False
            self.filter_buf = ""
            self.lp.apply_filter("")
            self._refresh_detail()
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            self.filter_buf = self.filter_buf[:-1]
            self.lp.apply_filter(self.filter_buf)
            self._refresh_detail()
        elif 32 <= key < 127:
            self.filter_buf += chr(key)
            self.lp.apply_filter(self.filter_buf)
            self._refresh_detail()

    def _key(self, key):
        if key in (ord("q"), ord("Q")):
            self.running = False
        elif key == curses.KEY_UP:
            self.lp.move(-1)
            self._refresh_detail()
        elif key == curses.KEY_DOWN:
            self.lp.move(1)
            self._refresh_detail()
        elif key == curses.KEY_PPAGE:
            self.lp.move(-10)
            self._refresh_detail()
        elif key == curses.KEY_NPAGE:
            self.lp.move(10)
            self._refresh_detail()
        elif key == curses.KEY_HOME:
            self.lp.cursor = 0
            self.lp.scroll = 0
            self._refresh_detail()
        elif key == curses.KEY_END:
            self.lp.cursor = max(0, len(self.lp.items) - 1)
            self._refresh_detail()
        elif key == ord("j"):
            self.dp.scroll_by(1)
        elif key == ord("k"):
            self.dp.scroll_by(-1)
        elif key == ord("/"):
            self.filter_typing = True
            self.filter_buf = ""
        elif key in (curses.KEY_ENTER, 10, 13, ord("i"), ord("I")):
            pid = self.lp.selected()
            if pid:
                self._show_info(pid)
        elif key in (ord("d"), ord("D")):
            pid = self.lp.selected()
            if pid:
                self._delete_flow(pid, with_deps=True)
        elif key in (ord("o"), ord("O")):
            self._show_orphans()
        elif key in (ord("m"), ord("M")):
            self._show_missing()
        elif key == curses.KEY_RESIZE:
            self._build()

    # ── Info popup ────────────────────────────────────────────────────────────

    def _show_info(self, pid: str):
        info = self.mgr.package_info(pid)
        if not info:
            return
        lines = [
            f"Package  : {pid}",
            f"Creator  : {info['creator']}",
            f"License  : {info['license']}",
            f"Size     : {info['size_mb']:.2f} MB",
            "",
            f"Direct deps      : {len(info['direct_deps'])}",
            f"Transitive deps  : {len(info['all_deps'])}",
            f"Missing deps     : {len(info['missing_deps'])}",
            f"Used by          : {len(info['dependents'])} package(s)",
        ]
        if info["dependents"]:
            lines.append("")
            for d in info["dependents"][:6]:
                lines.append(f"  ^ {d}")
            if len(info["dependents"]) > 6:
                lines.append(f"  ... and {len(info['dependents']) - 6} more")
        popup(self.stdscr, f"Info: {pid}", lines, C_ACCENT)

    # ── Orphan finder ─────────────────────────────────────────────────────────

    def _show_orphans(self):
        orphans = self.mgr.find_orphans()
        if not orphans:
            popup(
                self.stdscr,
                "Orphan Finder",
                ["No orphans found.", "", "Every package is used by at least one other."],
                C_OK,
            )
            return

        total_mb = sum(mb for _, mb in orphans)
        scroll = 0
        cursor = 0

        h, w = self.stdscr.getmaxyx()
        lw = max(30, w // 3)
        dw = w - lw - 1
        panel_h = h - 2

        dp = DetailPanel(y=1, x=lw + 1, h=panel_h, w=dw)

        def refresh_detail():
            pid, mb = orphans[cursor]
            dp.set_content(build_detail(self.mgr, pid))

        refresh_detail()

        while True:
            h, w = self.stdscr.getmaxyx()
            lw = max(30, w // 3)
            dw = w - lw - 1
            panel_h = h - 2
            dp.y, dp.x, dp.h, dp.w = 1, lw + 1, panel_h, dw
            dp._ih = panel_h - 2
            list_inner = panel_h - 4

            self.stdscr.erase()
            draw_header(
                self.stdscr,
                f"Orphan Finder — {len(orphans)} unused  —  {total_mb:.1f} MB total",
            )

            for r in range(1, h - 1):
                addstr(self.stdscr, r, lw, "|", A(C_BORDER))

            t = f"Orphans ({len(orphans)})"
            draw_box(self.stdscr, 1, 0, panel_h, lw, t, color=C_ACCENT)

            for i in range(list_inner):
                idx = scroll + i
                row = 3 + i
                if idx >= len(orphans):
                    addstr(self.stdscr, row, 1, " " * (lw - 2))
                    continue
                pid, mb = orphans[idx]
                is_sel = idx == cursor
                prefix = " > " if is_sel else "   "
                line = f"{prefix}{mb:6.1f} MB  {pid}"
                at = A(C_SEL, bold=True) if is_sel else A(C_DIM)
                addstr(self.stdscr, row, 1, " " * (lw - 2))
                addstr(self.stdscr, row, 1, line[: lw - 2], at)

            addstr(self.stdscr, 1 + panel_h - 2, 2,
                   f" Total: {total_mb:.1f} MB "[: lw - 4], A(C_DIM))

            if len(orphans) > list_inner:
                pct = int((scroll / max(1, len(orphans) - list_inner)) * (list_inner - 1))
                addstr(self.stdscr, 3 + pct, lw - 1, "#", A(C_ACCENT))

            dp.draw(self.stdscr)

            draw_footer(
                self.stdscr,
                [
                    ("^v", "Navigate"),
                    ("jk", "Detail"),
                    ("I", "Info"),
                    ("D", "Del+Deps"),
                    ("Q", "Close"),
                ],
                status=self.status,
            )
            self.stdscr.noutrefresh()
            curses.doupdate()

            key = self.stdscr.getch()
            if key == -1:
                continue
            elif key == curses.KEY_UP:
                cursor = max(0, cursor - 1)
                if cursor < scroll:
                    scroll = cursor
                refresh_detail()
            elif key == curses.KEY_DOWN:
                cursor = min(len(orphans) - 1, cursor + 1)
                if cursor >= scroll + list_inner:
                    scroll = cursor - list_inner + 1
                refresh_detail()
            elif key == curses.KEY_PPAGE:
                cursor = max(0, cursor - 10)
                scroll = max(0, scroll - 10)
                refresh_detail()
            elif key == curses.KEY_NPAGE:
                cursor = min(len(orphans) - 1, cursor + 10)
                scroll = min(max(0, len(orphans) - list_inner), scroll + 10)
                refresh_detail()
            elif key == ord("j"):
                dp.scroll_by(1)
            elif key == ord("k"):
                dp.scroll_by(-1)
            elif key in (curses.KEY_ENTER, 10, 13, ord("i"), ord("I")):
                pid, mb = orphans[cursor]
                self._show_info(pid)
            elif key in (ord("d"), ord("D")):
                pid, mb = orphans[cursor]
                if pid:
                    self._delete_flow(pid, with_deps=True)
                    orphans = self.mgr.find_orphans()
                    total_mb = sum(mb for _, mb in orphans)
                    cursor = min(cursor, max(0, len(orphans) - 1))
                    scroll = min(scroll, max(0, len(orphans) - list_inner))
                    if not orphans:
                        popup(self.stdscr, "Done", ["All orphans deleted!"], C_OK)
                        break
                    refresh_detail()
            elif key == curses.KEY_RESIZE:
                pass
            elif key in (ord("q"), ord("Q")):
                break

        self._build()

    # ── Missing packages ─────────────────────────────────────────────────────

    def _show_missing(self):
        missing = self.mgr.find_missing()
        if not missing:
            popup(
                self.stdscr,
                "Missing Packages",
                ["No missing packages found.", "", "All dependencies are satisfied."],
                C_OK,
            )
            return

        cursor = 0
        scroll = 0

        h, w = self.stdscr.getmaxyx()
        lw = max(30, w // 3)
        dw = w - lw - 1
        panel_h = h - 2

        dp = DetailPanel(y=1, x=lw + 1, h=panel_h, w=dw)

        def build_missing_detail(mid: str, dependents: list) -> list:
            lines = []
            def row(t, c=C_DIM, b=False):
                lines.append((t, c, b))
            def sep():
                lines.append(("-" * 48, C_BORDER, False))
            def blank():
                lines.append(("", C_DIM, False))

            row(f"  {mid}", C_DANGER, True)
            row("  [NOT INSTALLED]", C_DANGER, False)
            sep()
            blank()
            row(f"  Needed by {len(dependents)} installed package(s):", C_ACCENT, True)
            blank()
            for dep in dependents:
                row(f"    ^ {dep}", C_WARN)
            return lines

        def refresh_detail():
            mid, dependents = missing[cursor]
            dp.set_content(build_missing_detail(mid, dependents))

        refresh_detail()

        while True:
            h, w = self.stdscr.getmaxyx()
            lw = max(30, w // 3)
            dw = w - lw - 1
            panel_h = h - 2
            dp.y, dp.x, dp.h, dp.w = 1, lw + 1, panel_h, dw
            dp._ih = panel_h - 2
            list_inner = panel_h - 4

            self.stdscr.erase()
            draw_header(
                self.stdscr,
                f"Missing Packages — {len(missing)} absent",
            )

            for r in range(1, h - 1):
                addstr(self.stdscr, r, lw, "|", A(C_BORDER))

            draw_box(self.stdscr, 1, 0, panel_h, lw,
                     f"Missing ({len(missing)})", color=C_DANGER)

            for i in range(list_inner):
                idx = scroll + i
                row = 3 + i
                if idx >= len(missing):
                    addstr(self.stdscr, row, 1, " " * (lw - 2))
                    continue
                mid, dependents = missing[idx]
                is_sel = idx == cursor
                prefix = " > " if is_sel else "   "
                count_tag = f"[{len(dependents):2d}] "
                line = prefix + count_tag + mid
                at = A(C_SEL, bold=True) if is_sel else A(C_DANGER)
                addstr(self.stdscr, row, 1, " " * (lw - 2))
                addstr(self.stdscr, row, 1, line[: lw - 2], at)

            if len(missing) > list_inner:
                pct = int((scroll / max(1, len(missing) - list_inner)) * (list_inner - 1))
                addstr(self.stdscr, 3 + pct, lw - 1, "#", A(C_ACCENT))

            dp.draw(self.stdscr)

            draw_footer(
                self.stdscr,
                [
                    ("^v", "Navigate"),
                    ("jk", "Scroll detail"),
                    ("Q", "Close"),
                ],
                status=self.status,
            )
            self.stdscr.noutrefresh()
            curses.doupdate()

            key = self.stdscr.getch()
            if key == -1:
                continue
            elif key == curses.KEY_UP:
                cursor = max(0, cursor - 1)
                if cursor < scroll:
                    scroll = cursor
                refresh_detail()
            elif key == curses.KEY_DOWN:
                cursor = min(len(missing) - 1, cursor + 1)
                if cursor >= scroll + list_inner:
                    scroll = cursor - list_inner + 1
                refresh_detail()
            elif key == curses.KEY_PPAGE:
                cursor = max(0, cursor - 10)
                scroll = max(0, scroll - 10)
                refresh_detail()
            elif key == curses.KEY_NPAGE:
                cursor = min(len(missing) - 1, cursor + 10)
                scroll = min(max(0, len(missing) - list_inner), scroll + 10)
                refresh_detail()
            elif key == ord("j"):
                dp.scroll_by(1)
            elif key == ord("k"):
                dp.scroll_by(-1)
            elif key == curses.KEY_RESIZE:
                pass
            elif key in (ord("q"), ord("Q")):
                break

        self._build()

    # ── Delete flow ───────────────────────────────────────────────────────────

    def _delete_flow(self, pid: str, with_deps: bool):
        plan = self.mgr.plan_delete(pid, with_deps=with_deps)
        if not plan:
            return

        lines = []
        danger = bool(plan["dependents"])
        if danger:
            lines.append(f"WARNING: {len(plan['dependents'])} package(s) depend on this!")
            for d in plan["dependents"][:4]:
                lines.append(f"  ^ {d}")
            if len(plan["dependents"]) > 4:
                lines.append(f"  ... and {len(plan['dependents']) - 4} more")
            lines.append("")

        lines.append(f"Will delete {len(plan['to_delete'])} file(s):")
        for p in plan["to_delete"][:12]:
            mb = (
                self.mgr.packages[p].stat().st_size / (1024 * 1024)
                if p in self.mgr.packages
                else 0
            )
            lines.append(f"  {p}  ({mb:.1f} MB)")
        if len(plan["to_delete"]) > 12:
            lines.append(f"  ... and {len(plan['to_delete']) - 12} more")
        lines.append("")
        lines.append(f"Total freed: {plan['total_mb']:.1f} MB")
        if plan.get("keep_deps"):
            lines.append("")
            lines.append(f"Keeping {len(plan['keep_deps'])} shared dep(s) used elsewhere")

        if not confirm_popup(
            self.stdscr,
            "CONFIRM DELETE (has dependents!)" if danger else "Confirm Delete",
            lines,
            danger=danger,
        ):
            self.status = "Cancelled."
            return

        results = self.mgr.execute_delete(plan)
        ok = sum(1 for _, s, _ in results if s)
        fail = len(results) - ok
        self.status = f"Deleted {ok} package(s)." + (f" ({fail} errors)" if fail else "")
        self._build()
