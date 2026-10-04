"""Parser, rules, storage, exports, and acceptance checks with synthetic fixtures."""
import os
import json


# Helpers
import csv
from io import StringIO,BytesIO
from datetime import date
from openpyxl import Workbook
import inventory as config

AS_OF = date(2026,9,27)

def valid_row(rid='001', **changes):
    row = dict(zip(['ID', *config.FIELDS], [rid,'APP-'+rid,'Synthetic assistant '+rid,
        'Assist employees with locating approved internal reference material.',
        'Administrative / Back Office','Member: No, Regulatory: No, Financial: Yes',
        'alex-smith+owner@centene.com','technical@centene.com','', 'Developed in-house',
        'LLM','', '1','Contains PII','Snowflake','Centene Cloud (AWS, Azure) account',
        'Active','1/2/2026','Commercial','CA','Medium','Yes','Synthetic Submitter','9/1/2026']))
    row.update(changes)
    return row

def csv_file(rows, headers=None, extra=None, encoding='utf-8-sig'):
    headers = headers or [config.HEADER_ALIASES[q][0] for q in ['ID',*config.FIELDS]]
    stream = StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([row.get(q,'') for q in ['ID',*config.FIELDS]]+(extra or []))
    return stream.getvalue().encode(encoding)

def xlsx_file(rows, mutate=None):
    wb = Workbook()
    ws = wb.active
    ws.title = 'Disclosure'
    ws.append([config.HEADER_ALIASES[q][0] for q in ['ID',*config.FIELDS]])
    for row in rows: ws.append([row.get(q,'') for q in ['ID',*config.FIELDS]])
    if mutate: mutate(wb)
    out = BytesIO()
    wb.save(out)
    return out.getvalue()

# Conftest
import pytest

# Ingestion
from datetime import date,datetime
import csv
from io import StringIO
import pytest
import inventory as config
from inventory.ingestion import parse_file,ImportFailure,SheetSelectionRequired
from inventory.normalization import raw_inputs,normalize


def test_encoding_and_literal_preservation():
    data = csv_file([valid_row(Q1='0007',Q2='Café\xa0assistant',Q18='None;',Q11='N/A',Q12='Unknown')],encoding='cp1252')
    row = parse_file(data,'source.csv').rows[0]
    assert row['values']['ID'] == '001'
    assert row['values']['Q1'] == '0007'
    assert [row['values'][q] for q in ['Q18','Q11','Q12']] == ['None;','N/A','Unknown']

@pytest.mark.parametrize('kind',['missing','duplicate','normalized','canonical','malformed','quote'])
def test_structural_errors(kind):
    headers = [config.HEADER_ALIASES[q][0] for q in ['ID',*config.FIELDS]]
    if kind == 'missing': headers[2] = 'System Name'
    elif kind == 'duplicate': headers[2] = headers[1]
    elif kind == 'normalized': headers[2] = '  '+headers[1].replace(' ','\xa0')+' '
    elif kind == 'canonical': headers.append(config.HEADER_ALIASES['Q11'][1])
    data = csv_file([valid_row()],headers)
    if kind == 'malformed': data += b'1,2\n'
    elif kind == 'quote': data += b'"unterminated\n'
    with pytest.raises(ImportFailure): parse_file(data,'source.csv')


def test_trailing_and_interior_rows():
    data = csv_file([valid_row(),{},valid_row('002')])+b'\n,,\n'
    parsed = parse_file(data,'source.csv')
    assert [r['source_row'] for r in parsed.rows] == [2,3,4]
    assert parsed.rows[1]['values']['ID'] == ''


def test_extra_metadata_and_limits():
    headers = [config.HEADER_ALIASES[q][0] for q in ['ID',*config.FIELDS]]+['Work Queue']
    data = csv_file([valid_row()],headers,extra=['retain only'])
    parsed = parse_file(data,'source.csv')
    assert parsed.rows[0]['metadata']['Work Queue'] == 'retain only'
    with pytest.raises(ImportFailure,match='MiB'): parse_file(data,'source.csv',max_bytes=1)
    with pytest.raises(ImportFailure,match='data-row'): parse_file(data,'source.csv',max_rows=0)
    with pytest.raises(ImportFailure,match='Unsupported'): parse_file(data,'source.xls')
    with pytest.raises(ImportFailure): parse_file(b'not a zip','source.xlsx')


