"""Owl desktop pet for the Outreach workspace.

The owl hides at the side of the screen with only its head peeking out. Click it and it hops out and
opens the Outreach workspace in your browser (starting the local dashboard if it is not running yet).
Drag it anywhere; drop it near the left or right edge and it hides there again. Right-click for options.

Start it with "Owl Pet.bat" (Windows) or: python scripts/owl_pet.py
"""
import json
import math
import os
import random
import socket
import subprocess
import sys
import threading
import urllib.request
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

try:
    import tkinter as tk
except ImportError:  # pragma: no cover - only on Python builds without Tk
    print('The owl pet needs Tkinter, which is included with the standard Python installer for Windows.')
    raise SystemExit(1)

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
SPRITES = PROJECT / 'assets' / 'pet'
DASHBOARD = HERE / 'dashboard.py'
HOME = Path(os.environ.get('TIKTOK_OUTREACH_HOME', '~/.config/tiktok-outreach-v3')).expanduser()
CONFIG = HOME / 'owl-pet.json'
SESSION = HOME / 'dashboard-session.json'
LOCK_PORT = 8799

KEY = '#ff00fe'  # transparent color used in the sprite sheets
THEMES = ['forest', 'indigo', 'ocean', 'plum', 'coral', 'graphite']
OUTFITS = [('classic', 'Classic'), ('headphones', 'Headphones'), ('beret', 'Beret'), ('bowtie', 'Bow tie'),
           ('scarf', 'Striped scarf'), ('gradcap', 'Grad cap'), ('reindeer', 'Reindeer'), ('holiday-scarf', 'Christmas scarf')]
SCALES = [(7, 0.5), (11, 0.75), (15, 1.0), (22, 1.5), (30, 2.0)]  # sprite file suffix, size relative to the base owl
PET_SIZE = 0.5  # the owl is drawn at half the base size (about 75 px tall on a 100% screen)
# Sprite sheet columns: one row per theme.
COL = {'idle': 0, 'blink': 1, 'flapup': 2, 'flapdown': 3, 'peek': 4, 'peekblink': 5, 'peek-left': 10, 'peekblink-left': 11}
SHEET_COLUMNS = 12
PEEK_CUT = 0.47   # fraction of the frame width kept on screen while peeking from the right edge
IDLE_RETURN_MS = 20000


def load_config():
    try:
        data = json.loads(CONFIG.read_text())
    except (OSError, ValueError):
        data = {}
    data.setdefault('theme', 'forest')
    data.setdefault('outfit', 'classic')
    data.setdefault('side', 'right')
    data.setdefault('y', None)
    if data['theme'] not in THEMES: data['theme'] = 'forest'
    if data['outfit'] not in dict(OUTFITS): data['outfit'] = 'classic'
    if data['side'] not in ('left', 'right'): data['side'] = 'right'
    return data


def save_config(data):
    try:
        HOME.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps(data))
    except OSError:
        pass


def running_dashboard_url():
    """Return the saved workspace link if that dashboard is still answering, otherwise None."""
    try:
        session = json.loads(SESSION.read_text())
        url = session.get('url', '')
        parsed = urlparse(url)
        if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or not parsed.port:
            return None
        token = parsed.fragment.removeprefix('token=')
        request = urllib.request.Request(f'http://127.0.0.1:{parsed.port}/api/status', headers={'X-Outreach-Token': token})
        with urllib.request.urlopen(request, timeout=2) as response:
            json.load(response)
        return url
    except (OSError, ValueError):
        return None


def windows_setup():
    """Sharp sprites on high-DPI screens and the usable screen area (without the taskbar)."""
    if sys.platform != 'win32':
        return None
    import ctypes
    from ctypes import wintypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try: ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError): pass
    rect = wintypes.RECT()
    if ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(rect), 0):
        return rect.left, rect.top, rect.right, rect.bottom
    return None


