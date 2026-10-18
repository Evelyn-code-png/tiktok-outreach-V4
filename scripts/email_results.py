"""Read EasyKOL's completed XLSX export, using explicit URL/email associations."""
import io
import re
from pathlib import Path
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

import outreach as o

NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
DOWNLOAD_HOSTS = {'talent-marketing-api.aiwaifu.top'}

def parse_xml(raw):
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('Workbooks containing external entities are not supported')
    return ET.fromstring(raw)

def xlsx_rows(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if sum(f.file_size for f in z.infolist()) > 100_000_000:
            raise ValueError('The uncompressed workbook is too large')
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            for si in parse_xml(z.read('xl/sharedStrings.xml')).findall('m:si', NS):
                shared.append(''.join(t.text or '' for t in si.findall('.//m:t', NS)))
        name = 'xl/worksheets/sheet1.xml'
        if name not in z.namelist(): raise ValueError('The workbook is missing the expected worksheet')
        rows = []
        for row in parse_xml(z.read(name)).findall('.//m:sheetData/m:row', NS):
            values = {}
            for cell in row.findall('m:c', NS):
                match = re.fullmatch(r'([A-Z]+)[0-9]+', cell.get('r', ''))
                if not match: raise ValueError('The cell reference is invalid')
                col = 0
                for c in match.group(1): col = col * 26 + ord(c) - 64
                if col > 200: raise ValueError('The workbook contains too many columns')
                if cell.find('m:f', NS) is not None:
                    value = ''  # Never interpret formulas as addresses or source URLs.
                elif cell.get('t') == 'inlineStr':
                    value = ''.join(t.text or '' for t in cell.findall('.//m:t', NS))
                else:
                    v = cell.find('m:v', NS); value = v.text if v is not None else ''
                    if cell.get('t') == 's': value = shared[int(value)]
                values[col - 1] = value or ''
            rows.append(values)
            if len(rows) > 5001: raise ValueError('The workbook contains more than 5,000 rows')
        if not rows: raise ValueError('The workbook contains no data')
        headers = rows[0]
        if len(set(headers.values())) != len(headers): raise ValueError('The workbook contains duplicate column names')
        return [{header: row.get(index, '') for index, header in headers.items()} for row in rows[1:]]

def profile_key(url):
    p = urllib.parse.urlparse(str(url))
    if p.scheme != 'https' or p.hostname not in ('tiktok.com', 'www.tiktok.com'):
        return None
    match = re.fullmatch(r'/@([A-Za-z0-9_.]+)/?', p.path)
    return match.group(1).lower() if match else None

def merge_rows(original, exported):
    known = {profile_key(r.get('profile_url')) for r in original} - {None}
    by_profile = {}
    skipped = 0
    for row in exported:
        key = profile_key(row.get('URL'))
        if key not in known:
            skipped += 1; continue
        emails = sorted(set(x.lower() for x in o.EMAIL.findall(str(row.get('Email') or ''))))
        if emails: by_profile.setdefault(key, set()).update(emails)
    output = []
    for row in original:
        addresses = by_profile.get(profile_key(row.get('profile_url')), set())
        existing = set(o.EMAIL.findall(row.get('email') or ''))
        for email in sorted(addresses | existing) or ['']:
            item = dict(row, email=email)
            if email in addresses: item['source'] = 'EasyKOL email lookup'
            output.append(item)
    return o.normalize(output), skipped

def collect(args):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.task_id): raise ValueError('The task ID is invalid')
    result = o.api('/kol-emails/' + args.task_id)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    o.save_json(out / 'task-result.json', result)
    status = result.get('status')
    if status != 'COMPLETED': return {'status': status, 'task_id': args.task_id}
    url = result.get('downloadUrl', '')
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in DOWNLOAD_HOSTS or parsed.port not in (None, 443) or parsed.username or parsed.password:
        raise ValueError('The email export URL is outside the verified provider domain. The response was saved for review.')
    with urllib.request.build_opener(o.NoRedirect).open(url, timeout=45) as response:
        data = response.read(10_000_001)
    if len(data) > 10_000_000: raise ValueError('The downloaded file exceeds 10 MB')
    p = out / 'emails.xlsx'; p.write_bytes(data); p.chmod(0o600)
    exported = xlsx_rows(data)
    if exported and ('URL' not in exported[0] or 'Email' not in exported[0]):
        raise ValueError('The email export columns changed. The raw file was saved, and automatic merging was stopped.')
    merged, skipped = merge_rows(o.csv_read(args.csv), exported)
    o.csv_write(out / 'creators.csv', merged)
    return {'status': status, 'task_id': args.task_id, 'csv': str(out / 'creators.csv'),
            'rows': len(merged), 'with_email': sum(bool(r['email']) for r in merged), 'unmatched_export_rows': skipped}