def test_xlsx_dates_padding_formula_and_sheets():
    def mutate(wb):
        ws=wb.active
        ws['A2']=7; ws['A2'].number_format='0000'
        ws['B2']='0009'
        ws['R2']=datetime(2026,1,2)
        ws['M2']='=1+1'
        wb.create_sheet('Empty')
    data=xlsx_file([valid_row()],mutate)
    row=parse_file(data,'source.xlsx').rows[0]
    assert row['values']['ID']=='0007' and row['values']['Q1']=='0009'
    assert row['formulas']==['Q12']
    assert normalize(raw_inputs(row))[0]['go_live_date']=='2026-01-02'
    def several(wb): wb.copy_worksheet(wb.active).title='Second'
    multi=xlsx_file([valid_row()],several)
    with pytest.raises(SheetSelectionRequired) as exc: parse_file(multi,'source.xlsx')
    assert exc.value.sheets==['Disclosure','Second']
    assert parse_file(multi,'source.xlsx','Second').sheet=='Second'

# Validation
from datetime import date
import pytest
from inventory.ingestion import parse_file
from inventory.normalization import raw_inputs,count,parse_date,normalize
from inventory.validation import validate_row


def validate(**changes):
    row=parse_file(csv_file([valid_row(**changes)]),'synthetic.csv').rows[0]
    return validate_row(raw_inputs(row),2,AS_OF,legacy=True)

def rules(findings,severity='ERROR'):
    return {f.rule_id for f in findings if f.severity==severity}


def test_valid_and_multiselect_commas():
    product,findings=validate(Q4='Fraud, Waste, & Abuse Detection;Claims Processing;Claims Processing;')
    assert not rules(findings)
    assert product['business_functions']==['Fraud, Waste, & Abuse Detection','Claims Processing']

@pytest.mark.parametrize('value,expected', [('0',(0,'known')),('1.0',(1,'known')),('',(None,'not_provided')),('TBD',(None,'unknown')),('Not Available',(None,'unknown'))])
def test_counts(value,expected): assert count(value)==expected

@pytest.mark.parametrize('value', ['-1','1.5','Infinity','NaN','one LLM','3 or 4','1 (model)','N/A',True,'1e3'])
def test_invalid_counts(value):
    with pytest.raises(ValueError): count(value)

@pytest.mark.parametrize('technology,llm,ml,blocking,warnings',[
 ('LLM','0','','COUNT-02',None),('LLM','','','COUNT-02',None),('LLM','Unknown','','COUNT-02',None),
 ('ML','','0','COUNT-03',None),('DL','','Unknown','COUNT-03',None),
 ('GenAI','','',None,'COUNT-04'),('Agentic AI','0','',None,'COUNT-04'),
 ('Predictive Analytics','','',None,'COUNT-04'),('RPA','1','',None,'COUNT-05'),
 ('GenAI','2','',None,None),('Predictive Analytics','','2',None,None),
 ('RPA','Unknown','',None,'COUNT-06'),('RPA','no','', 'COUNT-01',None)])
def test_conditional_counts(technology,llm,ml,blocking,warnings):
    _,f=validate(Q10=technology,Q12=llm,Q11=ml)
    assert rules(f)==({blocking} if blocking else set())
    if warnings: assert warnings in rules(f,'WARNING')

@pytest.mark.parametrize('field,value,rule',[
 ('Q16','Inactive','ENUM-01'),('Q16','Not Active','ENUM-01'),('Q16','Active;Pilot','ENUM-01'),
 ('Q20','Very Low','RISK-01'),('Q19','Atlantis','ENUM-01'),('Q9','Other','ENUM-01'),
 ('Q18','None;Medicare','SCOPE-01'),('Q19','All States;CA','SCOPE-01'),('Q19','None;CA','SCOPE-01'),
 ('Q6','Alex Smith','EMAIL-01'),('Q7','a@centene.com;b@centene.com','EMAIL-01'),
 ('Q5','no insights','IMPACT-01'),('Q5','Member: No, Financial: Yes','IMPACT-01'),
 ('Q5','Member: No, Member: Yes, Regulatory: No, Financial: No','IMPACT-01'),
 ('Q21','Autonomous sometimes','HITL-01')])
def test_invalid_categories_and_values(field,value,rule):
    assert rule in rules(validate(**{field:value})[1])


def test_unknowns_aliases_and_other():
    p,f=validate(Q20='Unknown',Q5='Unknown',Q21='Unknown',Q9='Other: Research prototype',Q18='Employer Group;',Q19='All')
    assert not rules(f)
    assert p['risk_tier']=='Unknown' and set(p['impact'].values())=={'Unknown'}
    assert p['other_details']['ai_source']=='Research prototype'
    assert p['lines_of_business']==['Employer Groups'] and p['states']==['All States']
    assert {'RISK-01','IMPACT-01','HITL-01','VENDOR-02'}<=rules(f,'WARNING')


