"""只替換 Netlify 站上指定檔案（digest 法）。用法：python3 netlify_swap.py [--go] 本機路徑:站上路徑 ..."""
import json, sys, hashlib, time, urllib.request, os
SITE = '［待填：Netlify site ID］'
SRC = os.path.expanduser('~/Desktop/講座報名網站_上線用')

def find_token(o):
    if isinstance(o, dict):
        if 'token' in o and isinstance(o['token'], str) and len(o['token']) > 20: return o['token']
        for v in o.values():
            t = find_token(v)
            if t: return t
    return None
TOKEN = find_token(json.load(open(os.path.expanduser('~/Library/Preferences/netlify/config.json'))))

def api(method, path, body=None, raw=None, ctype='application/json'):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request('https://api.netlify.com/api/v1' + path, data=data, method=method,
                                 headers={'Authorization': 'Bearer ' + TOKEN, 'Content-Type': ctype})
    with urllib.request.urlopen(req, timeout=120) as r:
        t = r.read()
        return json.loads(t) if t else None

def sha1(p): return hashlib.sha1(open(p, 'rb').read()).hexdigest()

go = '--go' in sys.argv
pairs = [a.split(':', 1) for a in sys.argv[1:] if not a.startswith('--')]
live = api('GET', f'/sites/{SITE}/files')
files = {x['path']: x['sha'] for x in live}
print('線上檔案數', len(files))
# _redirects 不會出現在 listSiteFiles，必須手動帶上，否則 /free /prep 會掉
files['/_redirects'] = sha1(os.path.join(SRC, '_redirects'))
changes = {}
for local, site_path in pairs:
    new = sha1(local)
    old = files.get(site_path)
    print(f'{site_path}: 線上 {old} → 新 {new}')
    files[site_path] = new
    changes[site_path] = (local, new)
if not go:
    print('（預演，未部署；加 --go 才上線）'); sys.exit()
d = api('POST', f'/sites/{SITE}/deploys', {'files': files, 'async': False})
did, req = d['id'], d.get('required', [])
print('deploy', did, 'required', req)
expect = {v[1] for v in changes.values()}
extra = set(req) - expect - {files['/_redirects']}
assert not extra, f'required 出現非預期檔案：{extra}'
for site_path, (local, sha) in changes.items():
    if sha in req:
        api('PUT', f'/deploys/{did}/files{site_path}', raw=open(local, 'rb').read(), ctype='application/octet-stream')
        print('上傳', site_path)
if files['/_redirects'] in req:
    api('PUT', f'/deploys/{did}/files/_redirects', raw=open(os.path.join(SRC, '_redirects'), 'rb').read(), ctype='application/octet-stream')
    print('上傳 /_redirects')
for _ in range(60):
    st = api('GET', f'/deploys/{did}')['state']
    if st in ('ready', 'error'): break
    time.sleep(3)
print('狀態', st)
after = {x['path']: x['sha'] for x in api('GET', f'/sites/{SITE}/files')}
before = {x['path']: x['sha'] for x in live}
print('sha 有變動：', [p for p in after if before.get(p) != after[p]], '消失：', [p for p in before if p not in after])