class OwlPet:
    def __init__(self):
        work_area = windows_setup()
        self.root = tk.Tk()
        self.root.title('Outreach owl')
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.configure(bg=KEY)
        try:
            self.root.attributes('-transparentcolor', KEY)
        except tk.TclError:
            pass  # only Windows supports a transparent color; elsewhere the owl shows on a colored square
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.area = work_area or (0, 0, sw, sh)
        dpi_scale = self.root.winfo_fpixels('1i') / 96
        self.suffix = min(SCALES, key=lambda s: abs(s[1] - dpi_scale * PET_SIZE))[0]

        self.config = load_config()
        self.label = tk.Label(self.root, bg=KEY, bd=0, highlightthickness=0, cursor='hand2')
        self.label.pack()
        self.frames = {}
        self.load_frames()

        self.state = 'docked'   # docked | out | flying
        self.side = self.config['side']
        self.offset = 0         # how far the docked owl currently leans out, in pixels
        self.hover = False
        self.bob = 0.0
        self.blinking = False
        self.anim = None
        self.idle_job = None
        self.server = None
        self.drag = None
        self.bubble = None

        top, bottom = self.area[1], self.area[3]
        default_y = bottom - int(self.h * 1.35)
        self.y = self.config['y'] if isinstance(self.config['y'], int) else default_y
        self.y = max(top, min(self.y, bottom - self.h))
        self.x = self.dock_x()
        self.show(self.peek_frame())
        self.place()

        self.label.bind('<ButtonPress-1>', self.on_press)
        self.label.bind('<B1-Motion>', self.on_drag)
        self.label.bind('<ButtonRelease-1>', self.on_release)
        self.label.bind('<Button-3>', self.on_menu)
        self.label.bind('<Enter>', lambda e: self.set_hover(True))
        self.label.bind('<Leave>', lambda e: self.set_hover(False))
        self.build_menu()
        self.root.after(80, self.tick)
        self.schedule_blink()
        self.schedule_curious()
        if not CONFIG.exists():
            self.root.after(900, lambda: self.say('Hi! Click me to open Outreach.', 4000))
        save_config(self.config)

    # ---------- sprites ----------
    def load_frames(self):
        path = SPRITES / f"owl-{self.config['outfit']}@{self.suffix}.png"
        sheet = tk.PhotoImage(file=str(path))
        self.w = sheet.width() // SHEET_COLUMNS
        self.h = sheet.height() // len(THEMES)
        row = THEMES.index(self.config['theme'])
        self.frames = {}
        for name, col in COL.items():
            image = tk.PhotoImage(width=self.w, height=self.h)
            image.tk.call(image, 'copy', sheet, '-from', col * self.w, row * self.h, (col + 1) * self.w, (row + 1) * self.h, '-to', 0, 0)
            self.frames[name] = image
        self.sheet = sheet

    def show(self, name):
        self.current = name
        self.label.configure(image=self.frames[name])

    def peek_frame(self, blink=False):
        base = 'peekblink' if blink else 'peek'
        return base + ('-left' if self.side == 'left' else '')

    # ---------- position ----------
    def dock_x(self):
        left, right = self.area[0], self.area[2]
        cut = int(self.w * PEEK_CUT)
        if self.side == 'right':
            return right - cut - self.offset
        return left - (self.w - cut) + self.offset

    def place(self):
        bob = int(round(self.bob)) if self.state != 'flying' and not (self.drag and self.drag['moved']) else 0
        self.root.geometry(f'{self.w}x{self.h}+{int(self.x)}+{int(self.y) + bob}')
        if self.bubble: self.place_bubble()

    def tick(self):
        """Gentle breathing while resting, and leaning out a little when the mouse is over the docked owl."""
        if QUIT_REQUESTED.is_set():  # turned off from the workspace Settings
            return self.quit(stop_server=False)
        self.bob = 2.0 * math.sin(self.root.tk.call('clock', 'milliseconds') / 700)
        if self.state == 'docked':
            target = int(self.w * 0.25) if self.hover else 0
            self.offset += (target - self.offset) * 0.35
            if abs(target - self.offset) < 0.5: self.offset = target
            self.x = self.dock_x()
        if self.state != 'flying': self.place()
        self.root.after(60, self.tick)

    # ---------- idle behaviour ----------
    def schedule_blink(self):
        self.root.after(random.randint(2500, 6000), self.blink)

    def blink(self):
        if self.state != 'flying' and not self.blinking:
            self.blinking = True
            closed = self.peek_frame(True) if self.state == 'docked' else 'blink'
            opened = self.peek_frame() if self.state == 'docked' else 'idle'
            self.show(closed)
            def reopen():
                self.blinking = False
                if self.current == closed: self.show(opened)
            self.root.after(160, reopen)
        self.schedule_blink()

    def schedule_curious(self):
        self.root.after(random.randint(25000, 45000), self.curious)

    def curious(self):
        """Every so often the docked owl leans out to look around, then hides again."""
        if self.state == 'docked' and not self.hover:
            self.hover = True
            self.root.after(1600, lambda: self.set_hover(False) if self.state == 'docked' else None)
        self.schedule_curious()

    def set_hover(self, value):
        self.hover = value
        if value and self.state == 'out': self.reset_idle()

    def reset_idle(self):
        if self.idle_job: self.root.after_cancel(self.idle_job)
        self.idle_job = self.root.after(IDLE_RETURN_MS, self.hop_home)

    # ---------- hopping ----------
    def hop(self, x1, y1, done):
        """Hop from the current spot to (x1, y1): a short crouch, then one to three bouncy hops."""
        if self.anim: self.root.after_cancel(self.anim)
        self.state = 'flying'
        x0, y0 = self.x, self.y
        hops = max(1, min(3, round(math.hypot(x1 - x0, y1 - y0) / (self.w * 0.9))))
        crouch, air, land = 110, 330, 70
        total = crouch + hops * air + (hops - 1) * land
        start = self.root.tk.call('clock', 'milliseconds')
        def step():
            t = self.root.tk.call('clock', 'milliseconds') - start
            if t < crouch:
                self.show('blink')
                self.x, self.y = x0, y0 + 8 * math.sin(math.pi * t / crouch)
            else:
                k, r = divmod(t - crouch, air + land)
                k = min(k, hops - 1)
                in_air = min(1.0, r / air) if t < total else 1.0
                progress = min(1.0, (k + in_air) / hops)
                height = self.h * 0.32 * (0.7 ** k)
                self.show('idle')
                self.x = x0 + (x1 - x0) * progress
                self.y = y0 + (y1 - y0) * progress - height * math.sin(math.pi * in_air)
                if r > air and t < total:  # small squash after each landing
                    self.y += 5 * math.sin(math.pi * (r - air) / land)
            self.place()
            if t < total: self.anim = self.root.after(16, step)
            else:
                self.anim = None
                self.x, self.y = x1, y1
                done()
        step()

    def hop_out(self, then_open=True):
        if self.state != 'docked': return
        if self.idle_job: self.root.after_cancel(self.idle_job)
        left, top, right, bottom = self.area
        inward = int(self.w * 1.2)
        x1 = right - self.w - inward if self.side == 'right' else left + inward
        y1 = max(top, min(self.y - 20, bottom - self.h))
        self.offset = 0
        def landed():
            self.state = 'out'
            self.show('idle')
            self.reset_idle()
            if then_open: self.open_workspace()
        self.hop(x1, y1, landed)

    def hop_home(self, side=None):
        if self.state != 'out': return
        if self.idle_job: self.root.after_cancel(self.idle_job); self.idle_job = None
        self.close_bubble()
        left, top, right, bottom = self.area
        if side is None:
            side = 'left' if self.x + self.w / 2 < (left + right) / 2 else 'right'
        self.side = side
        self.offset = 0
        self.y = max(top, min(self.y, bottom - self.h))
        x1 = self.dock_x()
        def docked():
            self.state = 'docked'
            self.show(self.peek_frame())
            self.config.update(side=self.side, y=int(self.y))
            save_config(self.config)
        self.hop(x1, self.y, docked)

    # ---------- mouse ----------
    def on_press(self, event):
        self.drag = {'x': event.x_root, 'y': event.y_root, 'ox': self.x, 'oy': self.y, 'moved': False}

    def on_drag(self, event):
        if not self.drag or self.state == 'flying': return
        dx, dy = event.x_root - self.drag['x'], event.y_root - self.drag['y']
        if not self.drag['moved'] and abs(dx) + abs(dy) < 5: return
        if not self.drag['moved']:
            self.drag['moved'] = True
            if self.state == 'docked':
                self.state = 'out'
                self.offset = 0
                self.drag['ox'] = self.x
            self.show('idle')
        self.x, self.y = self.drag['ox'] + dx, self.drag['oy'] + dy
        self.place()

    def on_release(self, event):
        drag, self.drag = self.drag, None
        if self.state == 'flying' or not drag: return
        if drag['moved']:
            self.show('idle')
            left, right = self.area[0], self.area[2]
            if self.x < left + 60: self.hop_home('left')
            elif self.x + self.w > right - 60: self.hop_home('right')
            else: self.reset_idle()
            return
        if self.state == 'docked': self.hop_out()
        else:
            self.reset_idle()
            self.open_workspace()

    # ---------- workspace ----------
    def open_workspace(self):
        self.say('Opening Outreach…', 2500)
        threading.Thread(target=self._open_workspace, daemon=True).start()

    def _open_workspace(self):
        url = running_dashboard_url()
        if url:
            webbrowser.open(url)
            return
        try:
            HOME.mkdir(parents=True, exist_ok=True)
            log = open(HOME / 'owl-pet-dashboard.log', 'a')
            flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            python = sys.executable
            self.server = subprocess.Popen([python, str(DASHBOARD), '--reuse'], cwd=str(PROJECT),
                                           stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
        except OSError:
            self.root.after(0, lambda: self.say('I could not start Outreach. Open "Open Dashboard.bat" to see why.', 6000))
            return
        for _ in range(40):
            if self.server.poll() is not None: break
            if running_dashboard_url(): return  # the dashboard opens the browser itself
            threading.Event().wait(0.25)
        if self.server.poll() not in (None, 0):
            self.root.after(0, lambda: self.say('Outreach stopped while starting. Open "Open Dashboard.bat" to see why.', 6000))

    # ---------- speech bubble ----------
    def say(self, text, ms):
        self.close_bubble()
        bubble = tk.Toplevel(self.root)
        bubble.overrideredirect(True)
        bubble.attributes('-topmost', True)
        tk.Label(bubble, text=text, bg='#ffffff', fg='#17202a', padx=12, pady=7, font=('Segoe UI', 10),
                 relief='solid', bd=1, wraplength=240, justify='left').pack()
        self.bubble = bubble
        self.place_bubble()
        bubble.after(ms, lambda: self.close_bubble(bubble))

    def place_bubble(self):
        bubble = self.bubble
        bubble.update_idletasks()
        bw, bh = bubble.winfo_reqwidth(), bubble.winfo_reqheight()
        left, top, right, bottom = self.area
        visible_left = self.x + (0 if self.side == 'right' or self.state != 'docked' else self.w * (1 - PEEK_CUT))
        bx = visible_left - bw - 8 if self.side == 'right' else self.x + self.w + 8
        if self.state == 'docked' and self.side == 'left': bx = left + int(self.w * PEEK_CUT) + 8
        bx = max(left, min(int(bx), right - bw))
        by = max(top, min(int(self.y + self.h * 0.15), bottom - bh))
        bubble.geometry(f'+{bx}+{by}')

    def close_bubble(self, which=None):
        if self.bubble and (which is None or which is self.bubble):
            try: self.bubble.destroy()
            except tk.TclError: pass
            self.bubble = None

    # ---------- menu ----------
    def build_menu(self):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label='Open Outreach', command=self.open_workspace)
        menu.add_command(label='Hide at the edge', command=lambda: self.hop_home())
        themes = tk.Menu(menu, tearoff=0)
        self.theme_var = tk.StringVar(value=self.config['theme'])
        for name in THEMES:
            themes.add_radiobutton(label=name.title(), value=name, variable=self.theme_var, command=self.change_look)
        outfits = tk.Menu(menu, tearoff=0)
        self.outfit_var = tk.StringVar(value=self.config['outfit'])
        for value, label in OUTFITS:
            outfits.add_radiobutton(label=label, value=value, variable=self.outfit_var, command=self.change_look)
        menu.add_cascade(label='Theme color', menu=themes)
        menu.add_cascade(label='Owl outfit', menu=outfits)
        menu.add_separator()
        menu.add_command(label='Quit owl', command=self.quit)
        self.menu = menu

    def on_menu(self, event):
        try: self.menu.tk_popup(event.x_root, event.y_root)
        finally: self.menu.grab_release()

    def change_look(self):
        self.config.update(theme=self.theme_var.get(), outfit=self.outfit_var.get())
        save_config(self.config)
        self.load_frames()
        self.show(self.peek_frame() if self.state == 'docked' else 'idle')

    def quit(self, stop_server=True):
        self.config.update(side=self.side, y=int(self.y))
        save_config(self.config)
        if stop_server and self.server and self.server.poll() is None:
            self.server.terminate()  # stop the dashboard only if the owl started it
        self.root.destroy()

    def run(self):
        self.root.mainloop()


QUIT_REQUESTED = threading.Event()


def handle_command(text):
    """Commands the workspace sends over the single-instance socket."""
    command = text.strip().lower()
    if command == 'ping':
        return b'owl'
    if command == 'quit':
        QUIT_REQUESTED.set()
        return b'bye'
    return b'?'


def serve_commands(lock):
    lock.listen(4)

    def serve():
        while True:
            try:
                conn, _ = lock.accept()
            except OSError:
                return
            with conn:
                try:
                    conn.settimeout(2)
                    conn.sendall(handle_command(conn.recv(32).decode('ascii', 'ignore')))
                    conn.recv(1)  # let the caller close first, so this port is not left in TIME_WAIT
                except OSError:
                    pass
    threading.Thread(target=serve, daemon=True).start()


def main():
    lock = socket.socket()
    if os.name != 'nt':
        # Allows a restart while old connections linger; Linux and macOS still refuse a second listener.
        lock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        lock.bind(('127.0.0.1', LOCK_PORT))  # one owl at a time
    except OSError:
        return
    serve_commands(lock)
    OwlPet().run()


if __name__ == '__main__':
    main()
