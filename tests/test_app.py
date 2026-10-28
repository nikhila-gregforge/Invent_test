"""HTTP and opt-in Chrome acceptance for direct, fixed-format validation."""
import csv
import os
from io import BytesIO, StringIO
import pytest
from app import create_app
from test_inventory import csv_file, dict_csv, export_csv, valid_row, stage, HEADERS, AS_OF, create_legacy_database

HEAD = {'X-Requested-With':'AIInventory'}


@pytest.fixture
def app(tmp_path,request):
    if getattr(request,'param',False): create_legacy_database(tmp_path)
    application=create_app(tmp_path); application.config['TESTING']=True
    return application


def upload(client,data=None,name='sample.csv',**kwargs):
    data = data if data is not None else csv_file([valid_row(),valid_row('002',Q3=''),valid_row('003',Q12='-1')])
    return client.post('/api/runs',data={'file':(BytesIO(data),name),**kwargs},headers=HEAD)


def test_direct_upload_review_detail_reports_and_restart(app):
    client=app.test_client(); response=upload(client); assert response.status_code==201
    identifier=response.json['id']; result=client.get('/api/runs/'+identifier).json
    assert (result['run']['passed'],result['run']['errors'])==(1,2) and result['matched']==2
    assert all('warnings' not in record and 'response_id' not in record for record in result['records'])
    filtered=client.get('/api/runs/'+identifier+'?status=all&field=business_purpose').json
    assert filtered['matched']==1 and filtered['records'][0]['application_id']=='APP-002'
    detail=client.get(f'/api/runs/{identifier}/records/1').json
    assert detail['record']['cells']['business_purpose']=='' and detail['run']['id']==identifier
    assert detail['record']['findings'][0]['fix']
    report=client.get(f'/api/runs/{identifier}/export?kind=errors&status=all&field=business_purpose')
    rows=list(csv.DictReader(StringIO(report.data.decode('utf-8-sig'))))
    assert report.headers['X-Record-Count']=='1' and {r['Application / System ID'] for r in rows}=={'APP-002'}
    full=client.get(f'/api/runs/{identifier}/export?kind=records&scope=all&field=business_purpose')
    assert full.headers['X-Record-Count']=='3'
    assert upload(client).json['id']==identifier
    restarted=create_app(app.extensions['store'].path.parent).test_client()
    assert restarted.get('/api/runs/'+identifier).json==result


def test_template_rules_and_complete_header_feedback(app):
    client=app.test_client(); template=client.get('/api/template')
    assert template.status_code==200 and template.headers['Content-Disposition'].endswith('ai-inventory-template.csv')
    rows=list(csv.reader(StringIO(template.data.decode('utf-8-sig')))); assert rows==[HEADERS]
    assert upload(client,template.data).status_code==400  # Empty template needs records.
    headers=HEADERS.copy(); headers[0]='Application ID'; headers[1]=HEADERS[2]; headers[3]=''
    response=upload(client,csv_file([valid_row()],headers))
    assert response.status_code==422
    assert response.json['columns']=={'missing':[HEADERS[0],HEADERS[1],HEADERS[3]],'unexpected':['Application ID'],
                                      'duplicates':[HEADERS[2]],'blank_columns':[4]}
    assert not client.get('/api/runs').json['runs']
    rules=client.get('/api/rules').json
    assert [f['label'] for f in rules['fields']]==HEADERS
    assert all('severity' not in check and check['fix'] for f in rules['fields'] for check in f['checks'])
    assert client.post('/api/preview',headers=HEAD).status_code==404


def test_vendor_contact_error_is_counted_once_and_source_filter_is_clear(app):
    client=app.test_client()
    identifier=upload(client,csv_file([valid_row(Q9='Hybrid',Q8='N/A')])).json['id']
    detail=client.get(f'/api/runs/{identifier}/records/0').json['record']
    assert detail['errors']==1 and detail['affected_fields']==['vendor_owner']
    assert detail['field_results']['ai_source']=='No errors'
    assert detail['field_results']['vendor_owner']=='Error'
    assert client.get(f'/api/runs/{identifier}?status=all&field=ai_source').json['matched']==0
    assert client.get(f'/api/runs/{identifier}?status=all&field=vendor_owner').json['matched']==1
    report=client.get(f'/api/runs/{identifier}/export?kind=errors&scope=all')
    rows=list(csv.DictReader(StringIO(report.data.decode('utf-8-sig'))))
    assert len(rows)==1 and rows[0]['Inventory fields']=='Vendor Owner'


