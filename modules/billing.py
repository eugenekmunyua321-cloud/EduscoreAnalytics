import json
import os
from pathlib import Path
import time
from typing import Optional, Tuple

ROOT = Path(__file__).parent.parent / 'saved_exams_storage'
ROOT.mkdir(parents=True, exist_ok=True)

GLOBAL_BILLING_FILE = ROOT / 'billing_config.json'


def _read_json(path: Path, default):
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding='utf-8') or '{}')
    except Exception:
        return default


def _write_json(path: Path, data) -> bool:
    try:
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
        tmp.replace(path)
        return True
    except Exception:
        return False


def get_global_billing_config() -> dict:
    return _read_json(GLOBAL_BILLING_FILE, {})


def set_global_billing_config(cfg: dict) -> bool:
    return _write_json(GLOBAL_BILLING_FILE, cfg or {})


def get_account_billing(storage_dir: Optional[str] = None) -> dict:
    try:
        if storage_dir:
            p = Path(storage_dir)
        else:
            p = ROOT
        p.mkdir(parents=True, exist_ok=True)
        acct_file = p / 'billing.json'
        return _read_json(acct_file, {})
    except Exception:
        return {}


def set_account_billing(acct: dict, storage_dir: Optional[str] = None) -> bool:
    try:
        if storage_dir:
            p = Path(storage_dir)
        else:
            p = ROOT
        p.mkdir(parents=True, exist_ok=True)
        acct_file = p / 'billing.json'
        return _write_json(acct_file, acct or {})
    except Exception:
        return False


def record_payment_confirmation(txn: str, payer_phone: str, amount: float, storage_dir: Optional[str] = None) -> Tuple[bool, str]:
    """Record a confirmed payment and update account expiry accordingly.

    storage_dir: path to the account folder (if None, use global ROOT)
    """
    try:
        if storage_dir:
            p = Path(storage_dir)
        else:
            p = ROOT
        p.mkdir(parents=True, exist_ok=True)

        # Append purchase record
        purch_file = p / 'purchases.json'
        try:
            items = json.loads(purch_file.read_text(encoding='utf-8') or '[]') if purch_file.exists() else []
        except Exception:
            items = []
        rec = {'time': int(time.time()), 'txn': str(txn), 'phone': str(payer_phone), 'amount': float(amount)}
        items.append(rec)
        try:
            purch_file.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding='utf-8')
        except Exception:
            pass

        # Update account billing expiry
        acct = get_account_billing(str(p)) or {}
        gcfg = get_global_billing_config() or {}
        period_days = acct.get('period_days') or gcfg.get('period_days') or 30
        try:
            period_days = int(period_days)
        except Exception:
            period_days = 30

        now = int(time.time())
        current_expiry = int(acct.get('expiry_ts') or 0)
        # If current expiry in future, extend; else start from now
        base = current_expiry if current_expiry and current_expiry > now else now
        new_expiry = base + period_days * 86400
        acct['expiry_ts'] = int(new_expiry)
        acct['last_payment_amount'] = float(amount)
        acct['period_days'] = int(period_days)

        if not set_account_billing(acct, str(p)):
            return False, 'Failed to save account billing'

        return True, ''
    except Exception as e:
        return False, str(e)


def seconds_until_expiry(storage_dir: Optional[str] = None) -> int:
    try:
        acct = get_account_billing(storage_dir)
        expiry = int(acct.get('expiry_ts') or 0)
        return max(0, expiry - int(time.time()))
    except Exception:
        return 0


def human_readable_remaining(storage_dir: Optional[str] = None) -> str:
    try:
        secs = seconds_until_expiry(storage_dir)
        if secs <= 0:
            return 'Expired or not active'
        days = secs // 86400
        if days >= 365:
            yrs = days // 365
            return f'{yrs} year(s)'
        if days >= 30:
            months = days // 30
            return f'{months} month(s) ({days} days)'
        return f'{days} day(s) ({secs} seconds)'
    except Exception:
        return 'Not available'
