import os
from pathlib import Path
try:
    from . import auth
except Exception:
    auth = None

BASE_STORAGE = os.path.join(os.path.dirname(__file__), '..', 'saved_exams_storage')

def get_storage_dir():
    """Return the storage directory for the current signed-in school (if any),
    otherwise return the shared saved_exams_storage path. Creates the directory if missing.
    """
    try:
        if auth is not None:
            sid = auth.get_current_school_id()
            if sid:
                path = os.path.join(os.path.dirname(__file__), '..', 'saved_exams_storage', sid)
                os.makedirs(path, exist_ok=True)
                return path
    except Exception:
        pass
    path = os.path.join(os.path.dirname(__file__), '..', 'saved_exams_storage')
    os.makedirs(path, exist_ok=True)
    return path


def initialize_account(school_id: str):
    """Create a fresh per-school storage folder with empty datasets and
    prefilled messaging configuration copied from the global config (if present).

    This is called when a new local account is created so each account starts
    with no exams, no photos, no contacts, and no message history. The only
    thing copied into new accounts is the messaging provider info (messaging_config.json)
    so schools can send messages if they configure credentials.
    """
    try:
        if not school_id:
            return False
        root = os.path.join(os.path.dirname(__file__), '..', 'saved_exams_storage')
        acct_dir = os.path.join(root, school_id)
        os.makedirs(acct_dir, exist_ok=True)

        # Helper to write file if missing
        def write_if_missing(fname, data):
            p = os.path.join(acct_dir, fname)
            if os.path.exists(p):
                return
            try:
                import json
                with open(p, 'w', encoding='utf-8') as fh:
                    json.dump(data, fh, indent=2, ensure_ascii=False)
            except Exception:
                pass

        # Create empty containers
        write_if_missing('exams_metadata.json', {})
        write_if_missing('student_contacts.json', [])
        write_if_missing('student_photos.json', {})
        write_if_missing('sent_messages_log.json', [])
        write_if_missing('purchases.json', {})
        write_if_missing('ta_teachers.json', {})
        write_if_missing('teacher_assignments.json', {})
        write_if_missing('ta_assignments.json', {})
        write_if_missing('ta_assignments_simple.json', {})
        write_if_missing('ta_class_map.json', {})
        write_if_missing('ta_selected_exams.json', {})
        write_if_missing('ta_settings.json', {})
        write_if_missing('report_card_settings.json', {})

        # Create a per-account app config with empty school/class/exam names so new accounts start blank
        acct_app_cfg = os.path.join(acct_dir, 'app_persistent_config.json')
        if not os.path.exists(acct_app_cfg):
            try:
                import json
                acct_cfg = {
                    "school_name": "",
                    "class_name": "",
                    "exam_name": "",
                    "font_family": "Poppins",
                    "font_size": 14,
                    "font_weight": "normal",
                    "font_color": "#111111",
                    "primary_color": "#0E6BA8",
                    "apply_to": ["whole_app"],
                    "input_mode": "paste",
                    "combined_subjects": {},
                    "grading_enabled": False,
                    "grading_system": [
                        {"grade": "A", "min": 80, "max": 100},
                        {"grade": "B", "min": 70, "max": 79},
                        {"grade": "C", "min": 60, "max": 69},
                        {"grade": "D", "min": 50, "max": 59},
                        {"grade": "E", "min": 0, "max": 49}
                    ]
                }
                with open(acct_app_cfg, 'w', encoding='utf-8') as fh:
                    json.dump(acct_cfg, fh, indent=2, ensure_ascii=False)
            except Exception:
                pass

        # Ensure student_photos dir exists but empty
        photos_dir = os.path.join(acct_dir, 'student_photos')
        os.makedirs(photos_dir, exist_ok=True)

        # Create a default admin_meta.json so admin features don't accidentally
        # create a minimal file later which would wipe user-provided profile data.
        def write_admin_meta_default():
            try:
                import json, time
                adm = os.path.join(acct_dir, 'admin_meta.json')
                if os.path.exists(adm):
                    return
                username = (school_id or '').replace('_at_', '')
                created = int(time.time())
                default_meta = {
                    'account_number': '',
                    'username': username,
                    'email': f"{username}@local" if username else '',
                    'phone': '',
                    'school_name': '',
                    'location': '',
                    'country': '',
                    'created_at': created,
                    'trial_until': 0,
                    'active': False,
                    'disabled': False
                }
                with open(adm, 'w', encoding='utf-8') as fh:
                    json.dump(default_meta, fh, indent=2, ensure_ascii=False)
            except Exception:
                pass

        try:
            write_admin_meta_default()
        except Exception:
            pass

        # Copy messaging_config.json from global storage if present, else create a minimal default
        global_msg = os.path.join(root, 'messaging_config.json')
        acct_msg = os.path.join(acct_dir, 'messaging_config.json')
        if os.path.exists(global_msg) and not os.path.exists(acct_msg):
            try:
                import shutil
                shutil.copyfile(global_msg, acct_msg)
            except Exception:
                pass
        else:
            # minimal default: Africa's Talking (the project uses AT credentials)
            write_if_missing('messaging_config.json', {
                'provider': 'africastalking',
                'api_url': 'https://api.africastalking.com/version1/messaging',
                'username': '',
                'api_key': '',
                'password': '',
                'sender': '',
                'http_method': 'POST',
                'content_type': 'application/x-www-form-urlencoded',
                'extra_params': {}
            })

        return True
    except Exception:
        return False