def test_delete_review_requires_same_origin_and_removes_all_saved_endpoints(app):
    client=app.test_client()
    first=upload(client).json['id']
    second=upload(client,csv_file([valid_row('kept')])).json['id']
    paths=[f'/api/runs/{first}',f'/api/runs/{first}/records/0',
           f'/api/runs/{first}/analytics',f'/api/runs/{first}/export?kind=records']
    for path in paths: assert client.get(path).status_code==200
    assert client.delete(f'/api/runs/{first}').status_code==403
    assert client.delete(f'/api/runs/{first}',headers={**HEAD,'Origin':'https://untrusted.example'}).status_code==403
    assert len(client.get('/api/runs').json['runs'])==2
    response=client.delete(f'/api/runs/{first}',headers={**HEAD,'Origin':'http://localhost'})
    assert response.status_code==200 and response.json=={'deleted':first}
    for path in paths: assert client.get(path).status_code==404
    assert client.delete(f'/api/runs/{first}',headers=HEAD).status_code==404
    assert [run['id'] for run in client.get('/api/runs').json['runs']]==[second]
    assert client.get(f'/api/runs/{second}').status_code==200


@pytest.mark.parametrize('app',[True],indirect=True)
def test_archived_review_can_be_deleted_from_history(app):
    client=app.test_client()
    assert client.delete('/api/runs/old-run',headers=HEAD).status_code==200
    assert client.get('/api/runs').json['runs']==[]
    assert client.get('/api/runs/old-run').status_code==404


@pytest.mark.parametrize('name',['book.xlsx','book.xls','inventory.ods','report.pdf','data.json',
                                'inventory.txt','inventory.tsv','archive.zip','inventory','inventory.csv.xlsx'])
def test_non_csv_uploads_are_rejected_without_saving(app,name):
    client=app.test_client()
    # Even valid CSV content cannot bypass the file-type restriction.
    response=upload(client,csv_file([valid_row()]),name,sheet='Sheet1')
    assert response.status_code==400
    assert 'Only CSV files are accepted' in response.json['error']
    assert not client.get('/api/runs').json['runs']


@pytest.mark.parametrize('data',[b'PK\x03\x04not CSV',b'%PDF-1.7\nnot CSV',b'{"inventory": []}',
                               ('\t'.join(HEADERS)+'\n').encode()])
def test_non_csv_content_renamed_csv_is_rejected(app,data):
    client=app.test_client()
    response=upload(client,data,'renamed.csv')
    assert response.status_code in {400,422}
    assert not client.get('/api/runs').json['runs']


def test_uppercase_csv_extension_and_missing_file(app):
    client=app.test_client()
    assert upload(client,csv_file([valid_row()]),'INVENTORY.CSV').status_code==201
    response=client.post('/api/runs',headers=HEAD)
    assert response.status_code==400 and response.json['error']=='Choose a CSV file.'


def test_read_only_routes_headers_origins_and_error_privacy(app,caplog,monkeypatch):
    client=app.test_client()
    html=client.get('/'); assert html.status_code==200 and b'streamlit' not in html.data.lower()
    for path in ['/assets/app.js','/assets/charts.js','/assets/style.css','/assets/centene-logo.jpg']:
        response=client.get(path); assert response.status_code==200 and response.headers['X-Content-Type-Options']=='nosniff'
    for path in ['/','/assets/app.js','/assets/style.css']:
        text=client.get(path).data.decode().lower()
        assert all(retired not in text for retired in ['mapping','warnings','needs review','needs attention'])
    assert client.post('/api/runs').status_code==403
    assert client.post('/api/runs',headers={**HEAD,'Origin':'https://untrusted.example'}).status_code==403
    identifier=upload(client).json['id']
    for path in [f'/api/runs/{identifier}/records/0',f'/api/runs/{identifier}/edit',f'/api/runs/{identifier}/commit']:
        for method in ['post','put','patch','delete']:
            assert getattr(client,method)(path,json={'name':'changed'}).status_code in {404,405}
    assert client.get('/api/runs').headers['Cache-Control']=='no-store'
    assert "frame-ancestors 'none'" in html.headers['Content-Security-Policy']
    assert client.get('/api/runs',headers={'Host':'attacker.example'}).status_code==400
    def fail(): raise RuntimeError('SENSITIVE SOURCE VALUE')
    monkeypatch.setattr(app.extensions['store'],'runs',fail)
    response=client.get('/api/runs')
    assert response.status_code==500 and b'SENSITIVE' not in response.data
    assert 'RuntimeError' in caplog.text and 'SENSITIVE' not in caplog.text


