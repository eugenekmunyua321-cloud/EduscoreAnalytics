"""
Messaging utilities for sending SMS via a configurable provider (Mobitech).

This module implements a safe, configurable wrapper that supports a test-mode
so you can preview messages without actually calling the provider.

Configure credentials in `saved_exams_storage/messaging_config.json` or pass a
config dict with keys: api_url, username, password, sender, extra_params (dict).

Real HTTP requests use `requests`. Phone formatting/normalization is done by the
caller (pages/send_messages.py or pages/parent_contacts.py).
"""
import time
import json
import os
from pathlib import Path
import requests
from typing import List, Dict
try:
    import certifi
    CA_BUNDLE = certifi.where()
except Exception:
    CA_BUNDLE = True

from modules.storage import get_storage_dir
BASE = Path(get_storage_dir())
BASE.mkdir(parents=True, exist_ok=True)
# Keep per-account logs, but use a global messaging config so all accounts share the
# same SMS provider credentials (so every school uses the same Africa's Talking account).
LOG_FILE = BASE / 'sent_messages_log.json'
GLOBAL_CONFIG_FILE = BASE.parent / 'messaging_config.json'
CONFIG_FILE = GLOBAL_CONFIG_FILE

def ensure_log():
    if not LOG_FILE.exists():
        LOG_FILE.write_text('[]', encoding='utf-8')

def load_config():
    if not CONFIG_FILE.exists():
        cfg = {
            'api_url': '',
            'username': '',
            'password': '',
            'api_key': '',
            'provider': 'mobitech',
            'sender': '',
            'http_method': 'POST',
            'content_type': 'application/json',
            'extra_params': {}
        }
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding='utf-8')
        return cfg
    try:
        return json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
    except Exception:
        return {}

def log_send(entry: Dict):
    ensure_log()
    try:
        data = json.loads(LOG_FILE.read_text(encoding='utf-8'))
    except Exception:
        data = []
    data.append(entry)
    LOG_FILE.write_text(json.dumps(data, indent=2), encoding='utf-8')


def _is_html_response(text: str, headers: Dict = None) -> bool:
    try:
        ct = headers.get('Content-Type', '') if headers else ''
        if 'text/html' in ct.lower():
            return True
    except Exception:
        pass
    if isinstance(text, str) and '<!DOCTYPE html' in text[:200].lower():
        return True
    return False


def send_single_africastalking(phone_e164: str, message: str, config: Dict = None, test_mode: bool = True, contact: Dict = None):
    """Send a single SMS via Africa's Talking REST API.

    Expects config to contain:
      - username
      - api_key (preferred) or password
      - api_url (optional, defaults to AT messaging endpoint)
      - sender (optional)

    Africa's Talking expects form-encoded fields: username, to, message, from (optional)
    and header 'apiKey: <key>'.
    """
    cfg = config or load_config()
    entry = {
        'phone': phone_e164,
        'message': message,
        'time': time.time(),
        'provider': 'africastalking',
        # record the exact config used (loaded from messaging_config.json or passed in)
        'config_used': cfg.copy() if isinstance(cfg, dict) else cfg,
        'status': 'TEST' if test_mode else 'SENT'
    }
    # include contact metadata if provided so audit logs are unambiguous
    if isinstance(contact, dict):
        try:
            entry['contact'] = {
                'student_name': contact.get('student_name') or contact.get('student'),
                'parent_name': contact.get('parent_name') or contact.get('parent'),
                'class': contact.get('class') or contact.get('grade') or contact.get('class_name'),
                'phone': contact.get('phone') or contact.get('phone_raw') or phone_e164
            }
        except Exception:
            pass

    payload = {
        'username': cfg.get('username', ''),
        'to': phone_e164,
        'message': message
    }
    if cfg.get('sender'):
        payload['from'] = cfg.get('sender')

    if test_mode:
        entry['response'] = {'ok': True, 'note': "test-mode, no network call made", 'payload': payload}
        log_send(entry)
        return {'ok': True, 'test_mode': True, 'entry': entry}

    url = cfg.get('api_url') or 'https://api.africastalking.com/version1/messaging'
    api_key = cfg.get('api_key') or cfg.get('password')
    # Africa's Talking expects the header 'apiKey' and typically form-encoded body
    headers = {'Accept': 'application/json'}
    content_type = (cfg.get('content_type') or '').lower()
    if content_type == 'application/x-www-form-urlencoded' or not content_type:
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
        send_as_json = False
    else:
        headers['Content-Type'] = cfg.get('content_type')
        send_as_json = (content_type == 'application/json')

    if api_key:
        headers['apiKey'] = api_key

    try:
        if send_as_json:
            r = requests.post(url, json=payload, headers=headers, timeout=30, verify=CA_BUNDLE)
        else:
            # form-encoded body
            r = requests.post(url, data=payload, headers=headers, timeout=30, verify=CA_BUNDLE)
        text = r.text
        if _is_html_response(text, r.headers):
            entry['response'] = {'status_code': r.status_code, 'text': text, 'error': 'HTML response received (likely wrong endpoint or missing auth)'}
            entry['ok'] = False
            log_send(entry)
            return {'ok': False, 'status_code': r.status_code, 'text': text}

        # attempt to parse JSON
        try:
            resp_json = r.json()
        except Exception:
            resp_json = {'text': r.text}

        entry['response'] = {'status_code': r.status_code, 'json': resp_json}
        entry['ok'] = r.ok
        log_send(entry)
        return {'ok': r.ok, 'status_code': r.status_code, 'json': resp_json}
    except Exception as e:
        entry['response'] = {'error': str(e)}
        entry['ok'] = False
        log_send(entry)
        return {'ok': False, 'error': str(e)}


