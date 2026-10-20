import sys, tempfile, unittest, json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import outreach as o
import workspace as w
import creator_photos as photos

class CreatorPhotoTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=o.ROOT;o.ROOT=Path(self.tmp.name)
        self.run=o.ROOT/'runs'/'demo';self.run.mkdir(parents=True)
        self.profile='https://www.tiktok.com/@demo'
        o.csv_write(self.run/'creators.csv',[{'name':'Demo','profile_url':self.profile,'email':'demo@example.com'}])
    def tearDown(self):
        o.ROOT=self.old;self.tmp.cleanup()
    def test_reject_unsafe_images(self):
        for url in ['javascript:alert(1)','data:image/svg+xml,test','http://example.com/a','https://user:pass@example.com/a']:
            self.assertEqual(o.avatar_url({'avatarUrl':url}),'')
    def test_normalization_and_csv_preserve_photo(self):
        url='https://example.com/photo.jpg'
        rows=o.normalize([{'nickname':'Demo','avatarThumb':{'url_list':[url]},'email':'demo@example.com'}])
        o.csv_write(self.run/'new.csv',rows)
        self.assertEqual(o.csv_read(self.run/'new.csv')[0]['avatar_url'],url)
    def test_old_list_enriched_without_rewriting_or_provider_call(self):
        original=(self.run/'creators.csv').read_bytes()
        (self.run/'raw-1.json').write_text(json.dumps({'data':[{'profileUrl':self.profile,'avatarUrl':'https://example.com/photo.jpg'}]}))
        with patch('personalization.fetch_kol_details') as fetch:
            self.assertEqual(w.get_run('demo')['contacts'][0]['avatar_url'],'https://example.com/photo.jpg')
            fetch.assert_not_called()
        self.assertEqual((self.run/'creators.csv').read_bytes(),original)
    def test_explicit_lookup_cached(self):
        with patch('personalization.fetch_kol_details',return_value={'avatar_url':'https://example.com/photo.jpg'}) as fetch:
            self.assertFalse(photos.resolve({'run_id':'demo','profile_url':self.profile})['cached'])
            self.assertTrue(photos.resolve({'run_id':'demo','profile_url':self.profile})['cached'])
            fetch.assert_called_once()
            self.assertEqual(w.get_run('demo')['contacts'][0]['avatar_url'],'https://example.com/photo.jpg')
    def test_unlisted_creator_cannot_trigger_provider_request(self):
        with patch('personalization.fetch_kol_details') as fetch:
            with self.assertRaises(ValueError):photos.resolve({'run_id':'demo','profile_url':'https://www.tiktok.com/@other'})
            fetch.assert_not_called()
