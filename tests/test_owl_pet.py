import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HAS_TK = importlib.util.find_spec('tkinter') is not None


@unittest.skipUnless(HAS_TK, 'Tkinter is not installed')
class OwlPetTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        os.environ['TIKTOK_OUTREACH_HOME'] = self.home
        sys.path.insert(0, str(ROOT / 'scripts'))
        sys.modules.pop('owl_pet', None)
        import owl_pet
        self.pet = owl_pet

    def tearDown(self):
        os.environ.pop('TIKTOK_OUTREACH_HOME', None)
        sys.path.remove(str(ROOT / 'scripts'))

    def test_every_outfit_has_sprites_for_every_screen_scale(self):
        for outfit, _ in self.pet.OUTFITS:
            for suffix, _ in self.pet.SCALES:
                self.assertTrue((self.pet.SPRITES / f'owl-{outfit}@{suffix}.png').exists(), (outfit, suffix))

    def test_config_falls_back_to_safe_values(self):
        self.pet.CONFIG.parent.mkdir(parents=True, exist_ok=True)
        self.pet.CONFIG.write_text(json.dumps({'theme': 'neon', 'outfit': 'cape', 'side': 'top', 'y': 120}))
        config = self.pet.load_config()
        self.assertEqual((config['theme'], config['outfit'], config['side'], config['y']), ('forest', 'classic', 'right', 120))

    def test_no_dashboard_link_without_a_running_workspace(self):
        self.assertIsNone(self.pet.running_dashboard_url())
        self.pet.SESSION.write_text(json.dumps({'url': 'https://example.com/#token=x'}))
        self.assertIsNone(self.pet.running_dashboard_url())


    def test_mac_sprites_make_only_the_key_color_transparent(self):
        import struct, zlib
        for outfit, _ in self.pet.OUTFITS:
            path = self.pet.SPRITES / f'owl-{outfit}@7.png'
            data = self.pet.png_with_transparent_key(path)
            chunks, pos = {}, 8
            while pos < len(data):
                length, kind = struct.unpack('>I4s', data[pos:pos + 8])
                body = data[pos + 8:pos + 8 + length]
                crc, = struct.unpack('>I', data[pos + 8 + length:pos + 12 + length])
                self.assertEqual(crc, zlib.crc32(kind + body) & 0xffffffff)
                chunks.setdefault(kind, body); pos += 12 + length
            palette, alpha = chunks[b'PLTE'], chunks[b'tRNS']
            for i, a in enumerate(alpha):
                is_key = palette[3 * i:3 * i + 3] == bytes([255, 0, 254])
                self.assertEqual(a, 0 if is_key else 255, (outfit, i))
            self.assertIn(0, alpha)
            self.assertEqual(self.pet.png_with_transparent_key(path)[:8], path.read_bytes()[:8])

    def test_mac_work_area_avoids_menu_bar_and_dock(self):
        left, top, right, bottom = self.pet.mac_work_area(1440, 900)
        self.assertEqual((left, right), (0, 1440))
        self.assertGreater(top, 0); self.assertLess(bottom, 900)

    def test_workspace_can_ping_and_close_the_owl(self):
        self.pet.QUIT_REQUESTED.clear()
        self.assertEqual(self.pet.handle_command('ping\n'), b'owl')
        self.assertFalse(self.pet.QUIT_REQUESTED.is_set())
        self.assertEqual(self.pet.handle_command('quit'), b'bye')
        self.assertTrue(self.pet.QUIT_REQUESTED.is_set())
        self.assertEqual(self.pet.handle_command('rm -rf'), b'?')

if __name__ == '__main__':
    unittest.main()
