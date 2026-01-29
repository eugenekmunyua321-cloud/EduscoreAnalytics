import os, json, time
root = r'C:\Users\user\Desktop\Analysis App\Exam1\saved_exams_storage'
accounts = [d for d in os.listdir(root) if os.path.isdir(os.path.join(root,d)) and d.endswith('_at_local')]
print('Accounts:', accounts)
for d in accounts:
    p = os.path.join(root, d, 'admin_meta.json')
    print('\n---', d)
    am = {}
    if os.path.exists(p):
        try:
            with open(p, 'r', encoding='utf-8') as fh:
                am = json.load(fh) or {}
        except Exception as e:
            print('Read error:', e)
            am = {}
    # Determine if file is too minimal (only disabled or empty)
    keys = set(am.keys())
    if not keys or keys <= {'disabled'}:
        print('Patching admin_meta.json (was minimal or missing)')
        username = d.replace('_at_local', '')
        created = int(time.time())
        default_meta = {
            'account_number': am.get('account_number',''),
            'username': am.get('username', username),
            'email': am.get('email', f"{username}@local"),
            'phone': am.get('phone',''),
            'school_name': am.get('school_name',''),
            'location': am.get('location',''),
            'country': am.get('country',''),
            'created_at': am.get('created_at', created),
            'trial_until': am.get('trial_until', 0),
            'active': am.get('active', False),
            'disabled': bool(am.get('disabled', False))
        }
        # write atomically
        tmp = p + '.tmp'
        try:
            with open(tmp, 'w', encoding='utf-8') as fh:
                json.dump(default_meta, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, p)
            print('Wrote default admin_meta.json')
        except Exception as e:
            print('Failed to write:', e)
    else:
        print('OK (has keys):', ','.join(sorted(keys)))
print('\nDone')
