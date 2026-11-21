from pathlib import Path
import socket
import sys
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import pet_control as pc


class FakeOwl:
    """Stands in for the owl's single-instance socket on a free port."""
    def __init__(self):
        self.sock = socket.socket(); self.sock.bind(('127.0.0.1', 0)); self.sock.listen(4)
        self.port = self.sock.getsockname()[1]; self.alive = True; self.commands = []
        threading.Thread(target=self.serve, daemon=True).start()

    def serve(self):
        while self.alive:
            try: conn, _ = self.sock.accept()
            except OSError: return
            with conn:
                cmd = conn.recv(32).decode().strip(); self.commands.append(cmd)
                conn.sendall(b'owl' if cmd == 'ping' else b'bye')
                if cmd == 'quit': self.alive = False; self.sock.close()


class PetControlTests(unittest.TestCase):
    def setUp(self):
        self.port = patch.object(pc, 'LOCK_PORT', self.free_port()); self.port.start()

    def tearDown(self):
        self.port.stop()

    def free_port(self):
        s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close(); return port

    def test_status_is_off_when_no_owl_is_listening(self):
        self.assertFalse(pc.control({'action': 'status'})['running'])

    def test_unknown_action_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'status, start or stop'):
            pc.control({'action': 'delete'})

    def test_start_launches_owl_once(self):
        owl = None
        def fake_launch():
            nonlocal owl
            owl = FakeOwl(); pc.LOCK_PORT = owl.port
        with patch.object(pc, 'launch', side_effect=fake_launch) as launch:
            self.assertTrue(pc.control({'action': 'start'})['running'])
            self.assertTrue(pc.control({'action': 'start'})['running'])
        self.assertEqual(launch.call_count, 1)

    def test_stop_sends_quit_to_a_running_owl(self):
        owl = FakeOwl(); pc.LOCK_PORT = owl.port
        self.assertFalse(pc.control({'action': 'stop'})['running'])
        self.assertIn('quit', owl.commands)

    def test_failed_start_explains_what_is_needed(self):
        with patch.object(pc, 'launch'), patch.object(pc.time, 'sleep'):
            with self.assertRaisesRegex(ValueError, 'Tkinter'):
                pc.control({'action': 'start'})

    def test_owl_is_offered_on_windows_and_macos_only(self):
        for os_name, platform, expected in [('nt', 'win32', True), ('posix', 'darwin', True), ('posix', 'linux', False)]:
            with patch.object(pc.os, 'name', os_name), patch.object(pc.sys, 'platform', platform):
                self.assertEqual(pc.control({'action': 'status'})['supported'], expected, platform)

    def test_launch_runs_the_pet_script_detached(self):
        with patch.object(pc.subprocess, 'Popen') as popen:
            pc.launch()
        args, kwargs = popen.call_args
        self.assertEqual(args[0][1], str(pc.PET))
        self.assertIs(kwargs['stdout'], pc.subprocess.DEVNULL)


if __name__ == '__main__':
    unittest.main()
