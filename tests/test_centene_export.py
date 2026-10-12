"""Exact export-layout support without guessing arbitrary headers or cell values."""
import csv
from io import BytesIO, StringIO
import pytest
import inventory as config
from app import create_app
from inventory.ingestion import parse_file, HeaderMismatch
from inventory.validation import validate_upload
from test_inventory import AS_OF, valid_row, csv_file, export_csv, dict_csv, validate, rules


@pytest.mark.parametrize('lifecycle', ['', 'Active', 'Unrecognized lifecycle', 'Draft, pending\n"Review" — <b>source text</b>'])
@pytest.mark.parametrize('layout', ['template', 'export'])
def test_lifecycle_is_retained_without_validation_in_detail_reports_and_restart(tmp_path, lifecycle, layout):
    row = valid_row(Q12='-1')
    baseline = validate_upload(parse_file(csv_file([row]), 'baseline.csv'), AS_OF)['records'][0]
    raw = parse_file((csv_file if layout == 'template' else export_csv)([row]), 'source.csv').rows[0]['values']
    raw['Lifecycle'] = lifecycle
    data = dict_csv([dict(reversed(list(raw.items())))])
    app = create_app(tmp_path)
    client = app.test_client()
    response = client.post('/api/runs', headers={'X-Requested-With': 'AIInventory'},
                           data={'file': (BytesIO(data), 'inventory.csv')})
    assert response.status_code == 201
    identifier = response.json['id']
    detail_url = f'/api/runs/{identifier}/records/0'
    detail = client.get(detail_url).json
    record = detail['record']
    assert record['source_values']['Lifecycle'] == record['extra_values']['Lifecycle'] == lifecycle
    assert record['findings'] == baseline['findings']
    assert record['cells'] == baseline['cells']
    assert all(field['label'] != 'Lifecycle' for field in detail['fields'])
    report = client.get(f'/api/runs/{identifier}/export?kind=records&scope=all')
    exported = next(csv.DictReader(StringIO(report.data.decode('utf-8-sig'))))
    assert exported['Source: Lifecycle'] == lifecycle
    assert create_app(tmp_path).test_client().get(detail_url).json == detail


def test_export_layout_maps_all_fields_and_preserves_metadata_and_source_order():
    row=valid_row(Q18='Medicaid, Medicare',Q10='GenAI, LLM',Q6='Alex <alex@centene.com> (primary)')
    parsed=parse_file(export_csv([row]),'Centene AI Inventory.csv')
    assert parsed.layout=='centene-export' and len(parsed.columns)==25
    data=validate_upload(parsed,AS_OF); record=data['records'][0]
    assert record['status']=='Passed'
    assert record['cells']=={field:row[q] for q,field in config.FIELDS.items()}
    assert record['source_values']['Lifecycle']=='Export metadata'
    assert record['source_values']['User AIS']=='Export metadata'
    assert record['normalized']['lines_of_business']==['Medicaid','Medicare']
    raw=parsed.rows[0]['values']
    reordered=parse_file(dict_csv([dict(reversed(list(raw.items())))]),'export.csv')
    assert validate_upload(reordered,AS_OF)['records']==data['records']


def test_export_layout_does_not_accept_missing_extra_or_mixed_headers():
    raw=parse_file(export_csv([valid_row()]),'export.csv').rows[0]['values']
    for changed in [{k:v for k,v in raw.items() if k!='Lifecycle'},
                    {**raw,'Extra':'value'},
                    {('Application / System ID' if k=='AI System ID' else k):v for k,v in raw.items()}]:
        with pytest.raises(HeaderMismatch): parse_file(dict_csv([changed]),'export.csv')


@pytest.mark.parametrize('functions',[
    'Fraud, Waste, & Abuse Detection, Claims Processing',
    'Claims Processing; Fraud, Waste, & Abuse Detection',
    'Fraud, Waste, & Abuse Detection',
])
def test_comma_selections_preserve_commas_inside_official_choices(functions):
    product,findings,_=validate(Q4=functions)
    assert not findings and 'Fraud, Waste, & Abuse Detection' in product['business_functions']


def test_decorated_choices_and_descriptive_override_text():
    product,findings,_=validate(Q16='Active = Currently operational: Post-Deployment',
                               Q21='Yes – Human oversight includes override capability',
                               Q10='GenAI = text generation, LLM',
                               Q14='Other: Internal warehouse, reporting tables')
    assert not findings
    assert product['deployment_status']=='Active' and product['human_oversight']=='Yes'
    assert product['ai_types']==['Generative AI (GenAI)','Large Language Model (LLM)']
    assert product['other_details']['data_environments']=='Internal warehouse, reporting tables'
    assert not validate(Q21='Yes; Override: Maybe')[1]
    assert not validate(Q10='LLM, Unsupported model')[1]


def test_export_upload_and_download_keep_raw_25_columns(tmp_path):
    app=create_app(tmp_path); client=app.test_client(); data=export_csv([valid_row()])
    response=client.post('/api/runs',headers={'X-Requested-With':'AIInventory'},
                         data={'file':(BytesIO(data),'Centene AI Inventory.csv')})
    assert response.status_code==201
    identifier=response.json['id']
    result=client.get('/api/runs/'+identifier).json
    assert result['run']['input_layout']=='centene-export' and result['run']['passed']==1
    assert result['inventory_error_records']==0
    report=client.get(f'/api/runs/{identifier}/export?kind=records&scope=all')
    row=next(csv.DictReader(StringIO(report.data.decode('utf-8-sig'))))
    assert row['Source: AI System ID']=='APP-001'
    assert row['Source: Lifecycle']=='Export metadata' and row['Source: User AIS']=='Export metadata'


def test_export_owner_names_are_accepted_and_metadata_is_preserved():
    row=valid_row(Q6='Alex Smith',Q7='Taylor Jones')
    raw=parse_file(export_csv([row]),'export.csv').rows[0]['values']
    raw['User AIS']='Contact: taylor@centene.com'
    record=validate_upload(parse_file(dict_csv([raw]),'export.csv'),AS_OF)['records'][0]
    assert record['status']=='Passed'
    assert record['extra_values']['User AIS']=='Contact: taylor@centene.com'


def test_comma_whitespace_html_entities_and_unambiguous_aliases():
    row=valid_row(Q4='Clinical Decision Support , Enrollment',
        Q14='Snowflake , Teradata, Electronic Medical Record (EMR)',
        Q13='Provider data (e.g., provider directories, credentialing data), Contains PHI',
        Q19='Alabama , Arizona, AK',Q15='On-premise',
        Q16='Plan &amp; Design',Q21='Conditional (exception threshold)',
        Q10='GenAI&#58; text generation, LLM')
    record=validate_upload(parse_file(export_csv([row]),'export.csv'),AS_OF)['records'][0]
    assert record['status']=='Passed'
    product=record['normalized']
    assert product['data_environments']==['Snowflake','Teradata','EMR']
    assert product['states']==['Alabama','Arizona','Alaska']
    assert product['human_oversight']=='Partially'
    assert product['data_types']==['Provider data','Contains PHI']
    assert record['source_values']['Type(s) of AI Used']=='GenAI&#58; text generation, LLM'