def test_errors_pagination_empty_reports_and_limits(app):
    client=app.test_client()
    assert upload(client,b'broken','bad.csv').status_code==422
    assert client.get('/api/runs').json['runs']==[]
    assert client.get('/api/runs/unknown').status_code==404
    identifier=upload(client,csv_file([valid_row(str(i).zfill(3)) for i in range(60)])).json['id']
    page=client.get(f'/api/runs/{identifier}?status=all&page=2&size=25').json
    assert page['matched']==60 and len(page['records'])==25 and page['records'][0]['source_row']==27
    for query in ['page=abc','field=unknown','status=Needs+review','status=attention']:
        assert client.get(f'/api/runs/{identifier}?'+query).status_code==400
    assert client.get(f'/api/runs/{identifier}/records/60').status_code==404
    empty=client.get(f'/api/runs/{identifier}/export?kind=errors&status=Errors')
    assert len(list(csv.reader(StringIO(empty.data.decode('utf-8-sig')))))==1 and empty.headers['X-Record-Count']=='0'
    assert client.get(f'/api/runs/{identifier}/export?kind=fields').status_code==400
    app.config['MAX_CONTENT_LENGTH']=1
    assert upload(client).status_code==413


@pytest.mark.parametrize('app',[True],indirect=True)
def test_archived_routes_require_new_upload_and_do_not_relabel_old_records(app):
    client=app.test_client(); runs=client.get('/api/runs').json['runs']
    assert runs[0]['archived'] and 'passed' not in runs[0] and 'review' not in runs[0]
    for path in ['/api/runs/old-run','/api/runs/old-run/records/0','/api/runs/old-run/export?kind=records']:
        response=client.get(path)
        assert response.status_code==409 and response.json['archived'] and 'upload the file again' in response.json['error']
    assert upload(client).status_code==201 and len(client.get('/api/runs').json['runs'])==2


@pytest.fixture
def browser_app(app):
    if os.getenv('AI_INVENTORY_BROWSER_TESTS')!='1': pytest.skip('Set AI_INVENTORY_BROWSER_TESTS=1 for browser acceptance.')
    from playwright.sync_api import sync_playwright
    from threading import Thread
    from werkzeug.serving import make_server
    server=make_server('127.0.0.1',0,app,threaded=True)
    thread=Thread(target=server.serve_forever,daemon=True); thread.start()
    try:
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True,channel=os.getenv('AI_INVENTORY_BROWSER_CHANNEL') or None)
            context=browser.new_context(viewport={'width':1440,'height':1000},accept_downloads=True)
            page=context.new_page(); errors=[]; page.on('pageerror',lambda error:errors.append(str(error)))
            yield page,context,f'http://127.0.0.1:{server.server_port}',errors
            assert not errors,errors
            browser.close()
    finally:
        server.shutdown(); thread.join(timeout=5); server.server_close()


def choose_upload(page,data,name='sample.csv'):
    page.locator('.upload-trigger').click()
    page.locator('#file').set_input_files({'name':name,'mimeType':'text/csv','buffer':data})
    page.locator('#upload-submit').click()


