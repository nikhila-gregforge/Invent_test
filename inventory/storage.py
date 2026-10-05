"""Immutable reviews, confirmed mappings and backwards-compatible SQLite history."""
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
from inventory.ingestion import parse_file, confirm_mapping, suggest_mapping, header_signature, header_key
from inventory.validation import validate_upload, catalogue
from inventory.exports import display

RUN_COLUMNS = ('id,filename,sheet,file_hash,profile,rules_version,as_of,created_at,total,passed,review,failed,original_file,snapshot')
CREATE_RUNS = '''CREATE TABLE IF NOT EXISTS validation_runs (
    id TEXT PRIMARY KEY, filename TEXT NOT NULL, sheet TEXT NOT NULL,
    file_hash TEXT NOT NULL, profile TEXT NOT NULL, rules_version TEXT NOT NULL,
    as_of TEXT NOT NULL, created_at TEXT NOT NULL, total INTEGER NOT NULL,
    passed INTEGER NOT NULL, review INTEGER NOT NULL, failed INTEGER NOT NULL,
    original_file BLOB NOT NULL, snapshot BLOB NOT NULL, mapping_hash TEXT NOT NULL,
    UNIQUE(file_hash,sheet,rules_version,as_of,mapping_hash))'''


def today():
    return datetime.now(timezone.utc).date()


class Store:
    def __init__(self, data_dir=None):
        directory = Path(data_dir) if data_dir is not None else config.DATA_DIR
        directory.mkdir(parents=True,exist_ok=True)
        self.path = directory/'validations.sqlite3'
        with self.connect() as db:
            columns = {r['name'] for r in db.execute('PRAGMA table_info(validation_runs)')}
            if columns and 'mapping_hash' not in columns:
                # Preserve a recoverable copy before migrating any historical results.
                backup = directory/'validations-before-mapping.sqlite3'
                if not backup.exists():
                    with sqlite3.connect(backup) as destination:
                        db.backup(destination)
            db.execute('BEGIN IMMEDIATE')
            columns = {r['name'] for r in db.execute('PRAGMA table_info(validation_runs)')}
            if columns and 'mapping_hash' not in columns:
                db.execute('ALTER TABLE validation_runs RENAME TO validation_runs_v2')
                db.execute(CREATE_RUNS)
                db.execute(f"INSERT INTO validation_runs ({RUN_COLUMNS},mapping_hash) SELECT {RUN_COLUMNS},'legacy' FROM validation_runs_v2")
                db.execute('DROP TABLE validation_runs_v2')
            else:
                db.execute(CREATE_RUNS)
            db.execute('''CREATE TABLE IF NOT EXISTS mapping_choices (
                header_signature TEXT NOT NULL, rules_version TEXT NOT NULL,
                mapping TEXT NOT NULL, PRIMARY KEY(header_signature,rules_version))''')

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
            return [dict(row) for row in db.execute('''SELECT id,filename,sheet,profile,rules_version,as_of,
                created_at,total,passed,review,failed FROM validation_runs ORDER BY created_at DESC,id''')]

    def preview(self, data, filename, sheet=None):
        parsed = parse_file(data,filename,sheet)
        signature = header_signature(parsed.columns)
        with self.connect() as db:
            saved = db.execute('SELECT mapping FROM mapping_choices WHERE header_signature=? AND rules_version=?',
                               (signature,config.RULES_VERSION)).fetchone()
        restored = False
        mapping = suggest_mapping(parsed.columns)
        if saved:
            old = json.loads(saved['mapping'])
            by_key = {header_key(c):c for c in parsed.columns}
            candidate = {f:by_key.get(column) if column is not None else None for f,column in old.items()}
            try:
                confirm_mapping(parsed,candidate)
                mapping,restored = candidate,True
            except ValueError:
                pass
        samples = {}
        for column in parsed.columns:
            values = []
            for row in parsed.rows[:50]:
                value = display(row['values'][column])
                if value and value not in values:
                    values.append(value[:180]+('…' if len(value)>180 else ''))
                if len(values)==3:
                    break
            samples[column] = values
        return dict(filename=Path(filename.replace('\\','/')).name,sheet=parsed.sheet,total=len(parsed.rows),
                    columns=parsed.columns,samples=samples,mapping=mapping,restored=restored,
                    fields=catalogue(),file_hash=hashlib.sha256(data).hexdigest(),rules_version=config.RULES_VERSION)

    def stage(self, data, filename, mapping, sheet=None, as_of=None, expected_hash=None, rules_version=None):
        file_hash = hashlib.sha256(data).hexdigest()
        if expected_hash is not None and expected_hash!=file_hash:
            raise ValueError('The file changed after preview. Upload it again and confirm its mapping.')
        if rules_version is not None and rules_version!=config.RULES_VERSION:
            raise ValueError('The inventory rules changed after preview. Upload the file again to review the current rules.')
        as_of = as_of or today()
        parsed = confirm_mapping(parse_file(data,filename,sheet),mapping)
        mapping_hash = hashlib.sha256(json.dumps(parsed.mapping,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        identity = (file_hash,parsed.sheet,config.RULES_VERSION,as_of.isoformat(),mapping_hash)
        query = 'SELECT id FROM validation_runs WHERE file_hash=? AND sheet=? AND rules_version=? AND as_of=? AND mapping_hash=?'
        with self.connect() as db:
            existing = db.execute(query,identity).fetchone()
            if existing:
                self.remember(db,parsed)
        if existing:
            return existing['id']
        snapshot = validate_upload(parsed,as_of)
        identifier = str(uuid.uuid4())
        record = {'id':identifier,'filename':Path(filename.replace('\\','/')).name,'sheet':parsed.sheet,
            'file_hash':file_hash,'profile':'inventory','rules_version':config.RULES_VERSION,'mapping_hash':mapping_hash,
            'as_of':as_of.isoformat(),'created_at':datetime.now(timezone.utc).isoformat(),'total':len(snapshot['records']),
            'passed':sum(r['status']=='Passed' for r in snapshot['records']),
            'review':sum(r['status']=='Needs review' for r in snapshot['records']),
            'failed':sum(r['status']=='Failed' for r in snapshot['records'])}
        snapshot['run'] = record
        payload = gzip.compress(json.dumps(snapshot,ensure_ascii=False,allow_nan=False).encode('utf-8'))
        with self.connect() as db:
            db.execute(f'''INSERT OR IGNORE INTO validation_runs ({RUN_COLUMNS},mapping_hash)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (identifier,record['filename'],parsed.sheet,file_hash,'inventory',config.RULES_VERSION,record['as_of'],
                 record['created_at'],record['total'],record['passed'],record['review'],record['failed'],data,payload,mapping_hash))
            self.remember(db,parsed)
            return db.execute(query,identity).fetchone()['id']

    @staticmethod
    def remember(db,parsed):
        remembered = {f:header_key(column) if column is not None else None for f,column in parsed.mapping.items()}
        db.execute('''INSERT INTO mapping_choices VALUES (?,?,?) ON CONFLICT(header_signature,rules_version)
            DO UPDATE SET mapping=excluded.mapping''',
            (header_signature(parsed.columns),config.RULES_VERSION,json.dumps(remembered)))

    @lru_cache(maxsize=3)
    def snapshot(self, identifier):
        with self.connect() as db:
            row = db.execute('SELECT snapshot FROM validation_runs WHERE id=?',(identifier,)).fetchone()
        if row is None:
            raise KeyError('Validation review not found.')
        return json.loads(gzip.decompress(row['snapshot']))