def test_source_vendor_and_external_email():
    assert 'VENDOR-01' in rules(validate(Q9='Hybrid (in-house + vendor components)',Q8='N/A')[1])
    assert 'EMAIL-02' in rules(validate(Q6='alex-smith@subsidiary.example')[1],'WARNING')
    assert not rules(validate(Q6='alex-smith+alias@centene.com')[1])
    assert 'SCOPE-02' in rules(validate(Q18='Medicaid',Q19='None')[1])

@pytest.mark.parametrize('value',['45201','1/35/2026','2026-02-30','2026/01/01','tomorrow'])
def test_dates_fail_all_lifecycles(value):
    for status in ['Active','Pilot','Retired']:
        assert 'DATE-01' in rules(validate(Q16=status,Q17=value)[1])


def test_dates_boundaries():
    assert parse_date('1/1/68')=='2068-01-01'
    assert parse_date('1/1/69')=='1969-01-01'
    assert 'DATE-02' in rules(validate(Q17='')[1])
    assert 'DATE-02' in rules(validate(Q17='2026-09-28')[1])
    assert 'DATE-03' in rules(validate(Q16='Pilot',Q17='2026-09-28')[1],'WARNING')
    assert 'DATE-01' in rules(validate(Q23='2026-09-28')[1])
    assert not rules(validate(Q16='Retired',Q17='')[1])


def test_hitl_legacy_and_explicit_override():
    assert validate(Q21='Yes')[0]['override_capability']=='Unknown'
    inputs=raw_inputs({'values':valid_row(Q21='Yes—at final stage; Override: No')})
    p,f=validate_row(inputs,2,AS_OF,False)
    assert not rules(f) and p['human_oversight']=='Partially' and p['override_capability']=='No'
    assert validate(Q21='Conditional (exception) = human review triggered by thresholds')[0]['human_oversight']=='Partially'


# Read-only validation runs and reports
from pathlib import Path
from collections import Counter
from time import perf_counter
import sqlite3
from inventory.storage import Store
from inventory.validation import validate_upload, placeholder_text
from inventory.exports import select_records, field_summary, export_report, safe_cell


def agent_row(rid='agent-001', **changes):
    values={'Name':'Claims reference assistant '+rid,'Title ID':rid,'Description':'Find approved claims guidance for operational teams.',
        'Owner':'Alex Owner','Publisher':'Taylor Publisher','Status':'Active','Platform':'Internal agent service',
        'Date created':'2026-01-01T10:00:00Z','Last Modified':'2026-01-02T10:00:00Z',
        'Instructions':'Use the approved claims reference library and cite the source.',
        'Market Name':'California','Line of Business Name':'Commercial','Department Name':'Operations','Job Title':'Analyst',
        'Business Function':'Claims Processing','Impact from AI (Patient/Member, Regulatory, Financial)':'Member: No, Regulatory: No, Financial: Yes',
        'Vendor Owner':'N/A','Type(s) of AI used':'LLM','ML/DL Models Count':'0','LLM Count':'1',
        'Data input to or processed by AI tool':'Claims data','Data Environment':'Snowflake',
        'Deployment Environment':'Centene Cloud (AWS, Azure) account','State':'CA','Risk Tier':'Medium',
        'Human-in-the-Loop & Override Capability':'Yes','Source of AI System':'Developed in-house',
        'Go-Live Date':'2026-01-02','LOB':'Commercial'}
    values.update(changes)
    return values


def agent_csv(rows):
    out=StringIO(newline='')
    writer=csv.DictWriter(out,fieldnames=list(rows[0]))
    writer.writeheader();writer.writerows(rows)
    return out.getvalue().encode('utf-8-sig')


def snapshot(rows): return validate_upload(parse_file(csv_file(rows),'test.csv'),AS_OF)


@pytest.mark.parametrize('value',['test',' TEST123 ','testing','test test','this is a test','test-description','New Agent 4','Untitled Agent','TBD','12345'])
def test_placeholder_patterns(value):
    assert placeholder_text(value)
    result=snapshot([valid_row(Q3=value)])['records'][0]
    assert result['status']=='Failed'
    assert any(f['rule_id']=='TEXT-01' for f in result['findings'])


@pytest.mark.parametrize('value',['Automates regression testing for claims applications.','Test eligibility rules against approved scenarios.','Latest claims guidance retrieval','Contest administration for employee events'])
def test_real_testing_purposes_are_not_placeholders(value):
    assert not placeholder_text(value)
    assert snapshot([valid_row(Q3=value)])['records'][0]['status']=='Passed'


