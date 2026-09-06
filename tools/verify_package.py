"""Verify distributed files using the package's SHA-256 inventory (stdlib only)."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]

def file_hash(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024), b''):
            h.update(b)
    return h.hexdigest()

def main():
    manifest=json.loads((ROOT/'PACKAGE_MANIFEST.json').read_text(encoding='utf-8'))
    problems=[]
    for entry in manifest['files']:
        p=(ROOT/entry['path']).resolve()
        if ROOT not in p.parents:
            problems.append({'path':entry['path'], 'reason':'invalid path'})
        elif not p.is_file():
            problems.append({'path':entry['path'], 'reason':'missing'})
        elif file_hash(p)!=entry['sha256']:
            problems.append({'path':entry['path'], 'reason':'hash mismatch'})
    print(json.dumps({'checked_files':len(manifest['files']), 'passed':not problems, 'problems':problems}, ensure_ascii=False, indent=2))
    return bool(problems)

if __name__=='__main__':
    raise SystemExit(main())
