import os, json
try:
    from modules import storage
except Exception:
    storage = None

def list_accounts():
    # If adapter provides a local dir, use it; otherwise list top-level S3 prefixes
    try:
        base = storage.get_storage_dir() if storage is not None else r'C:\Users\user\Desktop\Analysis App\Exam1\saved_exams_storage'
    except Exception:
        base = r'C:\Users\user\Desktop\Analysis App\Exam1\saved_exams_storage'
    if os.path.exists(base):
        return [d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d)) and d.endswith('_at_local')]
    # S3 listing
    try:
        objs = storage.list_objects('') if storage is not None else []
        tops = sorted({o.split('/')[0] for o in objs if '/' in o})
        return [d for d in tops if d.endswith('_at_local')]
    except Exception:
        return []

root = storage.get_storage_dir() if storage is not None else r'C:\Users\user\Desktop\Analysis App\Exam1\saved_exams_storage'
print('ROOT=' + str(root))
accounts = list_accounts()
print('ACCOUNTS:', accounts)
for d in accounts:
    print('\n---', d)
    try:
        # try adapter read first
        meta = None
        try:
            if storage is not None:
                meta = storage.read_json(os.path.join(d, 'admin_meta.json'))
        except Exception:
            meta = None
        if meta is None:
            p = os.path.join(root, d, 'admin_meta.json')
            if not os.path.exists(p):
                print('MISSING admin_meta.json')
                continue
            try:
                with open(p, 'r', encoding='utf-8') as fh:
                    txt = fh.read()
                print(txt)
                continue
            except Exception as e:
                print('ERROR reading file:', e)
        else:
            print(json.dumps(meta, indent=2))
    except Exception as e:
        print('ERROR:', e)
