import os
import json
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

try:
    from sqlalchemy import create_engine, Table, Column, Integer, String, MetaData, LargeBinary, Text
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.sql import select
except Exception:
    create_engine = None


_engine = None
_metadata = None
_tables = {}


def init_from_env(db_url: Optional[str] = None) -> bool:
    """Initialize DB connection from environment or provided URL.
    Returns True if engine available.
    """
    global _engine, _metadata, _tables
    if create_engine is None:
        return False
    url = db_url or os.environ.get('RENDER_DATABASE_URL') or os.environ.get('DATABASE_URL')
    if not url:
        return False
    try:
        _engine = create_engine(url, connect_args={})
        _metadata = MetaData()

        # Define tables
        exams = Table('exams_metadata', _metadata,
                      Column('exam_id', String, primary_key=True),
                      Column('school_id', String, index=True),
                      Column('metadata', JSONB))

        files = Table('exam_files', _metadata,
                      Column('id', Integer, primary_key=True, autoincrement=True),
                      Column('exam_id', String, index=True),
                      Column('school_id', String, index=True),
                      Column('filename', String),
                      Column('data', LargeBinary),
                      Column('mimetype', String),
                      Column('created_at', String))

        kv = Table('kv_store', _metadata,
                   Column('key', String, primary_key=True),
                   Column('value', JSONB))

        _tables = {'exams': exams, 'files': files, 'kv': kv}

        # create tables if missing
        _metadata.create_all(_engine)
        return True
    except Exception:
        _engine = None
        return False


def enabled() -> bool:
    return _engine is not None


def save_exam_metadata(school_id: str, exam_id: str, metadata: Dict[str, Any]) -> bool:
    """Upsert exam metadata for an exam_id and school_id."""
    if not enabled():
        return False
    try:
        tbl = _tables['exams']
        conn = _engine.connect()
        stmt = select([tbl.c.exam_id]).where(tbl.c.exam_id == exam_id)
        res = conn.execute(stmt).fetchone()
        payload = dict(metadata)
        payload['saved_at'] = datetime.utcnow().isoformat()
        if res:
            upd = tbl.update().where(tbl.c.exam_id == exam_id).values(metadata=payload, school_id=school_id)
            conn.execute(upd)
        else:
            ins = tbl.insert().values(exam_id=exam_id, school_id=school_id, metadata=payload)
            conn.execute(ins)
        conn.close()
        return True
    except Exception:
        return False


def list_exams(school_id: Optional[str] = None) -> List[Dict[str, Any]]:
    if not enabled():
        return []
    try:
        tbl = _tables['exams']
        conn = _engine.connect()
        if school_id:
            stmt = select([tbl]).where(tbl.c.school_id == school_id)
        else:
            stmt = select([tbl])
        res = conn.execute(stmt).fetchall()
        out = []
        for r in res:
            out.append({'exam_id': r['exam_id'], 'school_id': r['school_id'], 'metadata': r['metadata']})
        conn.close()
        return out
    except Exception:
        return []


def get_exam_metadata(exam_id: str) -> Optional[Dict[str, Any]]:
    if not enabled():
        return None
    try:
        tbl = _tables['exams']
        conn = _engine.connect()
        stmt = select([tbl.c.metadata]).where(tbl.c.exam_id == exam_id)
        res = conn.execute(stmt).fetchone()
        conn.close()
        return res[0] if res else None
    except Exception:
        return None


def save_exam_file(school_id: str, exam_id: str, filename: str, data: bytes, mimetype: str = '') -> bool:
    if not enabled():
        return False
    try:
        tbl = _tables['files']
        conn = _engine.connect()
        ins = tbl.insert().values(exam_id=exam_id, school_id=school_id, filename=filename, data=data, mimetype=mimetype, created_at=datetime.utcnow().isoformat())
        conn.execute(ins)
        conn.close()
        return True
    except Exception:
        return False


def get_exam_files(exam_id: str) -> List[Tuple[str, bytes, str]]:
    """Return list of (filename, data, mimetype) for an exam."""
    if not enabled():
        return []
    try:
        tbl = _tables['files']
        conn = _engine.connect()
        stmt = select([tbl.c.filename, tbl.c.data, tbl.c.mimetype]).where(tbl.c.exam_id == exam_id)
        res = conn.execute(stmt).fetchall()
        conn.close()
        out = []
        for r in res:
            out.append((r['filename'], r['data'], r['mimetype']))
        return out
    except Exception:
        return []


def set_kv(key: str, value: Any) -> bool:
    if not enabled():
        return False
    try:
        tbl = _tables['kv']
        conn = _engine.connect()
        stmt = select([tbl.c.key]).where(tbl.c.key == key)
        res = conn.execute(stmt).fetchone()
        payload = value
        if res:
            upd = tbl.update().where(tbl.c.key == key).values(value=payload)
            conn.execute(upd)
        else:
            ins = tbl.insert().values(key=key, value=payload)
            conn.execute(ins)
        conn.close()
        return True
    except Exception:
        return False


def get_kv(key: str) -> Any:
    if not enabled():
        return None
    try:
        tbl = _tables['kv']
        conn = _engine.connect()
        stmt = select([tbl.c.value]).where(tbl.c.key == key)
        res = conn.execute(stmt).fetchone()
        conn.close()
        return res[0] if res else None
    except Exception:
        return None
