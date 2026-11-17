import concurrent.futures
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import creator_fit as f
import engagement as e
import outreach as o
import personalization as p
import workspace as w


class CreatorFitTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=patch.object(o,'ROOT',Path(self.tmp.name));self.root.start()
        self.env=patch.dict(f.os.environ, {'OPENAI_API_KEY':'','OPENAI_MODEL':''});self.env.start()
        self.config={'openai_key':'test-secret','openai_model':'test-model','easykol_key':'ek_test','easykol_email':'demo@example.com'}
        o.save_json(o.ROOT/'config.json',self.config)
        self.run=w.import_csv({'csv_text':'name,username,profile_url,email,followers,region,language\nEmma,emma,https://www.tiktok.com/@emma,emma@example.com,68000,US,en\n'})
        self.brand=e.save_brand({'name':'LUMA','product':'Daily sunscreen','goal':'Honest skincare partnerships','regions':'US','language':'English'})
        e.set_context({'run_id':self.run['id'],'brand_id':self.brand['id']})
        self.base={'run_id':self.run['id'],'creator_key':e.key_for(self.run['id'],self.run['contacts'][0])}
        self.profile={'description':'Shares sensitive-skin skincare routines and daily sunscreen advice.','aiTags':'skincare, sunscreen','username':'emma','profileUrl':'https://www.tiktok.com/@emma'}
        o.save_json(o.ROOT/'runs'/self.run['id']/'raw-1.json',{'data':[self.profile]})

    def tearDown(self):
        self.env.stop();self.root.stop();self.tmp.cleanup()

    def output(self):
        return {'verdict':'strong','summary':'Emma’s skincare focus is relevant to LUMA’s daily sunscreen.',
            'reasons':[{'reason':'Her sensitive-skin skincare focus provides a relevant context for the product.',
                        'evidence_field':'description','evidence_quote':'sensitive-skin skincare routines'}],
            'collaboration_angle':'Propose a daily sunscreen routine demonstration, subject to her interest.',
            'missing_information':['Audience demographics and recent posts have not been verified.']}

    def response(self,output):
        response=MagicMock()
        response.__enter__.return_value.read.return_value=json.dumps({'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(output)}]}]}).encode()
        return response

    def test_generates_real_model_request_from_easykol_facts_without_notes(self):
        e.mutate({**self.base,'operation':'details','content_notes':'UNTRUSTED MANUAL CLAIMS','notes':'PRIVATE CORRESPONDENCE'})
        with patch.object(f.urllib.request,'urlopen',return_value=self.response(self.output())) as model, patch.object(p,'fetch_kol_details') as lookup:
            result=f.generate(self.base)
        self.assertFalse(result['cached']);lookup.assert_not_called()
        request=model.call_args.args[0]
        self.assertEqual(request.full_url,'https://api.openai.com/v1/responses')
        payload=json.loads(request.data)
        self.assertEqual(payload['model'],'test-model')
        self.assertEqual(payload['text']['format']['type'],'json_schema')
        self.assertIn('daily sunscreen advice',payload['input'])
        for private in ('UNTRUSTED MANUAL CLAIMS','PRIVATE CORRESPONDENCE','emma@example.com'):
            self.assertNotIn(private,payload['input'])
        fit=result['snapshot']['creators'][0]['ai_fit']
        self.assertEqual(fit['status'],'ready');self.assertTrue(fit['result']['reasons'])

    def test_valid_cache_avoids_model_and_lookup_calls(self):
        with patch.object(f.urllib.request,'urlopen',return_value=self.response(self.output())) as model:
            f.generate(self.base);result=f.generate(self.base)
        self.assertTrue(result['cached']);self.assertEqual(model.call_count,1)

    def test_changed_brand_invalidates_and_regenerates(self):
        with patch.object(f.urllib.request,'urlopen',return_value=self.response(self.output())) as model:
            f.generate(self.base)
            e.save_brand({**self.brand,'product':'New sunscreen formulation'})
            self.assertEqual(e.snapshot(self.run['id'])['creators'][0]['ai_fit']['status'],'stale')
            f.generate(self.base)
        self.assertEqual(model.call_count,2)

    def test_missing_ai_is_explicit_and_never_spends_easykol_credits(self):
        o.save_json(o.ROOT/'config.json',{'easykol_key':'ek_test','easykol_email':'demo@example.com'})
        self.assertEqual(e.snapshot(self.run['id'])['creators'][0]['ai_fit']['status'],'needs_ai')
        with patch.object(p,'fetch_kol_details') as lookup,patch.object(f.urllib.request,'urlopen') as model:
            with self.assertRaisesRegex(ValueError,'Account Setup'): f.generate(self.base)
        lookup.assert_not_called();model.assert_not_called()

    def test_missing_brand_is_explicit(self):
        e.set_context({'run_id':self.run['id'],'brand_id':''})
        self.assertEqual(e.snapshot(self.run['id'])['creators'][0]['ai_fit']['status'],'needs_brand')
        with self.assertRaisesRegex(ValueError,'brand brief'): f.generate(self.base)

    def test_search_goal_can_generate_fit_without_a_brand_form(self):
        e.set_context({'run_id':self.run['id'],'brand_id':''})
        o.save_json(o.ROOT/'runs'/self.run['id']/'meta.json',{'title':'US skincare and beauty creators','source':'EasyKOL'})
        self.assertEqual(e.snapshot(self.run['id'])['creators'][0]['ai_fit']['status'],'not_generated')
        with patch.object(f.urllib.request,'urlopen',return_value=self.response(self.output())) as model:
            result=f.generate(self.base)
        source=json.loads(json.loads(model.call_args.args[0].data)['input'])
        self.assertEqual(source['brand']['goal'],'US skincare and beauty creators')
        self.assertEqual(source['brand']['product'],'')
        self.assertEqual(result['snapshot']['creators'][0]['ai_fit']['status'],'ready')

    def test_private_notes_never_change_cached_fit(self):
        with patch.object(f.urllib.request,'urlopen',return_value=self.response(self.output())) as model:
            f.generate(self.base)
            e.mutate({**self.base,'operation':'details','notes':'A private note','content_notes':'Manual claims'})
            result=f.generate(self.base)
        self.assertTrue(result['cached']);self.assertEqual(model.call_count,1)

    def test_profile_lookup_is_automatic_when_search_data_is_sparse(self):
        (o.ROOT/'runs'/self.run['id']/'raw-1.json').unlink()
        with patch.object(p,'fetch_kol_details',return_value={'description':self.profile['description']}) as lookup,patch.object(f.urllib.request,'urlopen',return_value=self.response(self.output())):
            result=f.generate(self.base)
        lookup.assert_called_once_with('https://www.tiktok.com/@emma')
        self.assertEqual(result['snapshot']['creators'][0]['ai_fit']['status'],'ready')

    def test_hallucinated_evidence_is_rejected_and_not_cached(self):
        output=self.output();output['reasons'][0]['evidence_quote']='A video that was never provided'
        with patch.object(f.urllib.request,'urlopen',return_value=self.response(output)):
            with self.assertRaisesRegex(ValueError,'not supplied'): f.generate(self.base)
        self.assertFalse(f.load_cache()['analyses'])

    def test_no_content_facts_cannot_receive_strong_verdict(self):
        profile=f.clean_profile({},self.run['contacts'][0]);output=self.output()
        output['reasons']=[{'reason':'The creator is in the selected region, but content fit is unknown.','evidence_field':'region','evidence_quote':'US'}]
        with patch.object(f.urllib.request,'urlopen',return_value=self.response(output)):
            result=f.call_model(profile,self.brand)
        self.assertEqual(result['verdict'],'insufficient')
        self.assertNotEqual(result['priority'],'high')

    def test_external_failures_are_clear_and_never_cache_a_fake_result(self):
        for code in (401,429,500):
            with self.subTest(code=code),patch.object(f.urllib.request,'urlopen',side_effect=urllib.error.HTTPError('https://api.openai.com',code,'PRIVATE',{},None)):
                with self.assertRaises(ValueError) as ctx:f.generate(self.base)
                self.assertNotIn('PRIVATE',str(ctx.exception))
                self.assertFalse(f.load_cache()['analyses'])

    def test_concurrent_opens_generate_once(self):
        with patch.object(f.urllib.request,'urlopen',return_value=self.response(self.output())) as model:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(lambda _:f.generate(self.base),range(2)))
        self.assertEqual(model.call_count,1);self.assertEqual(sum(x['cached'] for x in results),1)

    def test_english_output_and_shape_are_validated(self):
        for bad in ([],{}, {**self.output(),'summary':'中文'}, {**self.output(),'missing_information':'not a list'}, {**self.output(),'reasons':[]}):
            with patch.object(f.urllib.request,'urlopen',return_value=self.response(bad)):
                with self.assertRaises(ValueError): f.generate(self.base)

    def test_explicit_regenerate_reuses_profile_and_never_sends_mail(self):
        with patch.object(f.urllib.request,'urlopen',return_value=self.response(self.output())) as model,patch.object(o.smtplib,'SMTP_SSL',side_effect=AssertionError('No sends')):
            f.generate(self.base);f.generate({**self.base,'regenerate':True})
        self.assertEqual(model.call_count,2)
        self.assertFalse((o.ROOT/'outreach.sqlite').exists())