def write_admin_meta(school_id: str, updates: dict, backup: bool = True, force_replace: bool = False):
    """Merge `updates` into the existing admin_meta.json for `school_id` and write atomically.
    Returns (True, None) on success or (False, error_message) on failure.
    Creates an optional timestamped backup and returns an error message on failure.
    """
    try:
        if not school_id:
            return False, 'school_id required'
        root = os.path.join(os.path.dirname(__file__), '..', 'saved_exams_storage')
        acct_dir = os.path.join(root, school_id)
        os.makedirs(acct_dir, exist_ok=True)
        adm_path = os.path.join(acct_dir, 'admin_meta.json')
        cur = {}
        try:
            if os.path.exists(adm_path):
                import json
                with open(adm_path, 'r', encoding='utf-8') as fh:
                    cur = json.load(fh) or {}
        except Exception:
            cur = {}

        # Determine the object to write.
        # By default we merge updates into current meta so unrelated fields are preserved.
        # If force_replace=True we will replace the writable fields with `updates` while
        # preserving a small set of system keys (account_number, username, created_at, trial_until, active, disabled).
        if force_replace:
            preserved = ['account_number', 'username', 'created_at', 'trial_until', 'active', 'disabled']
            merged = dict((updates or {}))
            # restore preserved system keys from current meta when not provided in updates
            for k in preserved:
                if k in cur and k not in merged:
                    merged[k] = cur.get(k)
        else:
            # Merge updates into current meta, but do not allow empty-string updates to
            # overwrite existing non-empty values. This prevents background processes
            # from wiping user-provided profile fields with default empty strings.
            merged = dict(cur)
            skipped = {}
            for k, v in (updates or {}).items():
                try:
                    # If incoming value is a string and empty, and current has a non-empty value,
                    # skip overwriting unless caller explicitly provided None.
                    if isinstance(v, str) and v.strip() == '' and k in cur and cur.get(k) not in (None, ''):
                        skipped[k] = {'existing': cur.get(k), 'skipped_update': v}
                        continue
                except Exception:
                    pass
                merged[k] = v

        # Write atomically
        try:
            import json, time
            tmp = adm_path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as fh:
                json.dump(merged, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, adm_path)
        except Exception as e:
            try:
                with open(adm_path, 'w', encoding='utf-8') as fh:
                    import json
                    json.dump(merged, fh, indent=2, ensure_ascii=False)
            except Exception as e2:
                return False, f'Failed to write admin_meta: {e2}'

        # Optional backup for inspection
        created_backup = None
        if backup:
            try:
                import json, time
                ts = int(time.time())
                bpath = os.path.join(acct_dir, f'admin_meta.backup_{ts}.json')
                with open(bpath, 'w', encoding='utf-8') as bf:
                    json.dump({'saved': ts, 'meta': merged}, bf, indent=2, ensure_ascii=False)
                created_backup = bpath
            except Exception:
                created_backup = None

        # If force_replace was requested, delete other previous backups and raw submission snapshots
        if force_replace:
            try:
                import glob
                # remove other admin_meta.backup_*.json files except the one we just created
                pattern = os.path.join(acct_dir, 'admin_meta.backup_*.json')
                for p in glob.glob(pattern):
                    try:
                        if created_backup and os.path.abspath(p) == os.path.abspath(created_backup):
                            continue
                        os.remove(p)
                    except Exception:
                        pass
                # remove any raw submission snapshots
                rawpat = os.path.join(acct_dir, 'admin_meta.submission_raw_*.json')
                for p in glob.glob(rawpat):
                    try:
                        os.remove(p)
                    except Exception:
                        pass
            except Exception:
                pass

        # If this write was authoritative (force_replace), also persist a last-good copy
        # that we'll use to detect and repair out-of-band changes.
        if force_replace:
            try:
                import json, time
                lg = os.path.join(acct_dir, 'admin_meta.last_good.json')
                tmp_lg = lg + '.tmp'
                with open(tmp_lg, 'w', encoding='utf-8') as fh:
                    json.dump({'saved': int(time.time()), 'meta': merged}, fh, indent=2, ensure_ascii=False)
                os.replace(tmp_lg, lg)
            except Exception:
                pass

        # append debug global log entry with some details about changes and skipped keys
        try:
            import json, time
            logp = os.path.join(root, 'debug_profile_saves.log')
            entry = {'time': int(time.time()), 'school_id': school_id, 'keys': list((updates or {}).keys()), 'force_replace': bool(force_replace)}
            # include skipped keys info if any
            if not force_replace and 'skipped' in locals() and skipped:
                entry['skipped'] = skipped
            # include a simple before/after diff sample
            try:
                diff = {}
                for k in (updates or {}).keys():
                    diff[k] = {'before': cur.get(k), 'after': merged.get(k)}
                entry['diff'] = diff
            except Exception:
                pass
            with open(logp, 'a', encoding='utf-8') as lf:
                lf.write(json.dumps(entry, ensure_ascii=False) + '\n')
        except Exception:
            pass

        return True, None
    except Exception as e:
        return False, str(e)


