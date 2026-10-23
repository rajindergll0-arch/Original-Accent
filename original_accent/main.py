"""Entry point: python -m original_accent  (add --browser to use a browser tab instead of the window)."""
import os, socket, sys, time, webbrowser
from . import paths, server

LOCK_PORT = 47821   # single instance: a second launch just exits


def _dpi_aware():
    """Per-monitor DPI awareness before any window exists, so text stays sharp on 125/150/200%
    displays and the window resizes correctly when dragged between monitors."""
    if os.name != "nt":
        return
    import ctypes
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass


def _single_instance():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", LOCK_PORT))
        return s
    except OSError:
        return None


def _window_size(webview):
    """Size from the screen in logical pixels: 85% of the work area, never below the minimum
    the layouts are designed for, never larger than the screen."""
    try:
        sc = webview.screens[0]
        w, h = int(sc.width * 0.85), int(sc.height * 0.85)
    except Exception:
        w, h = 1440, 900
    return max(1100, min(w, 1920)), max(720, min(h, 1200))


def _app_identity():
    """Own taskbar identity, so Windows groups and labels the window as Original Accent, not Python."""
    if os.name == "nt":
        import ctypes
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("OriginalAccent.App")
        except Exception:
            pass


def _set_window_icon(title="Original Accent"):
    """pywebview's Windows backend shows python's icon; swap in ours on the real window."""
    if os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes
    ico = str(paths.UI / "icon.ico")
    u = ctypes.windll.user32
    # 64-bit handles: declare types or ctypes truncates them to 32 bits
    u.FindWindowW.restype = wintypes.HWND
    u.LoadImageW.restype = wintypes.HANDLE
    u.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    u.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    for _ in range(50):
        hwnd = u.FindWindowW(None, title)
        if hwnd:
            break
        time.sleep(0.1)
    else:
        return
    LR_LOADFROMFILE, IMAGE_ICON, WM_SETICON = 0x10, 1, 0x80
    big = u.LoadImageW(None, ico, IMAGE_ICON, 256, 256, LR_LOADFROMFILE)
    small = u.LoadImageW(None, ico, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
    if big:
        u.SendMessageW(hwnd, WM_SETICON, 1, big or 0)
    if small:
        u.SendMessageW(hwnd, WM_SETICON, 0, small or 0)


def main():
    lock = _single_instance()
    if lock is None and "--wait-lock" in sys.argv:      # restarting: wait for the old copy to exit
        for _ in range(60):
            time.sleep(0.25)
            lock = _single_instance()
            if lock:
                break
    if lock is None:
        sys.exit(0)
    _app_identity()
    _dpi_aware()
    httpd, url = server.serve()
    if "--browser" in sys.argv:
        print(url); webbrowser.open(url)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return
    import webview
    w, h = _window_size(webview)
    win = webview.create_window("Original Accent", url, width=w, height=h, min_size=(1100, 720),
                                background_color="#111214", text_select=True)
    server.WINDOW["w"] = win
    win.events.shown += lambda: _set_window_icon()
    webview.start(gui="edgechromium" if os.name == "nt" else None, private_mode=False,
                  storage_path=str(paths.DATA / "webview"))


if __name__ == "__main__":
    main()
