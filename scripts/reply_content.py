"""Extract reply text without quoted earlier messages."""
import re
from html.parser import HTMLParser


def clean_reply_text(body):
    lines = str(body or '').replace('\r\n','\n').replace('\r','\n').splitlines()
    kept=[]
    for index,line in enumerate(lines):
        stripped=line.strip()
        window=' '.join(x.strip() for x in lines[index:index+5])
        marker=(re.match(r'^[-_=]{2,}\s*(?:Original|Replied|Forwarded)\s+Message\s*[-_=]*$',stripped,re.I)
                or re.match(r'^Begin forwarded message:',stripped,re.I)
                or stripped.startswith('>')
                or (re.match(r'^On\s',stripped,re.I) and re.search(r'\bwrote\s*:',window,re.I))
                or re.match(r'^(?:在|.+于).{0,240}(?:写道|寫道)[：:](?:\s|$)',window)
                or (re.match(r'^(?:\|\s*)?From\s*[:|]',stripped,re.I)
                    and re.search(r'(?:Sent|Date)\s*[:|]',window,re.I)
                    and re.search(r'(?:To|Subject)\s*[:|]',window,re.I)))
        if marker: break
        kept.append(line)
    # Some mail clients encode signature tables as pipe-only spacer lines.
    cleaned=[]
    for line in kept:
        if re.fullmatch(r'\s*\|[\s|]*',line):continue
        cleaned.append(line)
    return re.sub(r'\n[ \t]*\n(?:[ \t]*\n)+','\n\n','\n'.join(cleaned)).strip()


class ReplyHTML(HTMLParser):
    def __init__(self):
        super().__init__();self.text=[];self.stack=[];self.skip=0;self.stop=False
    def handle_starttag(self,tag,attrs):
        attributes=dict(attrs)
        classes=set(attributes.get('class','').lower().split())
        quoted=tag=='blockquote' or bool(classes & {'gmail_quote','gmail_attr','yahoo_quoted','protonmail_quote','moz-cite-prefix'})
        if attributes.get('id','').lower()=='divrplyfwdmsg':self.stop=True
        hidden=quoted or tag in ('script','style')
        if tag not in ('br','hr','img','meta','link','input','wbr','source','area','embed','param','track','col'):
            self.stack.append((tag,hidden));self.skip+=int(hidden)
        if not self.skip and not self.stop and tag in ('br','p','div','tr','li'):self.text.append('\n')
    def handle_endtag(self,tag):
        index=next((i for i in range(len(self.stack)-1,-1,-1) if self.stack[i][0]==tag),None)
        if index is not None:
            self.skip-=sum(int(hidden) for _,hidden in self.stack[index:]);self.stack=self.stack[:index]
    def handle_data(self,data):
        if not self.skip and not self.stop:self.text.append(data)
    def result(self):return clean_reply_text(''.join(self.text))
