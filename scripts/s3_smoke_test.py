"""Simple smoke test to list objects and upload a small test object to S3 using modules.storage_s3.
Prints object list before and after upload.
"""
import sys
from modules import storage

try:
    # storage adapter will initialize S3 when configured
    storage.write_bytes('smoke_test/init_check.txt', b'init', content_type='text/plain')
except Exception as e:
    print('Storage adapter init/availability check failed:', e)
    sys.exit(2)

print('Listing objects before upload:')
objs = storage.list_objects('')
for o in objs:
    print(o)

key = 'smoke_test/agent_upload_test.txt'
print('\nUploading test object to', key)
ok = storage.write_bytes(key, b'hello from smoke test', content_type='text/plain')
print('Upload ok?', ok)

print('\nListing objects after upload:')
objs = storage.list_objects('')
for o in objs:
    print(o)

print('\nDone')
