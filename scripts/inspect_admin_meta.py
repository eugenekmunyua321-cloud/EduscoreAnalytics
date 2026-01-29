import os,json
root = r'C:\Users\user\Desktop\Analysis App\Exam1\saved_exams_storage'
print('ROOT=' + root)
accounts = [d for d in os.listdir(root) if os.path.isdir(os.path.join(root,d)) and d.endswith('_at_local')]
print('ACCOUNTS:', accounts)
for d in accounts:
    p = os.path.join(root, d, 'admin_meta.json')
    print('\n---', d)
    if not os.path.exists(p):
        print('MISSING admin_meta.json')
        continue
    try:
        with open(p, 'r', encoding='utf-8') as fh:
            txt = fh.read()
        print(txt)
    except Exception as e:
        print('ERROR reading file:', e)
