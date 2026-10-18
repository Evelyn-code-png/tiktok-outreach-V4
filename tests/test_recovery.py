"""Process-crash and concurrent-claim tests; no real mail/network is used."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import outreach as o
import workspace as w

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=patch.object(o,'ROOT',Path(self.tmp.name));self.root.start()
        o.save_json(o.ROOT/'config.json',{'sender':'fixture@example.com','gmail_app_password':'fixture'})
        contacts=o.ROOT/'contacts.csv'
        o.csv_write(contacts,o.normalize([{'name':'Fixture','email':'recipient@example.com'}]))
        body=o.ROOT/'body.txt';body.write_text('Local process-crash test; no real transport.')
        self.campaign=o.draft(NS(csv=str(contacts),body=str(body),subject='Fixture',out=str(o.ROOT/'campaign.json')))

    def tearDown(self):
        self.root.stop();self.tmp.cleanup()

    def test_concurrent_browser_claim_has_one_winner(self):
        # Initialize schema before simultaneous delivery reservations.
        with o.db_open():pass
        barrier=threading.Barrier(2);results=[]
        def claim():
            barrier.wait()
            try:o.browser_claim(NS(campaign=self.campaign['campaign_file'],email='recipient@example.com'));results.append('reserved')
            except ValueError:results.append('blocked')
        threads=[threading.Thread(target=claim) for _ in range(2)]
        for t in threads:t.start()
        for t in threads:t.join(timeout=10)
        self.assertEqual(sorted(results),['blocked','reserved'])

    def test_killed_submission_is_not_retried_after_restart(self):
        script=r'''
from pathlib import Path
import sys,time
from types import SimpleNamespace as NS
sys.path.insert(0,sys.argv[1])
import outreach as o
import workspace as w
o.ROOT=Path(sys.argv[2])
class InterruptedSMTP:
 def __init__(self,*a,**kw):pass
 def __enter__(self):return self
 def __exit__(self,*a):pass
 def login(self,*a):pass
 def send_message(self,msg):
  print('submission-reached',flush=True)
  time.sleep(60)
o.smtplib.SMTP_SSL=InterruptedSMTP
job={'id':'crash-test','kind':'send','status':'queued','created':1}
w.run_job(job,{'campaign_id':sys.argv[3],'max_messages':1})
'''
        root=o.ROOT
        campaigns=root/'campaigns';campaigns.mkdir()
        (campaigns/(self.campaign['campaign_id']+'.json')).write_bytes(Path(self.campaign['campaign_file']).read_bytes())
        child=subprocess.Popen([sys.executable,'-u','-c',script,str(Path(o.__file__).parent),str(root),self.campaign['campaign_id']],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            # A timer bounds a broken fixture without relying on a long sleep.
            timer=threading.Timer(10,child.kill);timer.start()
            self.assertEqual(child.stdout.readline().strip(),'submission-reached')
            child.kill();child.wait(timeout=5)
        finally:
            timer.cancel()
            if child.poll() is None:child.kill();child.wait(timeout=5)
            child.stdout.close();child.stderr.close()
        w.recover_jobs()
        self.assertEqual(w.get_job('crash-test')['status'],'interrupted')
        plan=o.browser_plan(NS(campaign=self.campaign['campaign_file']))
        self.assertEqual(plan['pending'],[])
        self.assertEqual(plan['skipped'][0]['status'],'sending')

if __name__=='__main__':unittest.main()
