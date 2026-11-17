from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from reply_content import clean_reply_text,ReplyHTML

class ReplyContentTests(unittest.TestCase):
    def test_replied_message_and_table_headers_are_excluded(self):
        self.assertEqual(clean_reply_text('Thank you. I do.\n\n---- Replied Message ----\n| From | brand@example.com |\n| Date | Today |\n| To | creator@example.com |\nHi Creator, original pitch'), 'Thank you. I do.')
    def test_wrapped_gmail_header_is_excluded(self):
        self.assertEqual(clean_reply_text('Interested!\n\nOn Fri, October 17, 2026 at 5:00 PM\nBrand <brand@example.com> wrote:\nOriginal pitch'), 'Interested!')
    def test_outlook_header_block_is_excluded(self):
        self.assertEqual(clean_reply_text('My rate is $50.\n\nFrom: Brand\nSent: Today\nTo: Me\nSubject: Pitch\nOriginal'), 'My rate is $50.')
    def test_normal_on_sentence_is_preserved(self):
        body='On Monday I can shoot.\nMy rate is $50.\nThanks.';self.assertEqual(clean_reply_text(body),body)
    def test_greater_than_quotes_are_excluded(self):
        self.assertEqual(clean_reply_text('Yes\n\n> Original pitch'), 'Yes')
    def test_chinese_quote_header_is_excluded_without_translating_reply(self):
        self.assertEqual(clean_reply_text('收到，谢谢。\n\n在2026年10月17日，Brand 写道：\nOriginal pitch'), '收到，谢谢。')
    def test_only_spacer_pipe_lines_are_removed(self):
        self.assertEqual(clean_reply_text('Yes\n| |\nCreator name\n|\ncreator@example.com'), 'Yes\nCreator name\ncreator@example.com')
    def test_html_gmail_quote_does_not_leak_original_body(self):
        p=ReplyHTML();p.feed('<div>Interested!</div><div class="gmail_quote gmail_quote_container"><div class="gmail_attr">On Friday wrote:</div><blockquote>Original pitch</blockquote></div>');self.assertEqual(p.result(),'Interested!')
    def test_html_blockquote_and_script_are_excluded(self):
        p=ReplyHTML();p.feed('<p>My reply.</p><script>bad()</script><blockquote><div>Original pitch</div></blockquote>');self.assertEqual(p.result(),'My reply.')
    def test_html_outlook_boundary_stops_original(self):
        p=ReplyHTML();p.feed('<p>My reply.</p><div id="divRplyFwdMsg">From: Original</div><p>Original pitch</p>');self.assertEqual(p.result(),'My reply.')
    def test_html_list_and_self_closing_break_preserve_content(self):
        p=ReplyHTML();p.feed('<div>Hello<br/>I am interested.</div><ul><li>Option A</li><li>Option B</li></ul>');self.assertEqual(p.result(),'Hello\nI am interested.\nOption A\nOption B')

if __name__=='__main__':unittest.main()
