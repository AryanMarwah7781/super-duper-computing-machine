"""Bring a minimised window back to the front.

    .venv\\Scripts\\python tools\\raise_window.py --list
    .venv\\Scripts\\python tools\\raise_window.py "Farming Simulator"
    .venv\\Scripts\\python tools\\raise_window.py "Farming Simulator" --maximize
    .venv\\Scripts\\python tools\\raise_window.py "Farming Simulator" --after 5

Windows will not let a background process steal the foreground on request --
that is what stops an advert raising itself over what you are typing. The
sanctioned way round it is to attach to the input state of the thread that
currently owns the foreground, which makes this process look like the
foreground for the length of the call. That is done here, but only after the
polite SetForegroundWindow has been tried and refused, because when the app
already has focus the plain call works and the attach is not needed.

Restore, not maximise, is the default: SW_RESTORE puts a window back the size
it was before it was minimised, while SW_MAXIMIZE resizes a game somebody had
deliberately left windowed.

Nothing here is wired into the app. It acts on this machine's windows, so it
only makes sense where the simulator and the assistant share a box.
"""
from __future__ import annotations

import argparse
import ctypes
import sys
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

SW_MAXIMIZE = 3
SW_RESTORE = 9

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND,
                                            ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD,
                                     wintypes.BOOL]
kernel32.GetCurrentThreadId.restype = wintypes.DWORD


def _title(hwnd: int) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    if not n:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def windows() -> list[tuple[int, str, bool]]:
    """Every visible top-level window with a title: hwnd, title, minimised."""
    out: list[tuple[int, str, bool]] = []

    def visit(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd):
            name = _title(hwnd)
            if name:
                out.append((hwnd, name, bool(user32.IsIconic(hwnd))))
        return True

    # The callback is kept in a local so it outlives the call; letting it be
    # collected mid-enumeration crashes the interpreter, not just this scan.
    cb = WNDENUMPROC(visit)
    user32.EnumWindows(cb, 0)
    return out


def find(needle: str) -> list[tuple[int, str, bool]]:
    n = needle.casefold()
    return [w for w in windows() if n in w[1].casefold()]


def raise_window(hwnd: int, maximize: bool = False) -> bool:
    """Un-minimise and foreground. True if it really ended up in front."""
    user32.ShowWindow(hwnd, SW_MAXIMIZE if maximize else SW_RESTORE)

    if user32.SetForegroundWindow(hwnd):
        return True

    target = user32.GetWindowThreadProcessId(hwnd, None)
    current = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(),
                                              None)
    me = kernel32.GetCurrentThreadId()
    borrowed = {target, current} - {me, 0}

    for other in borrowed:
        user32.AttachThreadInput(me, other, True)
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        # Detach whatever was attached, even if the calls above threw. A
        # thread left attached shares input state for the life of the
        # process, which is a far worse bug than a window that stayed down.
        for other in borrowed:
            user32.AttachThreadInput(me, other, False)

    return user32.GetForegroundWindow() == hwnd


def main() -> int:
    # Window titles are arbitrary Unicode and the console here is cp1252: a
    # browser tab with a zero-width space in it killed the listing outright.
    # A mangled character in a title is nothing; a traceback instead of the
    # list is the difference between finding the window and not.
    try:
        sys.stdout.reconfigure(errors="replace")
    except AttributeError:
        pass

    parser = argparse.ArgumentParser(prog="raise_window")
    parser.add_argument("title", nargs="?",
                        help="part of the window title, case-insensitive")
    parser.add_argument("--list", action="store_true",
                        help="show every window that could be raised")
    parser.add_argument("--maximize", action="store_true",
                        help="force maximised instead of its previous size")
    parser.add_argument("--after", type=float, default=0.0, metavar="SECONDS",
                        help="count down first, so you can minimise it by hand")
    args = parser.parse_args()

    if args.list or not args.title:
        for hwnd, name, minimised in windows():
            print(f"  {hwnd:>10}  {'min' if minimised else '   '}  {name}")
        if not args.title and not args.list:
            print("\nPass part of a title to raise one of these.")
        return 0

    matches = find(args.title)
    if not matches:
        print(f"nothing matching {args.title!r}. --list shows what is open.")
        return 1
    if len(matches) > 1:
        print(f"{len(matches)} windows match {args.title!r}:")
        for _, name, _ in matches:
            print(f"  {name}")
        print("Be more specific.")
        return 1

    hwnd, name, minimised = matches[0]
    print(f"found  {name}  ({'minimised' if minimised else 'on screen'})")

    if args.after:
        for left in range(int(args.after), 0, -1):
            print(f"  raising in {left}...", end="\r", flush=True)
            time.sleep(1)
        print(" " * 24, end="\r")

    if raise_window(hwnd, maximize=args.maximize):
        print("raised, and it has the foreground")
        return 0

    # Worth separating: the window came up but focus did not follow, which is
    # what exclusive-fullscreen games do while the swap chain comes back.
    print("shown, but something else still holds the foreground.")
    print("If this is a fullscreen game, set it to borderless windowed.")
    return 2


if __name__ == "__main__":
    if sys.platform != "win32":
        raise SystemExit("Windows only - this is the Win32 window API.")
    raise SystemExit(main())