def test_browser_delete_review_cancel_retry_persistence_and_empty_state(browser_app,app):
    from playwright.sync_api import expect
    first=stage(app.extensions['store'],csv_file([valid_row()]),'first.csv')
    second=stage(app.extensions['store'],csv_file([valid_row('002')]),'second.csv')
    page,context,base,errors=browser_app; page.goto(base)
    first_row=page.locator(f'#history tr[data-run-id="{first}"]')
    first_row.locator('.record-open').click()
    expect(page.locator('#review-content')).to_be_visible()
    page.locator('#home-button').click()
    first_row.locator('.review-delete').click()
    expect(page.locator('#delete-dialog')).to_be_visible()
    expect(page.locator('#delete-message')).to_contain_text('first.csv')
    expect(page.locator('#delete-cancel')).to_be_focused()
    page.locator('#delete-cancel').click()
    expect(page.locator('#history tr')).to_have_count(2)
    assert len(app.extensions['store'].runs())==2
    first_row.locator('.review-delete').click()
    failed=f'**/api/runs/{first}'
    page.route(failed,lambda route:route.fulfill(status=503,json={'error':'Could not delete this review. Retry.'}))
    page.locator('#delete-confirm').click()
    expect(page.locator('#delete-error')).to_have_text('Could not delete this review. Retry.')
    assert len(app.extensions['store'].runs())==2
    expect(page.locator('#delete-confirm')).to_be_enabled()
    page.unroute(failed)
    page.locator('#delete-confirm').click()
    expect(page.locator('#delete-dialog')).not_to_be_visible()
    expect(page.locator('#history tr')).to_have_count(1)
    expect(page.locator('#history')).to_contain_text('second.csv')
    assert page.evaluate("sessionStorage.getItem('inventory-review-4')") is None
    page.reload(); expect(page.locator('#history tr')).to_have_count(1)
    page.set_viewport_size({'width':390,'height':844})
    page.locator('.review-delete').click()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.locator('#delete-confirm').click()
    expect(page.locator('#home-empty')).to_be_visible()
    expect(page.locator('.upload-trigger')).to_be_focused()
    assert app.extensions['store'].runs()==[]
    page.reload(); expect(page.locator('#home-empty')).to_be_visible()


def test_browser_vendor_message_is_not_repeated_under_source(browser_app):
    from playwright.sync_api import expect
    page,context,base,errors=browser_app
    page.goto(base)
    choose_upload(page,csv_file([
        valid_row('vendor',Q9='Hybrid',Q8='N/A'),
        valid_row('platform',Q9='Copilot Studio',Q8='N/A'),
    ]))
    expect(page.locator('#summary')).to_have_text('Total records2Records with errors1Passed1')
    page.locator('#records .record-open').click()
    expect(page.locator('#record-content')).to_be_visible()
    vendor=page.locator('[data-field="vendor_owner"]')
    source=page.locator('[data-field="ai_source"]')
    expect(vendor).to_have_class('field-error')
    expect(vendor).to_contain_text('The selected source indicates vendor involvement')
    expect(vendor).to_contain_text('Enter the vendor contact’s name or email')
    expect(source).not_to_have_class('field-error')
    expect(source).to_contain_text('No errors')
    expect(source.locator('.field-issue')).to_have_count(0)
    expect(page.locator('#source-values .field-issue')).to_have_count(1)
    page.locator('#back-to-results').click()
    page.locator('#status').select_option('Passed')
    expect(page.locator('#records tr')).to_have_count(1)
    page.locator('#records .record-open').click()
    expect(page.locator('#record-title')).to_have_text('Synthetic assistant platform')
    expect(page.locator('#source-values .field-issue')).to_have_count(0)
    expect(page.locator('[data-field="ai_source"] .field-value')).to_have_text('Copilot Studio')


def test_browser_lifecycle_is_visible_unvalidated_and_escaped(browser_app):
    from playwright.sync_api import expect
    page,context,base,errors=browser_app
    page.goto(base)
    raw=dict(zip(HEADERS,valid_row().values()))
    lifecycle='Draft <img src=x onerror="window.injected=1">'
    raw['Lifecycle']=lifecycle
    choose_upload(page,dict_csv([raw]))
    expect(page.locator('#records tr')).to_have_count(1)
    page.locator('#records .record-open').click()
    source=page.locator('[data-source-column="Lifecycle"]')
    expect(source.locator('.field-value')).to_have_text(lifecycle)
    expect(source).to_contain_text('Not validated')
    expect(source.locator('button, img')).to_have_count(0)
    expect(page.locator('#record-status')).to_contain_text('0 errors')
    assert page.evaluate('window.injected') is None