def test_records_validate_independently_and_summary_deduplicates():
    original=valid_row()
    alone=snapshot([original])['records'][0]
    together=snapshot([original,valid_row('002',Q3='test',Q12='zero')])
    assert alone==together['records'][0]
    assert [r['status'] for r in together['records']]==['Passed','Failed']
    fields={f['id']:f for f in field_summary(together,together['records'])}
    assert fields['business_purpose']['affected']==1
    assert fields['llm_count']['affected']==1


def test_raw_profile_does_not_infer_meaning_and_preserves_source():
    row=agent_row(Status='Available',**{'LLM Count':'Auto/Quick/Think deeper','Description':'test123','Instructions':'a'*8000})
    for field in config.AGENT_OPTIONAL: row.pop(field)
    parsed=parse_file(agent_csv([row]),'agent.csv')
    assert parsed.profile=='agents'
    result=validate_upload(parsed,AS_OF)['records'][0]
    assert result['source_values']==row
    findings=result['findings']
    assert {'GAP-01','COUNT-01','TEXT-01','LENGTH-01'}<={f['rule_id'] for f in findings}
    assert any(f['rule_id']=='GAP-01' and 'deployment_status' in f['fields'] for f in findings)
    assert result['cells']['go_live_date']==''
    assert not any(f['rule_id']=='EMAIL-01' for f in findings)


def test_valid_raw_record_and_missing_columns():
    data=agent_csv([agent_row()])
    assert validate_upload(parse_file(data,'agents.csv'),AS_OF)['records'][0]['status']=='Passed'
    data=agent_csv([{'Title ID':'1','Name':'Claims assistant','Description':'Find approved claims guidance.'}])
    result=validate_upload(parse_file(data,'minimal.csv'),AS_OF)['records'][0]
    assert result['status']=='Failed'
    assert any(f['fields']==['business_owner_email'] for f in result['findings'])


def test_duplicate_flags_only_affect_matching_rows():
    results=snapshot([valid_row(),valid_row('002',Q2='Synthetic assistant 001'),valid_row('003')])['records']
    assert [r['status'] for r in results]==['Needs review','Needs review','Passed']
    results=snapshot([valid_row(),valid_row(Q2='Different assistant'),valid_row('003')])['records']
    assert results[0]['status']==results[1]['status']=='Failed'
    assert results[2]['status']=='Passed'


def test_raw_dates_and_formulas():
    row=agent_row(**{'Date created':'2026-02-01T00:00:00Z','Last Modified':'2026-01-01T00:00:00Z'})
    assert any(f['rule_id']=='DATE-04' for f in validate_upload(parse_file(agent_csv([row]),'a.csv'),AS_OF)['records'][0]['findings'])
    def formula(wb): wb.active['D2']='=1+1'
    parsed=parse_file(xlsx_file([valid_row()],formula),'a.xlsx')
    record=validate_upload(parsed,AS_OF)['records'][0]
    assert any(f['rule_id']=='FORMULA-01' for f in record['findings'])
    assert record['source_values'][config.HEADER_ALIASES['Q3'][0]]=='=1+1'


def test_persistence_idempotence_and_legacy_database_untouched(tmp_path):
    legacy=tmp_path/'inventory.sqlite3';legacy.write_bytes(b'preserve existing database')
    store=Store(tmp_path);data=csv_file([valid_row(),valid_row('002',Q3='test')])
    run=store.stage(data,'first.csv',as_of=AS_OF)
    assert store.stage(data,'renamed.csv',as_of=AS_OF)==run
    restored=Store(tmp_path)
    assert restored.snapshot(run)==store.snapshot(run)
    assert restored.runs()[0]['total']==2
    assert restored.runs()[0]['passed']==1
    assert legacy.read_bytes()==b'preserve existing database'
    with restored.connect() as db:
        assert db.execute('SELECT original_file FROM validation_runs WHERE id=?',(run,)).fetchone()[0]==data
    next_run=store.stage(data,'first.csv',as_of=date(2026,9,28))
    assert next_run!=run and len(store.runs())==2
    with pytest.raises(ImportFailure): store.stage(b'not,csv','broken.csv',as_of=AS_OF)
    assert len(store.runs())==2


@pytest.mark.parametrize('text',['=1+1','+CMD','-1','@SUM(A1)',' \t=HYPERLINK("x")','\x00\r@cmd','\u200b=cmd'])
def test_formula_export_safety(text): assert safe_cell(text)=="'"+text


