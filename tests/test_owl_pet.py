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


    def test_workspace_can_ping_and_close_the_owl(self):
        self.pet.QUIT_REQUESTED.clear()
        self.assertEqual(self.pet.handle_command('ping\n'), b'owl')
        self.assertFalse(self.pet.QUIT_REQUESTED.is_set())
        self.assertEqual(self.pet.handle_command('quit'), b'bye')
        self.assertTrue(self.pet.QUIT_REQUESTED.is_set())
        self.assertEqual(self.pet.handle_command('rm -rf'), b'?')

if __name__ == '__main__':
    unittest.main()