def test_browser_direct_upload_errors_and_download(browser_app,app):
    from playwright.sync_api import expect
    page,context,base,errors=browser_app; page.goto(base)
    expect(page.locator('#home-empty')).to_be_visible(); expect(page.locator('#summary')).to_be_hidden()
    page.locator('.upload-trigger').click()
    with page.expect_download() as downloaded: page.locator('#upload-dialog a[download]').click()
    assert list(csv.reader(StringIO(downloaded.value.path().read_text(encoding='utf-8-sig'))))==[HEADERS]
    page.locator('[data-close="upload-dialog"]').click()
    data=csv_file([valid_row(),valid_row('002',Q3=''),valid_row('003',Q12='-1')])
    choose_upload(page,data)
    expect(page.locator('#review-content')).to_be_visible(); expect(page.locator('#records tr')).to_have_count(2)
    expect(page.locator('#summary')).to_have_text('Total records3Records with errors2Passed1')
    assert page.locator('#status option').all_text_contents()==['All records','Errors','Passed']
    page.locator('#field').select_option('business_purpose'); expect(page.locator('#records tr')).to_have_count(1)
    page.locator('#records tr td').nth(2).click(); expect(page.locator('#record-content')).to_be_visible()
    expect(page.locator('[data-field="business_purpose"]')).to_have_class('field-error')
    expect(page.locator('[data-field="business_purpose"] .field-value')).to_have_text('(blank)')
    expect(page.locator('[data-field="business_purpose"]')).to_contain_text('How to fix: Describe what the system does')
    expect(page.locator('#record-view input, #record-view textarea, #record-view select, #record-view [contenteditable]')).to_have_count(0)
    page.locator('[data-field="business_owner_email"] button').click()
    expect(page.locator('#rules-list')).to_contain_text('any domain')
    expect(page.locator('#rules-list')).to_contain_text('Multiple addresses and surrounding text are accepted')
    page.locator('[data-close="rules-dialog"]').click()
    page.locator('#back-to-results').click(); expect(page.locator('#field')).to_have_value('business_purpose')
    expect(page.locator('#records .record-open')).to_be_focused()
    page.locator('#download-open').click()
    with page.expect_download() as downloaded: page.locator('#errors-download').click()
    rows=list(csv.DictReader(StringIO(downloaded.value.path().read_text(encoding='utf-8-sig'))))
    assert {r['Application / System ID'] for r in rows}=={'APP-002'} and all(r['How to fix'] for r in rows)
    assert all('severity' not in k.lower() for k in rows[0])
    page.locator('#report-scope').select_option('all')
    with page.expect_download() as downloaded: page.locator('#records-download').click()
    assert len(list(csv.DictReader(StringIO(downloaded.value.path().read_text(encoding='utf-8-sig')))))==3
    page.locator('[data-close="report-dialog"]').click()
    page.locator('#clear-filters').click(); expect(page.locator('#records tr')).to_have_count(3)
    page.locator('#status').select_option('Passed'); expect(page.locator('#records tr')).to_have_count(1)
    page.locator('#records tr').click(); expect(page.locator('#record-status')).to_contain_text('All applicable checks passed.')
    page.locator('#home-button').click(); expect(page.locator('#history tr')).to_have_count(1)
    choose_upload(page,data,'renamed.csv'); expect(page.locator('#review-content')).to_be_visible()
    assert len(app.extensions['store'].runs())==1
    choose_upload(page,csv_file([valid_row(),valid_row('002'),valid_row('003')]))
    expect(page.locator('#summary .passed')).to_have_text('Passed3'); expect(page.locator('#records tr')).to_have_count(3)
    # An explicitly selected Errors filter remains selected, even if the file has no errors.
    page.locator('#status').select_option('Errors'); expect(page.locator('#no-results')).to_be_visible()
    expect(page.locator('#status')).to_have_value('Errors')
    assert len(app.extensions['store'].runs())==2