def test_filter_semantics_exports_and_snapshot_immutability(tmp_path):
    store=Store(tmp_path)
    identifier=store.stage(csv_file([valid_row(),valid_row('002',Q3='test'),valid_row('003',Q20='Unknown')]),'sample.csv',as_of=AS_OF)
    data=store.snapshot(identifier)
    frozen=json.dumps(data,sort_keys=True)
    args={'status':'all','field':'business_purpose','rule':'TEXT-01','severity':'ERROR'}
    selected=select_records(data,args)
    assert [r['response_id'] for r in selected]==['002']
    assert not select_records(data,{**args,'field':'risk_tier'})
    assert len(select_records(data,{'status':'Needs review'}))==1
    assert len(select_records(data,{'status':'all','column':'risk_tier','value':'Unknown','exact':'1'}))==1
    for kind in ['records','issues','fields']:
        payload=export_report(data,selected,kind)
        assert payload.startswith(b'\xef\xbb\xbf')
        rows=list(csv.DictReader(StringIO(payload.decode('utf-8-sig'))))
        assert rows and all(row['Validation run']==identifier for row in rows)
    assert json.dumps(data,sort_keys=True)==frozen
    with pytest.raises(ValueError): select_records(data,{'field':'bogus'})
    with pytest.raises(ValueError): select_records(data,{'status':'all','value':'text'})


def test_reports_preserve_blank_zero_unknown_and_escape_headers(tmp_path):
    store=Store(tmp_path)
    headers=[config.HEADER_ALIASES[q][0] for q in ['ID',*config.FIELDS]]+['=malicious_header']
    data=csv_file([valid_row(Q11='0',Q12='Unknown',Q17='',Q16='Pilot')],headers,extra=['=1+1'])
    run=store.stage(data,'source.csv',as_of=AS_OF);s=store.snapshot(run)
    rows=list(csv.DictReader(StringIO(export_report(s,s['records'],'records').decode('utf-8-sig'))))
    assert rows[0][config.HEADER_ALIASES['Q11'][0]]=='0'
    assert rows[0][config.HEADER_ALIASES['Q12'][0]]=='Unknown'
    assert rows[0]['Go-Live Date']==''
    assert rows[0]["'=malicious_header"]=="'=1+1"


@pytest.mark.parametrize('size',[1000,10000])
def test_batch_size_and_performance(size):
    rows=[valid_row(str(i).zfill(5),Q6=f'owner-{i}@centene.com',Q7=f'tech-{i}@centene.com') for i in range(size)]
    start=perf_counter();data=snapshot(rows);elapsed=perf_counter()-start
    assert len(data['records'])==size and all(r['status']=='Passed' for r in data['records'])
    print(f'BATCH rows={size} parse_and_validate_seconds={elapsed:.3f}')


def test_reference_export_if_available():
    source=os.getenv('AI_INVENTORY_AGENT_SNAPSHOT')
    if not source: pytest.skip('Private reference export is not bundled.')
    data=validate_upload(parse_file(Path(source).read_bytes(),'reference.csv'),date(2026,10,1))
    assert len(data['records'])==249
    assert sum(any(f['rule_id']=='TEXT-01' and f['fields']==['business_purpose'] for f in r['findings']) for r in data['records'])==5
    assert sum(any(f['rule_id']=='COUNT-01' and f['fields']==['llm_count'] for f in r['findings']) for r in data['records'])==249
    assert sum(any(f['rule_id']=='LENGTH-01' for f in r['findings']) for r in data['records'])==13


def test_duplicate_id_and_application_flags_and_bounded_diagnostics():
    results=snapshot([valid_row(),valid_row('002',Q1=' app-001 '),valid_row('003')])['records']
    assert all(any(f['rule_id']=='ID-02' for f in r['findings']) for r in results[:2])
    assert results[2]['status']=='Passed'
    records=snapshot([valid_row(Q2='Repeated system') for _ in range(100)])['records']
    assert all(r['status']=='Failed' for r in records)
    assert all(len(f['expected_condition'])<400 for r in records for f in r['findings'])


def test_new_rules_version_creates_run_without_rewriting_history(tmp_path,monkeypatch):
    store=Store(tmp_path);data=csv_file([valid_row()])
    first=store.stage(data,'source.csv',as_of=AS_OF)
    original=store.snapshot(first)
    monkeypatch.setattr(config,'RULES_VERSION','next-version')
    second=store.stage(data,'source.csv',as_of=AS_OF)
    assert second!=first
    assert Store(tmp_path).snapshot(first)==original
    assert store.snapshot(second)['run']['rules_version']=='next-version'