def send_bulk_africastalking(contacts: List[Dict], message_template: str, config: Dict = None, test_mode: bool = True, delay_seconds: float = 0.2):
    results = []
    cfg = config or load_config()
    for c in contacts:
        phone = c.get('phone') or c.get('phone_e164') or c.get('phone_raw')
        if not phone:
            results.append({'ok': False, 'error': 'no phone', 'contact': c})
            continue
        try:
            msg = message_template.format(**c)
        except Exception:
            msg = message_template
        res = send_single_africastalking(phone, msg, config=cfg, test_mode=test_mode, contact=c)
        results.append({'contact': c, 'result': res})
        if not test_mode:
            time.sleep(delay_seconds)
    return results


def send_single(phone_e164: str, message: str, config: Dict = None, test_mode: bool = True):
    cfg = config or load_config()
    provider = (cfg.get('provider') or 'mobitech').lower()
    if provider == 'africastalking' or provider == 'at':
        return send_single_africastalking(phone_e164, message, config=cfg, test_mode=test_mode)
    # default to mobitech
    return send_single_mobitech(phone_e164, message, config=cfg, test_mode=test_mode)


def send_bulk(contacts: List[Dict], message_template: str, config: Dict = None, test_mode: bool = True, delay_seconds: float = 0.2):
    cfg = config or load_config()
    provider = (cfg.get('provider') or 'mobitech').lower()
    if provider == 'africastalking' or provider == 'at':
        return send_bulk_africastalking(contacts, message_template, config=cfg, test_mode=test_mode, delay_seconds=delay_seconds)
    return send_bulk_mobitech(contacts, message_template, config=cfg, test_mode=test_mode, delay_seconds=delay_seconds)


def send_single_infobip(phone: str, message: str, config: Dict = None, test_mode: bool = True, contact: Dict = None):
    """Send a single SMS via Infobip REST API (Authorization: App <key>)."""
    cfg = config or load_config()
    entry = {
        'phone': phone,
        'message': message,
        'time': time.time(),
        'provider': 'infobip',
        # store the active config exactly as provided by the app
        'config_used': cfg.copy() if isinstance(cfg, dict) else cfg,
        'status': 'TEST' if test_mode else 'SENT'
    }
    if isinstance(contact, dict):
        try:
            entry['contact'] = {
                'student_name': contact.get('student_name') or contact.get('student'),
                'parent_name': contact.get('parent_name') or contact.get('parent'),
                'class': contact.get('class') or contact.get('grade') or contact.get('class_name'),
                'phone': contact.get('phone') or contact.get('phone_raw') or phone
            }
        except Exception:
            pass

    payload = {
        "messages": [
            {
                "destinations": [{"to": phone.lstrip('+')}],
                "from": cfg.get('sender', ''),
                "text": message
            }
        ]
    }

    if test_mode:
        entry['response'] = {'ok': True, 'note': 'test-mode, not sent', 'payload': payload}
        log_send(entry)
        return {'ok': True, 'test_mode': True, 'entry': entry}

    url = cfg.get('api_url') or 'https://api.infobip.com/sms/2/text/advanced'
    api_key = cfg.get('api_key') or cfg.get('password')
    headers = {
        'Authorization': f'App {api_key}',
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=30, verify=CA_BUNDLE)
        try:
            resp = r.json()
        except Exception:
            resp = {'text': r.text}
        entry['response'] = {'status_code': r.status_code, 'json': resp}
        entry['ok'] = r.ok
        log_send(entry)
        return {'ok': r.ok, 'status_code': r.status_code, 'json': resp}
    except Exception as e:
        entry['response'] = {'error': str(e)}
        entry['ok'] = False
        log_send(entry)
        return {'ok': False, 'error': str(e)}