def restore_if_tampered(school_id: str):
    """If the admin_meta.json file was changed after the last authoritative save,
    restore the last-good copy (admin_meta.last_good.json). Returns (True, message)
    if a restoration was performed, or (False, reason) otherwise.
    """
    try:
        if not school_id:
            return False, 'school_id required'
        root = os.path.join(os.path.dirname(__file__), '..', 'saved_exams_storage')
        acct_dir = os.path.join(root, school_id)
        adm = os.path.join(acct_dir, 'admin_meta.json')
        lg = os.path.join(acct_dir, 'admin_meta.last_good.json')
        if not os.path.exists(lg) or not os.path.exists(adm):
            return False, 'no last-good or admin_meta missing'
        try:
            import json
            with open(lg, 'r', encoding='utf-8') as f:
                lg_obj = json.load(f) or {}
            lg_meta = lg_obj.get('meta') if isinstance(lg_obj, dict) else lg_obj
        except Exception:
            return False, 'failed to read last-good'
        try:
            with open(adm, 'r', encoding='utf-8') as f:
                adm_meta = json.load(f) or {}
        except Exception:
            adm_meta = {}
        # If they match, nothing to do
        if adm_meta == lg_meta:
            return False, 'no change'
        # Otherwise, restore the last-good copy atomically
        try:
            import json, time
            tmp = adm + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as fh:
                json.dump(lg_meta, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, adm)
            # log the restoration to diagnostics
            diag = os.path.join(root, 'profile_save_diagnostics.jsonl')
            entry = {'time': int(time.time()), 'acct': school_id, 'action': 'restored_last_good', 'note': 'admin_meta replaced by non-authoritative writer; restored last-good copy.'}
            try:
                with open(diag, 'a', encoding='utf-8') as df:
                    df.write(json.dumps(entry, ensure_ascii=False) + '\n')
            except Exception:
                pass
            # also append to debug log
            try:
                logp = os.path.join(root, 'debug_profile_saves.log')
                with open(logp, 'a', encoding='utf-8') as lf:
                    lf.write(json.dumps({'time': int(time.time()), 'school_id': school_id, 'action': 'restored_last_good'}, ensure_ascii=False) + '\n')
            except Exception:
                pass
            return True, 'restored'
        except Exception as e:
            return False, f'restore failed: {e}'
    except Exception as e:
        return False, str(e)


def ensure_last_good(school_id: str):
    """Ensure that a last-good file exists for the given account by copying the
    current admin_meta.json into admin_meta.last_good.json if the latter is missing.
    Returns (True, message) if created or already exists, (False, reason) otherwise.
    """
    try:
        if not school_id:
            return False, 'school_id required'
        root = os.path.join(os.path.dirname(__file__), '..', 'saved_exams_storage')
        acct_dir = os.path.join(root, school_id)
        adm = os.path.join(acct_dir, 'admin_meta.json')
        lg = os.path.join(acct_dir, 'admin_meta.last_good.json')
        if not os.path.exists(adm):
            return False, 'admin_meta missing'
        if os.path.exists(lg):
            return True, 'already'
        try:
            import json, time
            with open(adm, 'r', encoding='utf-8') as f:
                adm_meta = json.load(f) or {}
            tmp = lg + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as fh:
                json.dump({'saved': int(time.time()), 'meta': adm_meta}, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, lg)
            return True, 'created'
        except Exception as e:
            return False, f'failed: {e}'
    except Exception as e:
        return False, str(e)
