"""Immutable fixed-format reviews; earlier review snapshots remain archived intact."""
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

CREATE_RUNS = '''CREATE TABLE IF NOT EXISTS inventory_runs (
    id TEXT PRIMARY KEY, filename TEXT NOT NULL, sheet TEXT NOT NULL,
    file_hash TEXT NOT NULL, schema_version TEXT NOT NULL, rules_version TEXT NOT NULL,
    as_of TEXT NOT NULL, created_at TEXT NOT NULL, total INTEGER NOT NULL,
    passed INTEGER NOT NULL, errors INTEGER NOT NULL,
    original_file BLOB NOT NULL, snapshot BLOB NOT NULL,
    UNIQUE(file_hash,sheet,schema_version,rules_version,as_of))'''
SUMMARY = 'id,filename,sheet,schema_version,rules_version,as_of,created_at,total,passed,errors'


def today():
    return datetime.now(timezone.utc).date()


class ArchivedReview(ValueError):
    def __init__(self, run):
        self.run = run
        super().__init__('This review used an earlier file format and rule set. Use the current inventory template and upload the file again for a new result. The original upload and results are preserved.')


class Store:
    def __init__(self, data_dir=None):
        directory = Path(data_dir) if data_dir is not None else config.DATA_DIR
        directory.mkdir(parents=True,exist_ok=True)
        self.path = directory/'validations.sqlite3'
        with self.connect() as db:
            tables = {r['name'] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.has_archive = 'validation_runs' in tables
            if self.has_archive and 'inventory_runs' not in tables:
                backup = directory/'validations-before-strict.sqlite3'
                if not backup.exists():
                    with sqlite3.connect(backup) as destination:
                        db.backup(destination)
            # Earlier tables are never rewritten. Only fixed-format reviews use this table.
            db.execute(CREATE_RUNS)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path,timeout=20)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def runs(self):
        with self.connect() as db:
            runs = [{**dict(row),'archived':False} for row in db.execute(f'SELECT {SUMMARY} FROM inventory_runs')]
            if self.has_archive:
                runs += [{**dict(row),'archived':True} for row in db.execute('''SELECT id,filename,sheet,
                    rules_version,as_of,created_at,total FROM validation_runs''')]
        return sorted(runs,key=lambda r:(r['created_at'],r['id']),reverse=True)

    def stage(self, data, filename, sheet=None, as_of=None):
        as_of = as_of or today()
        parsed = parse_file(data,filename,sheet)
        file_hash = hashlib.sha256(data).hexdigest()
        identity = (file_hash,parsed.sheet,config.SCHEMA_VERSION,config.RULES_VERSION,as_of.isoformat())
        query = 'SELECT id FROM inventory_runs WHERE file_hash=? AND sheet=? AND schema_version=? AND rules_version=? AND as_of=?'
        with self.connect() as db:
            existing = db.execute(query,identity).fetchone()
        if existing:
            return existing['id']
        snapshot = validate_upload(parsed,as_of)
        identifier = str(uuid.uuid4())
        record = {'id':identifier,'filename':Path(filename.replace('\\','/')).name,'sheet':parsed.sheet,
            'file_hash':file_hash,'schema_version':config.SCHEMA_VERSION,'rules_version':config.RULES_VERSION,
            'as_of':as_of.isoformat(),'created_at':datetime.now(timezone.utc).isoformat(),'total':len(snapshot['records']),
            'passed':sum(r['status']=='Passed' for r in snapshot['records']),
            'errors':sum(r['status']=='Errors' for r in snapshot['records']),'archived':False}
        snapshot['run'] = record
        payload = gzip.compress(json.dumps(snapshot,ensure_ascii=False,allow_nan=False).encode('utf-8'))
        with self.connect() as db:
            db.execute('''INSERT OR IGNORE INTO inventory_runs
                (id,filename,sheet,file_hash,schema_version,rules_version,as_of,created_at,total,passed,errors,original_file,snapshot)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (identifier,record['filename'],parsed.sheet,file_hash,config.SCHEMA_VERSION,config.RULES_VERSION,
                 record['as_of'],record['created_at'],record['total'],record['passed'],record['errors'],data,payload))
            return db.execute(query,identity).fetchone()['id']

    @lru_cache(maxsize=3)
    def snapshot(self, identifier):
        with self.connect() as db:
            row = db.execute('SELECT snapshot FROM inventory_runs WHERE id=?',(identifier,)).fetchone()
            if row is None and self.has_archive:
                old = db.execute('''SELECT id,filename,sheet,rules_version,as_of,created_at,total
                    FROM validation_runs WHERE id=?''',(identifier,)).fetchone()
                if old:
                    raise ArchivedReview({**dict(old),'archived':True})
        if row is None:
            raise KeyError('Validation review not found.')
        return json.loads(gzip.decompress(row['snapshot']))
