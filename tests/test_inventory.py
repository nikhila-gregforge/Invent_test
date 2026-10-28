"""Fixed column contract, error rules, immutable history and CSV acceptance."""
import csv
import gzip
import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from io import StringIO
from pathlib import Path
from time import perf_counter
import pytest
import inventory as config
from inventory.ingestion import parse_file, ImportFailure, HeaderMismatch
from inventory.normalization import count, parse_date
from inventory.validation import validate_row, validate_upload, placeholder_text, catalogue, RULES
from inventory.storage import Store, ArchivedReview
from inventory.exports import select_records, export_report, safe_cell, csv_bytes

AS_OF = date(2026,9,27)
HEADERS = list(config.HEADERS)
# Deliberately explicit: catches accidental changes to the public file contract.
EXPECTED_HEADERS = ['Application / System ID','AI System / Solution Name','Business Purpose / Intended Use',
    'Business Function','Impact from AI (Patient/Member, Regulatory, Financial)','Business Owner','Technical Owner',
    'Vendor Owner','Source of AI System','Type(s) of AI Used','ML/DL Models Count','LLM Count',
    'Data Input to or Processed by AI Tool','Data Environment','Deployment Environment','Deployment Status',
    'Go-Live Date','LOB','State','Risk Tier','Human-in-the-Loop','Submitter Name','Date Submitted']


def valid_row(rid='001', **changes):
    row = dict(zip(config.FIELDS, ['APP-'+rid,'Synthetic assistant '+rid,
        'Assist employees with locating approved internal reference material.',
        'Administrative / Back Office','Member: No, Regulatory: No, Financial: Yes',
        'Alex Smith <alex.smith@centene.com>, Operations','technical@centene.com','', 'Developed in-house',
        'LLM','', '1','Contains PII','Snowflake','Centene Cloud (AWS, Azure) account',
        'Active','1/2/2026','Commercial','CA','Medium','Yes','Synthetic Submitter','9/1/2026']))
    row.update(changes)
    return row


def csv_file(rows, headers=None, extra=None, encoding='utf-8-sig'):
    stream = StringIO(newline=''); writer = csv.writer(stream); writer.writerow(HEADERS if headers is None else headers)
    for row in rows: writer.writerow([row.get(q,'') for q in config.FIELDS]+(extra or []))
    return stream.getvalue().encode(encoding)


def dict_csv(rows):
    stream = StringIO(newline=''); writer = csv.DictWriter(stream,fieldnames=list(rows[0]))
    writer.writeheader(); writer.writerows(rows)
    return stream.getvalue().encode('utf-8-sig')


def export_csv(rows):
    inverse={field:question for question,field in config.FIELDS.items()}
    return dict_csv([{header:row[inverse[field]] if field is not None else 'Export metadata'
                      for header,field in config.EXPORT_COLUMNS.items()} for row in rows])


def snapshot(rows): return validate_upload(parse_file(csv_file(rows),'source.csv'),AS_OF)
def stage(store,data,name='source.csv',**kwargs): return store.stage(data,name,as_of=AS_OF,**kwargs)
def validate(**changes):
    row = valid_row(**changes)
    return validate_row({f:row[q] for q,f in config.FIELDS.items()},2,AS_OF)
def rules(findings): return {f.rule_id for f in findings}


