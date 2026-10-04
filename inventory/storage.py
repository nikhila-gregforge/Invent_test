"""Immutable validation runs. Existing inventory.sqlite3 files are never modified."""
from datetime import datetime, timezone
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
import gzip
import hashlib
import json
import sqlite3
import uuid
import inventory as config
from inventory.ingestion import parse_file
from inventory.validation import validate_upload


def today():
    return datetime.now(timezone.utc).date()


class Store:
    def __init__(self, data_dir=None):
        directory=Path(data_dir) if data_dir is not None else config.DATA_DIR
        directory.mkdir(parents=True,exist_ok=True)
        self.path=directory/'validations.sqlite3'
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS validation_runs (
                id TEXT PRIMARY KEY, filename TEXT NOT NULL, sheet TEXT NOT NULL,
                file_hash TEXT NOT NULL, profile TEXT NOT NULL, rules_version TEXT NOT NULL,
                as_of TEXT NOT NULL, created_at TEXT NOT NULL, total INTEGER NOT NULL,
                passed INTEGER NOT NULL, review INTEGER NOT NULL, failed INTEGER NOT NULL,
                original_file BLOB NOT NULL, snapshot BLOB NOT NULL,
                UNIQUE(file_hash,sheet,rules_version,as_of))''')

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=20)
        db.row_factory=sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def runs(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute('''SELECT id,filename,sheet,profile,rules_version,as_of,
                created_at,total,passed,review,failed FROM validation_runs ORDER BY created_at DESC,id''')]

    def stage(self, data, filename, sheet=None, as_of=None):
        as_of=as_of or today()
        parsed=parse_file(data,filename,sheet)
        file_hash=hashlib.sha256(data).hexdigest()
        identity=(file_hash,parsed.sheet,config.RULES_VERSION,as_of.isoformat())
        with self.connect() as db:
            existing=db.execute('SELECT id FROM validation_runs WHERE file_hash=? AND sheet=? AND rules_version=? AND as_of=?',identity).fetchone()
        if existing: return existing['id']
        snapshot=validate_upload(parsed,as_of)
        identifier=str(uuid.uuid4())
        record={'id':identifier,'filename':Path(filename.replace('\\','/')).name,'sheet':parsed.sheet,
                'profile':parsed.profile,'rules_version':config.RULES_VERSION,'as_of':as_of.isoformat(),
                'created_at':datetime.now(timezone.utc).isoformat(),'total':len(snapshot['records']),
                'passed':sum(r['status']=='Passed' for r in snapshot['records']),
                'review':sum(r['status']=='Needs review' for r in snapshot['records']),
                'failed':sum(r['status']=='Failed' for r in snapshot['records'])}
        snapshot['run']=record
        payload=gzip.compress(json.dumps(snapshot,ensure_ascii=False,allow_nan=False).encode('utf-8'))
        with self.connect() as db:
            # Identical simultaneous uploads converge on one immutable run.
            db.execute('''INSERT OR IGNORE INTO validation_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (identifier,record['filename'],parsed.sheet,file_hash,parsed.profile,config.RULES_VERSION,
                 record['as_of'],record['created_at'],record['total'],record['passed'],record['review'],record['failed'],data,payload))
            return db.execute('SELECT id FROM validation_runs WHERE file_hash=? AND sheet=? AND rules_version=? AND as_of=?',identity).fetchone()['id']

    @lru_cache(maxsize=3)
    def snapshot(self, identifier):
        with self.connect() as db:
            row=db.execute('SELECT snapshot FROM validation_runs WHERE id=?',(identifier,)).fetchone()
        if row is None: raise KeyError('Validation run not found.')
        return json.loads(gzip.decompress(row['snapshot']))
