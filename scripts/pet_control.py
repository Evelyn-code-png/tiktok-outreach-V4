"""Start, stop and check the owl desktop pet from the workspace.

The pet holds a local socket on LOCK_PORT so only one owl runs at a time; the
same socket answers 'ping' and 'quit'. Starting it launches scripts/owl_pet.py
as its own process, so closing the browser tab does not close the owl.
"""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

LOCK_PORT = 8799
HERE = Path(__file__).resolve().parent
PET = HERE / 'owl_pet.py'


def send(command, timeout=1.0):
    try:
        with socket.create_connection(('127.0.0.1', LOCK_PORT), timeout=timeout) as conn:
            conn.settimeout(timeout)
            conn.sendall(command.encode('ascii'))
            return conn.recv(16)
    except OSError:
        return None


def running():
    return send('ping') == b'owl'


def python_for_pet():
    """Use pythonw on Windows so no console window appears."""
    exe = Path(sys.executable)
    if os.name == 'nt':
        windowed = exe.with_name('pythonw.exe')
        if windowed.exists():
            return str(windowed)
    return str(exe)


def launch():
    kwargs = {'cwd': str(HERE.parent), 'stdin': subprocess.DEVNULL,
              'stdout': subprocess.DEVNULL, 'stderr': subprocess.DEVNULL}
    if os.name == 'nt':
        kwargs['creationflags'] = getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    else:
        kwargs['start_new_session'] = True
    subprocess.Popen([python_for_pet(), str(PET)], **kwargs)


def control(data):
    action = data.get('action')
    if action not in ('status', 'start', 'stop'):
        raise ValueError('Choose status, start or stop for the desktop owl.')
    supported = os.name == 'nt' or sys.platform == 'darwin'
    if action == 'start' and not running():
        if not PET.exists():
            raise ValueError('The desktop owl is not installed in this copy of the app.')
        launch()
        for _ in range(30):  # the window needs a moment to appear
            time.sleep(0.1)
            if running():
                break
        else:
            raise ValueError('The desktop owl did not start. It needs Python with Tkinter (included in the python.org installer).')
    if action == 'stop' and running():
        send('quit')
        for _ in range(20):
            time.sleep(0.1)
            if not running():
                break
    return {'running': running(), 'supported': supported}