def create_legacy_database(directory):
    """Simulate version-2/3 history without including private uploaded data."""
    data=csv_file([valid_row()])
    old={'run':{'id':'old-run','rules_version':'3.0'},'records':[{'status':'Needs review','warnings':1}]}
    blob=gzip.compress(json.dumps(old).encode())
    with sqlite3.connect(directory/'validations.sqlite3') as db:
        db.execute('''CREATE TABLE validation_runs (id TEXT PRIMARY KEY,filename TEXT,sheet TEXT,file_hash TEXT,
            profile TEXT,rules_version TEXT,as_of TEXT,created_at TEXT,total INTEGER,passed INTEGER,review INTEGER,
            failed INTEGER,original_file BLOB,snapshot BLOB,UNIQUE(file_hash,sheet,rules_version,as_of))''')
        db.execute('INSERT INTO validation_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            ('old-run','previous.csv','','hash','inventory','3.0','2026-09-27','2026-09-27',1,0,1,0,data,blob))
    return data,blob


def test_contract_and_literal_values():
    assert HEADERS==EXPECTED_HEADERS and len(HEADERS)==23
    data=csv_file([valid_row(Q1='0007',Q2='Café\xa0assistant',Q18='None;',Q11='0',Q12='Unknown')],encoding='cp1252')
    source=parse_file(data,'any-name.csv'); raw=source.rows[0]['values']
    assert raw[HEADERS[0]]=='0007' and raw[HEADERS[1]]=='Café\xa0assistant'
    assert [raw[HEADERS[i-1]] for i in [18,11,12]]==['None;','0','Unknown']
    for name in ['sample.csv','Forms.csv','agents.csv','INVENTORY.CSV']:
        assert parse_file(csv_file([valid_row()]),name).columns==HEADERS


@pytest.mark.parametrize('kind',['missing','extra','duplicate','case','spacing','blank','old_forms','source_id'])
def test_strict_header_rejection_is_actionable(kind):
    headers=HEADERS.copy(); extra=None
    if kind=='missing': headers.pop()
    elif kind=='extra': headers.append('Department'); extra=['Operations']
    elif kind=='duplicate': headers[1]=headers[0]
    elif kind=='case': headers[0]=headers[0].lower()
    elif kind=='spacing': headers[0]=' '+headers[0]+' '
    elif kind=='blank': headers[0]=''
    elif kind=='old_forms': headers[0]='Provide the Application ID / System ID.'
    elif kind=='source_id': headers.append('Source record ID'); extra=['001']
    with pytest.raises(HeaderMismatch) as exc: parse_file(csv_file([valid_row()],headers,extra),'file.csv')
    details=exc.value.details()
    assert any(details.values()) and 'Fix the headers' in str(exc.value)
    if kind in {'extra','source_id'}: assert details['unexpected']==[headers[-1]]
    if kind=='missing': assert details['missing']==['Date Submitted']
    if kind=='duplicate': assert details['duplicates']==[HEADERS[0]]
    if kind=='blank': assert details['blank_columns']==[1]


def test_reordered_headers_are_accepted_without_changing_values():
    raw=dict(zip(HEADERS,valid_row().values()))
    reordered=dict(reversed(list(raw.items())))
    result=validate_upload(parse_file(dict_csv([reordered]),'file.csv'),AS_OF)['records'][0]
    assert result==snapshot([valid_row()])['records'][0]
    assert result['source_values']==raw


def test_all_columns_are_required_even_when_cell_values_are_optional():
    row=valid_row(Q16='Pilot',Q17='',Q10='RPA',Q11='',Q12='',Q8='')
    assert snapshot([row])['records'][0]['status']=='Passed'
    raw=dict(zip(HEADERS,row.values())); raw.pop('Vendor Owner')
    with pytest.raises(HeaderMismatch) as exc: parse_file(dict_csv([raw]),'file.csv')
    assert exc.value.missing==['Vendor Owner']


@pytest.mark.parametrize('suffix,data',[('.csv',b''),('.csv',b'bad\n'),('.xlsx',b'not a zip'),('.xls',b'no')])
def test_invalid_files(suffix,data):
    with pytest.raises(ImportFailure): parse_file(data,'file'+suffix)


def test_row_structure_blank_rows_and_limits():
    for data in [csv_file([]),csv_file([valid_row()])+b'1,2\n',csv_file([valid_row()])+b'"unterminated\n']:
        with pytest.raises(ImportFailure): parse_file(data,'file.csv')
    source=parse_file(csv_file([valid_row(),{},valid_row('002')])+b'\n,,\n','file.csv')
    assert [r['source_row'] for r in source.rows]==[2,3,4]
    result=validate_upload(source,AS_OF)['records']
    assert [r['status'] for r in result]==['Passed','Errors','Passed']
    assert result[1]['errors']==len(config.REQUIRED)
    for kw in [{'max_bytes':1},{'max_rows':0}]:
        with pytest.raises(ImportFailure): parse_file(csv_file([valid_row()]),'file.csv',**kw)


@pytest.mark.parametrize('name',['book.xlsx','book.xls','inventory.ods','report.pdf','data.json',
                                'inventory.txt','inventory.tsv','archive.zip','inventory','inventory.csv.xlsx'])
def test_only_csv_extensions_are_accepted(name):
    with pytest.raises(ImportFailure,match='Only CSV files are accepted'):
        parse_file(csv_file([valid_row()]),name)


def test_csv_preserves_leading_zeros_dates_and_literal_formula_text():
    source=parse_file(csv_file([valid_row(Q1='0007',Q17='2026-01-02',Q12='=1+1')]),'source.csv')
    assert source.sheet==''
    raw=source.rows[0]['values']
    assert raw[HEADERS[0]]=='0007' and raw[HEADERS[16]]=='2026-01-02'
    assert raw['LLM Count']=='=1+1'
    result=validate_upload(source,AS_OF)['records'][0]
    assert {f['rule_id'] for f in result['findings']}=={'COUNT-01'}


@pytest.mark.parametrize('value,expected',[('0',(0,'known')),('1.0',(1,'known')),('',(None,'not_provided')),('TBD',(None,'unknown')),('Not Available',(None,'unknown')),('N/A',(None,'unknown'))])
def test_counts(value,expected): assert count(value)==expected


@pytest.mark.parametrize('value',['-1','1.5','Infinity','NaN','one LLM','3 or 4','Auto/Quick/Think deeper',True,'1e3'])
def test_invalid_counts(value):
    with pytest.raises(ValueError): count(value)
    assert 'COUNT-01' in rules(validate(Q12=value)[1])


@pytest.mark.parametrize('technology,llm,ml,error',[
 ('LLM','0','',None),('LLM','','','COUNT-02'),('LLM','Unknown','','COUNT-02'),
 ('ML','','0','COUNT-03'),('DL','','Unknown','COUNT-03'),('GenAI','','','COUNT-02'),
 ('Agentic AI','0','',None),('Predictive Analytics','','','COUNT-03'),('RPA','1','',None),
 ('GenAI','2','',None),('Predictive Analytics','','2',None),('RPA','Unknown','',None),('RPA','no','','COUNT-01')])
def test_model_requirements(technology,llm,ml,error):
    assert rules(validate(Q10=technology,Q12=llm,Q11=ml)[1])==({error} if error else set())


@pytest.mark.parametrize('value',['Alex Smith <alex.smith@centene.com>','alex@centene.com, Operations',
                                '张伟 (wei@centene.com)','A. Kumar — a.kumar@centene.com',
                                'alex-smith+alias@centene.com','a@centene.com;b@centene.com'])
def test_owner_emails_with_names_and_notes_are_accepted(value): assert not validate(Q6=value,Q7=value)[1]


@pytest.mark.parametrize('value',['TBD','123','a@','owner@example..com'])
def test_invalid_owners(value): assert rules(validate(Q6=value)[1]) & {'REQ-02','EMAIL-01'}


@pytest.mark.parametrize('field,value,rule_id',[
 ('Q16','Active;Pilot','ENUM-01'),('Q18','None;Medicare','SCOPE-01'),
 ('Q19','All States;CA','SCOPE-01'),('Q19','None;CA','SCOPE-01')])
def test_invalid_values(field,value,rule_id): assert rule_id in rules(validate(**{field:value})[1])


def test_explicitly_permitted_values_and_former_advisory_cases_pass():
    rows=[valid_row(Q1='Not Available',Q6='owner@centene.com',Q20='Unknown',Q5='Unknown',Q21='Unknown',
                   Q9='Other: Research prototype',Q8='Research Vendor — Alex Smith',Q10='GenAI',Q12='0',Q16='Pilot',Q17=''),
          valid_row('002',Q1='Unknown',Q2='Synthetic assistant 001')]
    result=snapshot(rows)
    assert all(r['status']=='Passed' and not r['findings'] for r in result['records'])
    assert not any('severity' in r for r in RULES)
    serialized=json.dumps(result)
    assert all(s not in serialized for s in ['warnings','Needs review','mapping'])


def test_vendor_and_scope_errors():
    assert 'VENDOR-01' in rules(validate(Q9='Hybrid (in-house + vendor components)',Q8='N/A')[1])
    assert not validate(Q9='Other: Research prototype',Q8='')[1]
    assert not validate(Q18='Medicaid',Q19='None')[1]
    assert not validate(Q18='Medicaid',Q19='DC')[1]
    assert not validate(Q4='Fraud, Waste, & Abuse Detection;Claims Processing;Claims Processing;')[1]


@pytest.mark.parametrize('value',['45201','1/35/2026','2026-02-30','2026/01/01','tomorrow'])
def test_invalid_dates_for_all_lifecycles(value):
    for status in ['Active','Pilot','Retired']:
        _,findings,_=validate(Q16=status,Q17=value)
        assert rules(findings)=={'DATE-01'}


def test_date_boundaries_and_oversight():
    assert parse_date('1/1/68')=='2068-01-01' and parse_date('1/1/69')=='1969-01-01'
    assert 'DATE-02' in rules(validate(Q17='')[1])
    assert not validate(Q17='2026-09-28')[1]
    assert not validate(Q16='Pilot',Q17='2026-09-28')[1]
    assert 'DATE-05' in rules(validate(Q23='2026-09-28')[1])
    assert not validate(Q16='Retired',Q17='')[1]
    product,findings,_=validate(Q21='Yes—at final stage; Override: No')
    assert not findings and product['human_oversight']=='Partially' and product['override_capability']=='No'


def test_invalid_dependencies_produce_root_errors_without_cascading():
    _,findings,blocked=validate(Q10='',Q9='',Q16='Active;Pilot',Q12='Auto')
    assert rules(findings)=={'REQ-01','ENUM-01','COUNT-01'}
    assert {'COUNT-02','COUNT-03','VENDOR-01','DATE-02'} <= {c['rule_id'] for c in blocked}
    assert all(c['blocked_by'] and 'Fix ' in c['reason'] for c in blocked)
    result=snapshot([valid_row(Q18='Medicaid',Q19='')])['records'][0]
    assert result['status']=='Errors' and result['errors']==1
    assert result['field_results']['lines_of_business']=='No errors'


@pytest.mark.parametrize('value',['test',' TEST123 ','testing','test test','this is a test','test-description','New Agent 4','Untitled Agent','TBD','12345'])
def test_nonblank_descriptions_do_not_use_wording_heuristics(value):
    assert not validate(Q2=value,Q3=value)[1]


@pytest.mark.parametrize('value',['Automates regression testing for claims applications.','Test eligibility rules against approved scenarios.','Latest claims guidance retrieval','Contest administration for employee events'])
def test_legitimate_testing_purposes(value):
    assert not placeholder_text(value)
    assert snapshot([valid_row(Q3=value)])['records'][0]['status']=='Passed'


def test_independent_rows_duplicate_ids_and_bounded_diagnostics():
    alone=snapshot([valid_row()])['records'][0]
    batch=snapshot([valid_row(),valid_row('002',Q3='',Q12='zero')])
    assert alone==batch['records'][0] and batch['records'][1]['errors']==2
    repeated=snapshot([valid_row(Q1='0007'),valid_row('002',Q1=' 0007 ',Q2='Other assistant'),valid_row('003')])['records']
    assert all({f['rule_id'] for f in r['findings']}=={'ID-02'} for r in repeated[:2])
    assert repeated[2]['status']=='Passed'
    assert all(r['status']=='Passed' for r in snapshot([valid_row(Q1='Not Available'),valid_row('002',Q1='Not Available')])['records'])
    records=snapshot([valid_row(Q2='Repeated system') for _ in range(100)])['records']
    assert all(r['status']=='Errors' for r in records)
    assert all(len(f['message'])<300 for r in records for f in r['findings'])


def test_unavailable_id_placeholders_are_not_treated_as_duplicate_actual_ids():
    records=snapshot([valid_row(Q1='NA'),valid_row('002',Q1='NA')])['records']
    assert all(r['status']=='Passed' for r in records)


def test_actionable_messages_and_shared_rule_catalogue():
    by_id={r['id']:r for r in RULES}; assert len(by_id)==len(RULES)
    assert [f['label'] for f in catalogue()]==HEADERS
    for field in catalogue():
        assert field['format'] and field['description']
        for spec in field['checks']: assert spec['fix'] and spec['requirement'] and 'check' not in spec and 'severity' not in spec
    findings=validate(Q3='',Q12='Auto',Q6='')[1]
    for finding in findings:
        assert finding.fix and finding.message
        assert finding.requirement==by_id[finding.rule_id]['requirement']
    assert 'Describe what the system does' in next(f.fix for f in findings if f.fields==['business_purpose'])
    assert 'any domain' in next(f.fix for f in findings if f.rule_id=='REQ-01')


def test_immutable_history_deduplication_and_original_upload(tmp_path,monkeypatch):
    old=tmp_path/'inventory.sqlite3'; old.write_bytes(b'old onboarding data')
    store=Store(tmp_path); data=csv_file([valid_row()]); first=stage(store,data)
    frozen=json.dumps(store.snapshot(first),sort_keys=True)
    assert stage(store,data,'renamed.csv')==first and len(store.runs())==1
    with store.connect() as db: assert db.execute('SELECT original_file FROM inventory_runs').fetchone()[0]==data
    assert json.dumps(Store(tmp_path).snapshot(first),sort_keys=True)==frozen
    assert old.read_bytes()==b'old onboarding data'
    assert store.stage(data,'source.csv',as_of=date(2026,9,28))!=first
    monkeypatch.setattr(config,'RULES_VERSION','next-version'); assert stage(store,data)!=first
    assert json.dumps(Store(tmp_path).snapshot(first),sort_keys=True)==frozen
    before=len(store.runs())
    with pytest.raises(ImportFailure): stage(store,b'old,format\n1,2\n')
    assert len(store.runs())==before


def test_concurrent_identical_uploads(tmp_path):
    store=Store(tmp_path); data=csv_file([valid_row()])
    with ThreadPoolExecutor(max_workers=4) as pool: ids=list(pool.map(lambda _:stage(store,data),range(4)))
    assert len(set(ids))==1 and len(store.runs())==1


def test_delete_removes_only_selected_review_and_upload_and_allows_reupload(tmp_path):
    store=Store(tmp_path); reader=Store(tmp_path)
    data=csv_file([valid_row()]); first=stage(store,data)
    second=stage(store,csv_file([valid_row('002')]))
    untouched=json.dumps(store.snapshot(second),sort_keys=True)
    assert reader.snapshot(first)['run']['id']==first
    store.delete(first)
    for instance in [store,reader,Store(tmp_path)]:
        with pytest.raises(KeyError,match='Validation review not found'): instance.snapshot(first)
        assert json.dumps(instance.snapshot(second),sort_keys=True)==untouched
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM inventory_runs WHERE id=?',(first,)).fetchone()[0]==0
    with pytest.raises(KeyError): store.delete(first)
    replacement=stage(store,data)
    assert replacement!=first and store.snapshot(replacement)['records'][0]['status']=='Passed'


def test_delete_archived_review_preserves_current_reviews_and_existing_backup(tmp_path):
    create_legacy_database(tmp_path); store=Store(tmp_path)
    current=stage(store,csv_file([valid_row()]))
    backup=(tmp_path/'validations-before-strict.sqlite3').read_bytes()
    store.delete('old-run')
    assert [run['id'] for run in store.runs()]==[current]
    with pytest.raises(KeyError): store.snapshot('old-run')
    assert store.snapshot(current)['run']['id']==current
    assert (tmp_path/'validations-before-strict.sqlite3').read_bytes()==backup


def test_old_reviews_are_archived_without_changing_results(tmp_path):
    data,blob=create_legacy_database(tmp_path); store=Store(tmp_path)
    assert (tmp_path/'validations-before-strict.sqlite3').exists()
    with pytest.raises(ArchivedReview) as exc: store.snapshot('old-run')
    assert exc.value.run['archived'] and 'upload the file again' in str(exc.value)
    assert store.runs()[0]['archived'] and 'passed' not in store.runs()[0]
    with store.connect() as db:
        row=db.execute('SELECT original_file,snapshot,review FROM validation_runs').fetchone()
        assert tuple(row)==(data,blob,1)
    new=stage(store,data)
    assert new!='old-run' and len(Store(tmp_path).runs())==2
    assert not store.snapshot(new)['run']['archived']


@pytest.mark.parametrize('value',['=1+1','+CMD','-1','@SUM(A1)',' \t=HYPERLINK("x")','\x00\r@cmd','\u200b=cmd'])
def test_formula_export_safety(value): assert safe_cell(value)=="'"+value


def test_filters_reports_and_snapshot_immutability(tmp_path):
    store=Store(tmp_path); identifier=stage(store,csv_file([valid_row(),valid_row('002',Q3=''),valid_row('003',Q12='-1')]))
    data=store.snapshot(identifier); frozen=json.dumps(data,sort_keys=True)
    selected=select_records(data,{'status':'all','field':'business_purpose'})
    assert [r['application_id'] for r in selected]==['APP-002']
    assert len(select_records(data,{'status':'Passed','q':'001'}))==1 and len(select_records(data,{}))==2
    for kind in ['records','errors']:
        payload=export_report(data,selected,kind); rows=list(csv.DictReader(StringIO(payload.decode('utf-8-sig'))))
        assert payload.startswith(b'\xef\xbb\xbf') and rows and all(r['Validation run']==identifier for r in rows)
        assert rows[0]['Source row']=='3' and rows[0]['Inventory format']==config.SCHEMA_VERSION
        assert not any('mapping' in k.lower() or 'warning' in k.lower() or 'severity' in k.lower() for k in rows[0])
        if kind=='errors': assert rows[0]['How to fix'] and rows[0]['Problem'] and rows[0]['Requirement']
    assert json.dumps(data,sort_keys=True)==frozen
    for args in [{'field':'bogus'},{'status':'Needs review'},{'status':'attention'},{'status':'Failed'}]:
        with pytest.raises(ValueError): select_records(data,args)
    with pytest.raises(ValueError): export_report(data,selected,'issues')


def test_reports_keep_blank_zero_unknown_and_original_values(tmp_path):
    store=Store(tmp_path); data=csv_file([valid_row(Q1='0007',Q3='=1+1',Q11='0',Q12='Unknown',Q17='',Q16='Pilot')])
    result=store.snapshot(stage(store,data))
    rows=list(csv.DictReader(StringIO(export_report(result,result['records'],'records').decode('utf-8-sig'))))
    for header,value in [('Application / System ID','0007'),('ML/DL Models Count','0'),('LLM Count','Unknown'),('Go-Live Date',''),('Business Purpose / Intended Use',"'=1+1")]:
        assert rows[0]['Source: '+header]==value
    assert result['records'][0]['source_values']['Business Purpose / Intended Use']=='=1+1'


@pytest.mark.parametrize('size',[1000,10000])
def test_batch_size_and_performance(size):
    rows=[valid_row(str(i).zfill(5),Q6=f'owner-{i}@centene.com',Q7=f'tech-{i}@centene.com') for i in range(size)]
    start=perf_counter(); data=snapshot(rows); elapsed=perf_counter()-start
    assert len(data['records'])==size and all(r['status']=='Passed' for r in data['records'])
    print(f'BATCH rows={size} parse_and_validate_seconds={elapsed:.3f}')


def test_private_source_export_requires_external_header_correction():
    source=os.getenv('AI_INVENTORY_AGENT_SNAPSHOT')
    if not source: pytest.skip('Private source export is not bundled.')
    with pytest.raises(HeaderMismatch) as exc: parse_file(Path(source).read_bytes(),'reference.csv')
    assert exc.value.missing and exc.value.unexpected
