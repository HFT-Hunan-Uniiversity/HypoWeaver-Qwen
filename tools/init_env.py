"""Create local deployment credentials without copying the author's secrets."""
from pathlib import Path
import secrets

ROOT = Path(__file__).resolve().parents[1]

def main():
    target = ROOT / '.env'
    if target.exists():
        raise SystemExit('.env already exists; it was not changed.')
    text = (ROOT / '.env.example').read_text(encoding='utf-8')
    keys = {'HYPOWEAVER_API_TOKEN', 'RESEARCH_ENGINE_TOKEN', 'KNOWLEDGE_SERVICE_TOKEN', 'HYPOWEAVER_SEAL_SECRET'}
    lines=[]
    for line in text.splitlines():
        key=line.partition('=')[0]
        lines.append(key+'='+secrets.token_urlsafe(36) if key in keys else line)
    with target.open('x', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines)+'\n')
    print('Created local .env. Credentials are not printed. Add your own Bailian key if using online Qwen.')

if __name__ == '__main__':
    main()