def test_browser_csv_only_header_failures_and_reupload(browser_app,app):
    from playwright.sync_api import expect
    page,context,base,errors=browser_app; page.goto(base)
    choose_upload(page,csv_file([valid_row()]),'book.xlsx')
    expect(page.locator('#file')).to_have_attribute('accept','.csv')
    expect(page.locator('#file-limits')).to_contain_text('CSV only')
    expect(page.locator('#upload-error')).to_contain_text('Only CSV files are accepted')
    expect(page.locator('#upload-dialog')).to_be_visible()
    assert not app.extensions['store'].runs()
    headers=HEADERS.copy(); headers[0]='Application ID'; headers[1]='<img src=x onerror="window.injected=1">'
    page.locator('#file').set_input_files({'name':'headers.csv','mimeType':'text/csv','buffer':csv_file([valid_row()],headers)})
    expect(page.locator('#upload-error')).to_be_hidden()
    page.locator('#upload-submit').click()
    expect(page.locator('#header-errors')).to_be_visible()
    expect(page.locator('#header-errors')).to_contain_text('Missing columns')
    expect(page.locator('#header-errors')).to_contain_text('Unexpected columns')
    expect(page.locator('#header-errors')).to_contain_text('Application / System ID')
    assert not app.extensions['store'].runs() and not page.evaluate('window.injected')
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    # Correct the source externally and replace the file in the same upload dialog.
    page.locator('#file').set_input_files({'name':'corrected.csv','mimeType':'text/csv','buffer':csv_file([valid_row(Q6='',Q12='Auto')])})
    expect(page.locator('#header-errors')).to_be_hidden()
    page.locator('#upload-submit').click(); expect(page.locator('#records tr')).to_have_count(1)
    page.locator('#records .record-open').click(); expect(page.locator('#record-content')).to_be_visible()
    expect(page.locator('[data-field="business_owner_email"]')).to_contain_text('any domain')
    expect(page.locator('[data-field="llm_count"]')).to_contain_text('How to fix: Count the actual models used')
    expect(page.locator('#not-checked')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.set_viewport_size({'width':1440,'height':1000})
    choose_upload(page,csv_file([valid_row()]),'corrected.CSV')
    expect(page.locator('#summary .passed')).to_have_text('Passed1')


def test_browser_record_navigation_retry_and_html_safety(browser_app,app):
    from playwright.sync_api import expect
    page,context,base,errors=browser_app
    rows=[valid_row(str(i).zfill(3),Q3='') for i in range(1,31)]
    literal='<img src=x onerror="window.injected=1">'; rows[25]['Q2']=literal
    identifier=stage(app.extensions['store'],csv_file(rows),'browser.csv')
    page.goto(base+f'/#run/{identifier}'); expect(page.locator('#records tr')).to_have_count(25)
    page.locator('#field').select_option('business_purpose'); expect(page.locator('#results-loading')).to_be_hidden()
    page.locator('#next').click(); expect(page.locator('#page-info')).to_have_text('Page 2 of 2')
    expect(page.locator('#records tr')).to_have_count(5)
    for column in range(4):
        page.locator('#records tr').first.locator('td').nth(column).click(position={'x':6,'y':6})
        expect(page.locator('#record-content')).to_be_visible(); expect(page.locator('#record-title')).to_have_text(literal)
        assert not page.evaluate('window.injected')
        page.locator('#back-to-results').click(); expect(page.locator('#page-info')).to_have_text('Page 2 of 2')
        expect(page.locator('#records tr').first.locator('.record-open')).to_be_focused()
    page.keyboard.press('Enter'); expect(page.locator('#record-content')).to_be_visible(); record_url=page.url
    page.go_back(); expect(page.locator('#review-content')).to_be_visible()
    page.go_forward(); expect(page.locator('#record-content')).to_be_visible()
    page.reload(); expect(page.locator('#record-title')).to_have_text(literal)
    page.set_viewport_size({'width':390,'height':844}); assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.locator('#back-to-results').click(); expect(page.locator('#page-info')).to_have_text('Page 2 of 2')
    page.set_viewport_size({'width':1440,'height':1000})
    detail=f'**/api/runs/{identifier}/records/25'
    page.route(detail,lambda route:route.fulfill(status=503,json={'error':'Temporary review failure.'}))
    page.locator('#records tr').first.click(); expect(page.locator('#record-error-message')).to_have_text('Temporary review failure.')
    page.unroute(detail); page.locator('#record-retry').click(); expect(page.locator('#record-content')).to_be_visible()
    direct=context.new_page(); direct.goto(record_url); expect(direct.locator('#record-title')).to_have_text(literal)
    direct.goto(base+f'/#run/{identifier}/record/999'); expect(direct.locator('#record-error-message')).to_have_text('Record not found.')
    page.locator('#back-to-results').click(); page.locator('#clear-filters').click()
    page.locator('#search').fill('APP-005'); expect(page.locator('#records tr')).to_have_count(1)
    expect(page.locator('#records')).to_contain_text('APP-005')


@pytest.mark.parametrize('app',[True],indirect=True)
def test_browser_archive_notice_preserves_historical_meaning(browser_app,app):
    from playwright.sync_api import expect
    page,context,base,errors=browser_app; page.goto(base)
    expect(page.locator('#history')).to_contain_text('Upload again to review')
    expect(page.locator('#history .badge')).to_have_count(0)
    page.locator('#history tr').click(); expect(page.locator('#archived-review')).to_be_visible()
    expect(page.locator('#archived-message')).to_contain_text('original upload and results are preserved')
    expect(page.locator('#review-content')).to_be_hidden(); expect(page.locator('#download-open')).to_be_disabled()
    page.goto(base+'/#run/old-run/record/0'); expect(page.locator('#record-error')).to_be_visible()
    expect(page.locator('#record-retry')).to_be_hidden()
    choose_upload(page,csv_file([valid_row(Q6='owner@centene.com',Q20='Unknown')]))
    expect(page.locator('#summary .passed')).to_have_text('Passed1')
    expect(page.locator('#records')).to_contain_text('Passed')
    page.locator('#home-button').click(); expect(page.locator('#history tr')).to_have_count(2)


def test_browser_charts_scopes_counts_and_export_layout(browser_app,app):
    from pathlib import Path
    from playwright.sync_api import expect
    page,context,base,errors=browser_app; page.goto(base)
    rows=[valid_row('1',Q20='High',Q18='Medicaid, Medicare',Q3=''),
          valid_row('2',Q20='Medium',Q18='Medicare',Q16='Pilot',Q17=''),
          valid_row('3',Q20='Unknown',Q18='Commercial',Q16='Development',Q17='')]
    choose_upload(page,export_csv(rows),'Centene AI Inventory.csv')
    expect(page.locator('#inventory-error-count')).to_contain_text('Result: 1 of 3 records')
    expect(page.locator('#charts-content')).to_be_visible()
    expect(page.locator('#charts-context')).to_contain_text('Entire file · 3 application records')
    expect(page.locator('#primary-charts article')).to_have_count(3)
    risk=page.locator('[data-chart="risk_tier"]')
    expect(risk).to_contain_text('33.3%'); expect(risk).to_contain_text('Unknown')
    lob=page.locator('[data-chart="lines_of_business"]')
    expect(lob.locator('.chart-bars')).to_be_visible()
    expect(lob.locator('.pie-chart')).to_have_count(0)
    expect(lob).to_contain_text('3 records · % of records')
    expect(lob).to_contain_text('2 · 66.7%')
    expect(lob).not_to_contain_text('% of selections')
    screenshot_dir=os.getenv('AI_INVENTORY_SCREENSHOT_DIR')
    if screenshot_dir:
        destination=Path(screenshot_dir); destination.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(destination/'inventory-overview-desktop.png'),full_page=True)
    page.locator('#more-charts summary').click()
    page.locator('#extra-chart-field').select_option('ai_types')
    expect(page.locator('#extra-chart .chart-bars')).to_be_visible()
    expect(page.locator('#extra-chart')).to_contain_text('3 · 100%')
    page.locator('#chart-scope').select_option('filtered')
    expect(page.locator('#charts-context')).to_contain_text('Current filters, across all pages · 1 application records')
    expect(risk).to_contain_text('100%')
    page.locator('#clear-filters').click()
    expect(page.locator('#charts-context')).to_contain_text('Current filters, across all pages · 3 application records')
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    if screenshot_dir: page.screenshot(path=str(destination/'inventory-overview-mobile.png'),full_page=True)
    page.locator('#search').fill('no-such-record')
    expect(page.locator('#charts-context')).to_contain_text('0 application records')
    expect(page.locator('#primary-charts .chart-empty')).to_have_count(3)
    expect(page.locator('#primary-charts')).not_to_contain_text('NaN')
    page.locator('#chart-scope').select_option('all')
    expect(page.locator('#charts-context')).to_contain_text('Entire file · 3 application records')


