import os,glob,json
root=r'C:\Users\user\Desktop\Analysis App\Exam1\saved_exams_storage'
acct='omema_at_local'
meta=os.path.join(root,acct,'admin_meta.json')
print('META_PATH=',meta)
if os.path.exists(meta):
    try:
        print('\nCURRENT admin_meta.json:\n')
        print(open(meta,'r',encoding='utf-8').read())
    except Exception as e:
        print('ERROR reading meta:',e)
else:
    print('\nadmin_meta.json missing')

# List backups
backups=glob.glob(os.path.join(root,acct,'admin_meta.backup_*.json'))
print('\nBACKUPS found:',len(backups))
for b in sorted(backups):
    print(' -',b)

# Show last backup content if any
if backups:
    b=sorted(backups)[-1]
    print('\nLAST BACKUP CONTENT:\n')
    try:
        print(open(b,'r',encoding='utf-8').read())
    except Exception as e:
        print('ERR',e)

# Show last lines of debug log
log=os.path.join(root,'debug_profile_saves.log')
print('\nDEBUG LOG PATH=',log)
if os.path.exists(log):
    try:
        lines=open(log,'r',encoding='utf-8').read().splitlines()
        print('\nLAST 20 LOG ENTRIES:')
        for L in lines[-20:]:
            print(L)
    except Exception as e:
        print('ERR reading log',e)
else:
    print('\nNo debug log found')
