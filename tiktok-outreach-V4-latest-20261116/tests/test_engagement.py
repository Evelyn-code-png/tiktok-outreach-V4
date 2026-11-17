import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import outreach as o
import workspace as w
import engagement as e


class EngagementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = patch.object(o, 'ROOT', Path(self.tmp.name)); self.root.start()
        self.run = w.import_csv({'title': 'Review list', 'csv_text':
            'name,username,profile_url,email,followers,region,language\n'
            'Emma,emma,https://www.tiktok.com/@emma,emma@example.com,68000,US,en\n'
            'Mia,mia,https://www.tiktok.com/@mia,,20000,GB,en\n'})
        self.key = e.snapshot(self.run['id'])['creators'][0]['key']
        self.base = {'run_id': self.run['id'], 'creator_key': self.key}

    def tearDown(self):
        self.root.stop(); self.tmp.cleanup()

    def brand(self, **extra):
        return e.save_brand({'name': 'LUMA', 'product': 'Daily sunscreen', 'language': 'English',
            'regions': 'US', 'min_followers': '10000', 'max_followers': '100000',
            'content_keywords': 'skincare, sunscreen', **extra})

    def mutate(self, **extra):
        return e.mutate({**self.base, **extra})

    def followup(self):
        return self.mutate(operation='followup', due_at=time.time()+86400,
                           subject='Collaboration with LUMA', body='An editable follow-up draft')

    def test_old_gmail_category_uses_reply_instead_of_quoted_pitch(self):
        self.mutate(operation='reply',body='Thank you. I do.\n\n---- Replied Message ----\nPlease send rates and pricing')
        state=e.load();state['records'][self.key]['replies'][0]['source']='Gmail sync';e.write(state)
        shown=e.snapshot(self.run['id'])['records'][0]['replies'][0]
        self.assertEqual(shown['body'],'Thank you. I do.')
        self.assertEqual(shown['category'],'other')
        self.assertEqual(e.load()['records'][self.key]['replies'][0]['category'],'pricing')

    def test_old_reply_quotes_are_hidden_without_rewriting_saved_mail(self):
        original='Thanks, interested!\n\n---- Replied Message ----\nFrom: Brand\nOriginal pitch'
        self.mutate(operation='reply',body=original)
        stored=e.load()['records'][self.key]['replies'][0]['body']
        self.assertEqual(stored,original)
        snap=e.snapshot(self.run['id'])
        self.assertEqual(snap['records'][0]['replies'][0]['body'],'Thanks, interested!')
        self.assertEqual(e.load()['records'][self.key]['replies'][0]['body'],original)

    def test_brand_round_trip_and_context_persist(self):
        b = self.brand()
        e.set_context({'run_id': self.run['id'], 'brand_id': b['id']})
        e.save_brand({**b, 'product': 'Updated sunscreen'})
        snap = e.snapshot(self.run['id'])
        self.assertEqual(len(snap['brands']), 1)
        self.assertEqual(snap['brands'][0]['product'], 'Updated sunscreen')
        self.assertEqual(snap['contexts'][self.run['id']], b['id'])
        self.assertEqual(json.loads((o.ROOT/'engagement.json').read_text())['contexts'][self.run['id']], b['id'])

    def test_filter_fit_is_separate_from_ai_and_ignores_user_notes(self):
        b = self.brand(); e.set_context({'run_id': self.run['id'], 'brand_id': b['id']})
        match = e.snapshot(self.run['id'])['creators'][0]['match']
        self.assertEqual(match['label'], 'Strong filter fit')
        self.assertEqual(len(match['reasons']), 3)
        self.assertIn('evaluated by AI', match['gaps'][0])
        snap = self.mutate(operation='details', stage='shortlisted', priority='auto',
                           content_notes='Daily sunscreen advice and skincare.', notes='Profile reviewed')
        self.assertEqual(snap['creators'][0]['match']['label'], 'Strong filter fit')
        self.assertEqual(snap['creators'][0]['match']['suggested_priority'], 'high')
        self.assertFalse(any('Saved content notes' in x for x in snap['creators'][0]['match']['reasons']))
        self.assertEqual(snap['creators'][0]['ai_fit']['status'], 'needs_ai')

    def test_missing_data_never_becomes_strong_match(self):
        match = e.matching({}, {}, self.brand())
        self.assertEqual(match['label'], 'Needs review')
        self.assertEqual(match['rank'], 0)
        self.assertEqual(len(match['gaps']), 4)

    def test_keyword_matching_uses_boundaries(self):
        match = e.matching({}, {'content_notes': 'Education'}, {'content_keywords': 'cat'})
        self.assertEqual(match['rank'], 0)

    def test_priority_stage_notes_are_local_and_persistent(self):
        self.mutate(operation='details', stage='negotiating', priority='high', notes='Rate: $200', content_notes='')
        rec = e.snapshot(self.run['id'])['creators'][0]['record']
        self.assertEqual((rec['stage'], rec['priority'], rec['notes']), ('negotiating', 'high', 'Rate: $200'))

    def test_reply_creates_todo_and_pauses_followup(self):
        self.followup()
        snap = self.mutate(operation='reply', body='My rate is $200. What is your budget?')
        rec = snap['creators'][0]['record']
        self.assertEqual(rec['replies'][0]['category'], 'pricing')
        self.assertEqual(rec['stage'], 'replied')
        self.assertEqual(rec['todos'][0]['status'], 'paused')
        self.assertEqual(rec['todos'][1]['kind'], 'reply')
        self.assertEqual(rec['replies'][0]['source'], 'Manually recorded')
        with self.assertRaisesRegex(ValueError, 'reply'):
            self.followup()
        done = self.mutate(operation='complete', todo_id=rec['todos'][1]['id'])
        self.assertEqual(done['creators'][0]['record']['todos'][1]['status'], 'completed')

    def test_automatic_reply_does_not_pause_followup(self):
        self.followup(); snap = self.mutate(operation='reply', body='Automatic reply: out of office until Friday.')
        rec = snap['creators'][0]['record']
        self.assertEqual(rec['replies'][0]['category'], 'automatic')
        self.assertEqual(rec['todos'][0]['status'], 'pending')
        self.assertEqual(len(rec['todos']), 1)

    def test_override_category_and_decline_close_stage(self):
        snap = self.mutate(operation='reply', body='Not interested, thank you.', category='declined')
        self.assertEqual(snap['creators'][0]['record']['stage'], 'closed')
        self.assertFalse(snap['creators'][0]['record']['todos'])
        with self.assertRaises(ValueError): self.followup()

    def test_unsubscribe_also_protects_existing_send_workflow(self):
        self.mutate(operation='reply', body='Please remove me from your list.')
        with o.db_open() as db:
            self.assertEqual(db.execute('SELECT email FROM suppressed').fetchall(), [('emma@example.com',)])

    def test_existing_reply_event_dynamically_pauses_reminder(self):
        self.followup(); o.record_tracking('existing-campaign', 'emma@example.com', 'reply')
        snap = e.snapshot(self.run['id'])
        self.assertEqual(snap['records'][0]['todos'][0]['status'], 'paused')
        self.assertEqual(snap['creators'][0]['record']['todos'][0]['status'], 'paused')
        with self.assertRaisesRegex(ValueError, 'reply'): self.followup()

    def test_existing_delivery_suggests_contacted_stage(self):
        with o.db_open() as db:
            db.execute('INSERT INTO deliveries VALUES (?,?,?,?,?)', ('old-campaign', 'emma@example.com', 'sent_browser', 'id', 123))
        self.assertEqual(e.snapshot(self.run['id'])['creators'][0]['record']['stage'], 'contacted')

    def test_reply_on_another_list_blocks_followup_for_same_email(self):
        self.mutate(operation='reply', body='Sounds good, I am interested.')
        run2 = w.import_csv({'csv_text': 'name,email\nEmma,emma@example.com\n'})
        second = e.snapshot(run2['id'])['creators'][0]
        self.assertTrue(second['record']['followup_blocked'])
        with self.assertRaises(ValueError):
            e.mutate({'run_id': run2['id'], 'creator_key': second['key'], 'operation': 'followup',
                      'due_at': time.time()+1000, 'subject': 'Hi', 'body': 'Hi'})

    def test_unknown_contact_ids_and_invalid_fields_are_rejected(self):
        for change in ({'creator_key':'x'*24}, {'run_id':'../escape'}):
            with self.assertRaises(ValueError): e.mutate({**self.base, 'operation':'details', **change})
        for change in ({'stage':'unknown'}, {'priority':'urgent'}, {'notes':{}}):
            with self.assertRaises(ValueError): self.mutate(operation='details', **change)
        for value in ('NaN', float('inf'), None, 9999999999999):
            with self.assertRaises(ValueError): self.mutate(operation='followup', due_at=value, subject='Hi', body='Hi')
        for extra in ({'max_followers':'1'}, {'min_followers':'NaN'}, {'regions':'America'}):
            with self.assertRaises(ValueError): self.brand(**extra)

    def test_new_features_do_not_call_providers_or_send_mail(self):
        with patch.object(o, 'api', side_effect=AssertionError('No external API calls')), \
             patch.object(o.smtplib, 'SMTP_SSL', side_effect=AssertionError('No SMTP sends')):
            self.brand(); self.followup(); self.mutate(operation='reply', body='Can you share more details?')
            e.snapshot(self.run['id'])
        with o.db_open() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM deliveries').fetchone()[0], 0)

    def test_contacts_without_email_can_have_notes_but_not_email_followups(self):
        key = e.snapshot(self.run['id'])['creators'][1]['key']
        e.mutate({'run_id':self.run['id'], 'creator_key':key, 'operation':'details', 'notes':'Find email later'})
        with self.assertRaisesRegex(ValueError, 'email'):
            e.mutate({'run_id':self.run['id'], 'creator_key':key, 'operation':'followup',
                      'due_at':time.time()+1000, 'subject':'Hi', 'body':'Hi'})


if __name__ == '__main__':
    unittest.main()