def test_browser_nested_charts_keep_paths_in_records_and_downloads(browser_app,app,tmp_path):
    from playwright.sync_api import expect
    page,context,base,errors=browser_app
    identifier=stage(app.extensions['store'],csv_file([
        valid_row('1',Q20='High',Q18='Medicaid;Medicare'),
        valid_row('2',Q20='High',Q18='Medicaid',Q16='Pilot',Q17=''),
        valid_row('3',Q20='Low',Q18='Medicaid'),
        valid_row('4',Q20='High',Q18='Commercial'),
    ]))
    requests=[]; page.on('request',lambda req:requests.append(req.url))
    page.goto(base+'/#run/'+identifier)
    expect(page.locator('#charts-content')).to_be_visible()
    page.locator('#more-charts > summary').click()
    page.locator('#extra-chart-field').select_option('risk_tier')
    page.locator('#add-chart-field').click()
    page.locator('#breakdown-chart-field').select_option('lines_of_business')
    table=page.locator('#extra-chart .comparison-table')
    expect(table).to_be_visible()
    expect(page.locator('#extra-chart .chart-bars')).to_have_count(0)
    expect(table.locator('tfoot .comparison-total')).to_have_text('4')
    page.locator('#add-chart-field').click()
    page.locator('#nested-chart-field-3').select_option('deployment_status')
    expect(table.locator('tbody tr')).to_have_count(2)
    branch_route='**/analytics?*group_by=lines_of_business*'
    page.route(branch_route,lambda route:route.fulfill(status=503,json={'error':'Temporary chart failure.'}))
    page.get_by_role('button',name='Expand Risk tier: High',exact=True).click()
    expect(table).to_contain_text('Temporary chart failure.')
    page.unroute(branch_route)
    table.get_by_role('button',name='Retry',exact=True).click()
    expect(table.locator('tr[data-depth="1"]')).to_have_count(3)
    expect(table.locator('tfoot .comparison-total')).to_have_text('4')
    # Overlapping LOB groups have five memberships but only four source records.
    page.locator('#add-chart-field').click()
    page.locator('#nested-chart-field-4').select_option('human_oversight')
    page.get_by_role('button',name='Expand Risk tier: High',exact=True).click()
    page.get_by_role('button',name='Expand Risk tier: High / Line of business: Medicaid',exact=True).click()
    expect(table.locator('tr[data-depth="2"]')).to_have_count(2)
    active=table.locator('tr[data-depth="2"]').filter(has_text='Active')
    active.locator('.comparison-value').click()
    expect(page.locator('dialog[open] [role="status"]')).to_contain_text('1 matching records')
    expect(page.locator('dialog[open] tbody')).to_contain_text('APP-1')
    expect(page.locator('dialog[open] tbody')).not_to_contain_text('APP-3')
    page.get_by_role('button',name='Close',exact=True).click()
    with page.expect_download() as downloaded:
        page.get_by_role('button',name='Download table (CSV)').click()
    rows=list(csv.DictReader(StringIO(open(downloaded.value.path(),encoding='utf-8-sig').read())))
    assert rows[-1]['Row type']=='Distinct total' and rows[-1]['Unique records']=='4'
    assert any(row['Row type']=='Final group' and row['Unique records']=='1' and
               'Risk tier: High / Line of business: Medicaid / Deployment status: Active' in row['Group path'] for row in rows)
    active.locator('.comparison-show-chart').click()
    with page.expect_download() as downloaded:
        page.locator('.comparison-chart-dialog').get_by_role('button',name='Download chart (PNG)').click()
    image=tmp_path/'chart.png'; downloaded.value.save_as(image)
    assert image.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
    assert int.from_bytes(image.read_bytes()[16:20],'big')==2400
    page.locator('.comparison-chart-dialog').get_by_role('button',name='View underlying records').click()
    page.locator('dialog[open] tbody a').click()
    expect(page.locator('#record-content')).to_be_visible()
    expect(page.locator('dialog[open]')).to_have_count(0)
    page.locator('#back-to-results').click()
    expect(table).to_be_visible()
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.locator('#remove-chart-field').click()
    expect(page.locator('#nested-chart-field-4')).to_have_count(0)
    expect(table.locator('tfoot .comparison-total')).to_have_text('4')
    page.locator('#remove-chart-field').click()
    expect(table.locator('.comparison-expand')).to_have_count(0)
    # A selected category changes the footer's scope, not just the visible rows.
    page.locator('#comparison-category').select_option('High')
    expect(table.locator('tfoot .comparison-total')).to_have_text('3')
    expect(table.locator('tfoot th')).to_have_text('Unique records in selected category')
    assert len([url for url in requests if '/analytics?' in url and 'comparison_only' not in url])==1
    page.locator('#comparison-values').select_option('portfolio')
    expect(table.locator('tbody .comparison-percent').first).to_have_text('50%')
    expect(page.locator('#extra-chart')).to_contain_text('Percentages use all 4 products in the file')
    with page.expect_download() as downloaded:
        page.get_by_role('button',name='Download table (CSV)').click()
    rows=list(csv.DictReader(StringIO(open(downloaded.value.path(),encoding='utf-8-sig').read())))
    assert all(row['Percentage denominator']=='4' for row in rows)
    assert float(rows[0]['Medicaid | % of all products'])==50
    page.locator('#search').fill('APP-1')
    expect(page.locator('#record-count')).to_contain_text('of 1 records')
    page.locator('#chart-scope').select_option('filtered')
    expect(page.locator('#charts-context')).to_contain_text('1 application records')
    expect(table.locator('tbody .comparison-percent').first).to_have_text('25%')
    expect(table.locator('tfoot .comparison-total')).to_have_text('1')