def send_bulk_infobip(contacts: List[Dict], message_template: str, config: Dict = None, test_mode: bool = True, delay_seconds: float = 0.2):
    results = []
    cfg = config or load_config()
    for c in contacts:
        phone = c.get('phone') or c.get('phone_e164') or c.get('phone_raw')
        if not phone:
            results.append({'ok': False, 'error': 'no phone', 'contact': c})
            continue
        try:
            msg = message_template.format(**c)
        except Exception:
            msg = message_template
        res = send_single_infobip(phone, msg, config=cfg, test_mode=test_mode, contact=c)
        results.append({'contact': c, 'result': res})
        if not test_mode:
            time.sleep(delay_seconds)
    return results

def send_single_mobitech(phone_e164: str, message: str, config: Dict = None, test_mode: bool = True, contact: Dict = None):
    """Send a single SMS via Mobitech (configurable endpoint).

    phone_e164 must be normalized (e.g., +2547XXXXXXXX).
    If test_mode is True, the function will not make network calls and will
    instead return a simulated response and log the attempt.
    """
    cfg = config or load_config()
    payload = {
        'to': phone_e164,
        'message': message,
        'sender': cfg.get('sender', '')
    }
    payload.update(cfg.get('extra_params', {}) or {})

    entry = {
        'phone': phone_e164,
        'message': message,
        'time': time.time(),
        'provider': 'mobitech',
        # store the active config exactly as provided by the app
        'config_used': cfg.copy() if isinstance(cfg, dict) else cfg,
        'status': 'TEST' if test_mode else 'SENT'
    }
    if isinstance(contact, dict):
        try:
            entry['contact'] = {
                'student_name': contact.get('student_name') or contact.get('student'),
                'parent_name': contact.get('parent_name') or contact.get('parent'),
                'class': contact.get('class') or contact.get('grade') or contact.get('class_name'),
                'phone': contact.get('phone') or contact.get('phone_raw') or phone_e164
            }
        except Exception:
            pass

    if test_mode:
        # Log and return a simulated response
        entry['response'] = {'ok': True, 'note': 'test-mode, no network call made', 'payload': payload}
        log_send(entry)
        return {'ok': True, 'test_mode': True, 'entry': entry}

    # Perform real HTTP call
    url = cfg.get('api_url')
    if not url:
        raise ValueError('No api_url configured in messaging config')

    headers = {}
    if cfg.get('content_type') == 'application/json':
        headers['Content-Type'] = 'application/json'

    method = (cfg.get('http_method') or 'POST').upper()

    auth = None
    if cfg.get('username') and cfg.get('password'):
        auth = (cfg.get('username'), cfg.get('password'))

    try:
        if method == 'POST':
            if headers.get('Content-Type') == 'application/json':
                r = requests.post(url, json=payload, headers=headers, auth=auth, timeout=30, verify=CA_BUNDLE)
            else:
                r = requests.post(url, data=payload, headers=headers, auth=auth, timeout=30, verify=CA_BUNDLE)
        else:
            r = requests.get(url, params=payload, headers=headers, auth=auth, timeout=30, verify=CA_BUNDLE)

        entry['response'] = {'status_code': r.status_code, 'text': r.text}
        entry['ok'] = r.ok
        log_send(entry)
        return {'ok': r.ok, 'status_code': r.status_code, 'text': r.text}
    except Exception as e:
        entry['response'] = {'error': str(e)}
        entry['ok'] = False
        log_send(entry)
        return {'ok': False, 'error': str(e)}

def send_bulk_mobitech(contacts: List[Dict], message_template: str, config: Dict = None, test_mode: bool = True, delay_seconds: float = 0.2):
    """Send messages to multiple contacts.

    contacts: list of dicts with at least 'phone' and optionally other fields.
    message_template: may contain placeholders like {student_name}.
    test_mode: if True, no network calls will be made.
    Returns list of results for each contact.
    """
    results = []
    cfg = config or load_config()
    for c in contacts:
        phone = c.get('phone') or c.get('phone_e164') or c.get('phone_raw')
        if not phone:
            results.append({'ok': False, 'error': 'no phone', 'contact': c})
            continue
        try:
            msg = message_template.format(**c)
        except Exception:
            # fall back to raw message
            msg = message_template
        res = send_single_mobitech(phone, msg, config=cfg, test_mode=test_mode, contact=c)
        results.append({'contact': c, 'result': res})
        if not test_mode:
            time.sleep(delay_seconds)
    return results
