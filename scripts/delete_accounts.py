import shutil
from pathlib import Path
import time

ROOT = Path(__file__).parent.parent / 'saved_exams_storage'
BACKUP = ROOT.parent / f"saved_exams_storage_deleted_backup_{int(time.time())}"
BACKUP.mkdir(parents=True, exist_ok=True)

TO_DELETE = [
    'eugenekmunyua321_at_gmail_com',
    'guest_at_local',
    'jim_at_local',
    'johnjoe3646_at_gmail_com',
    'kamau_at_local',
    'mark_at_local',
    'mercy_at_local',
    'mercymorry2_at_gmail_com',
    'munyua_at_local',
]

results = []
for name in TO_DELETE:
    src = ROOT / name
    if not src.exists():
        results.append((name, 'missing'))
        continue
    dst = BACKUP / name
    try:
        shutil.copytree(src, dst)
        shutil.rmtree(src)
        results.append((name, 'deleted', str(dst)))
    except Exception as e:
        results.append((name, 'error', str(e)))

print('Backup+Delete results:')
for r in results:
    print(r)
print('Backup folder:', BACKUP)
