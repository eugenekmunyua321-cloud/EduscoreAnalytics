from modules import storage
import json, os
sid = 'omema_at_local'
updates = {
    'phone': '+254700000000',
    'school_name': 'Omema Academy',
    'location': 'Nairobi',
    'country': 'Kenya',
    'email': 'contact@omema.ac.ke'
}
ok, err = storage.write_admin_meta(sid, updates, backup=True)
print('OK', ok, 'ERR', err)
root = os.path.join(os.path.dirname(__file__), 'saved_exams_storage')
meta_path = os.path.join(root, sid, 'admin_meta.json')
print('META PATH:', meta_path)
if os.path.exists(meta_path):
    print(open(meta_path,'r',encoding='utf-8').read())
else:
    print('admin_meta.json missing')
# list backups
bdir = os.path.join(root, sid)
backups = [f for f in os.listdir(bdir) if f.startswith('admin_meta.backup_')]
print('BACKUPS:', backups)
# show debug log last line
log = os.path.join(root, 'debug_profile_saves.log')
if os.path.exists(log):
    with open(log,'r',encoding='utf-8') as lf:
        lines = lf.read().splitlines()
    print('LAST LOG:', lines[-1])
else:
    print('No global debug log')
