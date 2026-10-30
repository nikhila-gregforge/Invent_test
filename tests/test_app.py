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


def test_browser_five_level_drilldown_and_slide_export(browser_app,app,tmp_path):
    from playwright.sync_api import expect
    page,context,base,errors=browser_app
    vendor={'Q9':'Licensed from third-party vendor (customized)','Q8':'Vendor contact'}
    identifier=stage(app.extensions['store'],csv_file([
        valid_row('1',Q20='High',Q18='Medicaid;Medicare'),
        valid_row('2',Q20='High',Q18='Medicaid',Q16='Pilot',Q17='',Q21='No',**vendor),
        valid_row('3',Q20='High',Q18='Medicare',**vendor),
        valid_row('4',Q20='Low',Q18='Medicaid'),
    ]))
    page.goto(base+'/#run/'+identifier)
    expect(page.locator('#charts-content')).to_be_visible()
    page.locator('#more-charts > summary').click()
    page.locator('#extra-chart-field').select_option('risk_tier')
    for index,field in enumerate(['lines_of_business','deployment_status','human_oversight','ai_source_group'],2):
        page.locator('#add-chart-field').click()
        page.locator('#breakdown-chart-field' if index==2 else '#nested-chart-field-'+str(index)).select_option(field)
        expect(page.locator('.analysis-level')).to_have_count(index)
        if index==2:
            page.get_by_role('button',name='Drill into Line of business: Medicare',exact=True).click()
    board=page.locator('.analysis-board')
    expect(board).to_have_attribute('data-levels','5')
    expect(page.locator('#add-chart-field')).to_be_hidden()
    expect(page.locator('#nested-chart-field-6')).to_have_count(0)
    expect(board.locator('table')).to_have_count(5)
    expect(board.locator('.analysis-level[data-level="3"] .analysis-level-context')).to_have_text('Within Medicare · 2 records')
    expect(board.locator('.analysis-path-step').nth(1)).to_contain_text('Medicare')
    page.get_by_role('button',name='Drill into AI source group: Vendor AI',exact=True).click()
    source=board.locator('.analysis-level[data-level="5"]')
    source.get_by_role('button',name='View 1 record for AI source group: Vendor AI',exact=True).click()
    expect(page.locator('dialog[open] [role="status"]')).to_contain_text('1 matching records')
    expect(page.locator('dialog[open] tbody')).to_contain_text('APP-3')
    expect(page.locator('dialog[open] tbody')).not_to_contain_text('APP-1')
    expect(page.locator('dialog[open] tbody')).not_to_contain_text('APP-2')
    page.get_by_role('button',name='Close',exact=True).click()
    with page.expect_download() as downloaded:
        page.get_by_role('button',name='Download data (CSV)').click()
    rows=list(csv.DictReader(StringIO(open(downloaded.value.path(),encoding='utf-8-sig').read())))
    chosen=next(row for row in rows if row['Level']=='5' and row['Selected on path']=='Yes')
    assert chosen['Category']=='Vendor AI' and chosen['Records']=='1'
    assert chosen['Parent path']=='Risk tier: High / Line of business: Medicare / Deployment status: Active / Human oversight: Yes'
    assert all(row['Percentage denominator']=='4' for row in rows)
    assert float(chosen['Percent'])==25
    with page.expect_download() as downloaded:
        page.get_by_role('button',name='Export slide (PNG)').click()
    image=tmp_path/'slide.png';downloaded.value.save_as(image)
    raw=image.read_bytes()
    assert raw.startswith(b'\x89PNG\r\n\x1a\n')
    assert int.from_bytes(raw[16:20],'big')==1920 and int.from_bytes(raw[20:24],'big')==1080
    assert len(raw)>25000
    page.locator('#comparison-values').select_option('row')
    medicare=board.locator('.analysis-level[data-level="2"] tr[data-category="Medicare"]')
    expect(medicare.locator('td').last).to_have_text('66.7%')
    with page.expect_download() as downloaded:
        page.get_by_role('button',name='Download data (CSV)').click()
    rows=list(csv.DictReader(StringIO(open(downloaded.value.path(),encoding='utf-8-sig').read())))
    chosen=next(row for row in rows if row['Level']=='5' and row['Selected on path']=='Yes')
    assert chosen['Percentage denominator']=='2' and float(chosen['Percent'])==50
    page.get_by_role('button',name='Drill into Risk tier: Low',exact=True).click()
    expect(board.locator('.analysis-level[data-level="2"] .analysis-level-context')).to_have_text('Within Low · 1 record')
    expect(board.locator('.analysis-path-step').last).to_contain_text('Developed in-house')
    board.locator('.analysis-level[data-level="5"]').get_by_role('button',name='View 1 record for AI source group: Developed in-house',exact=True).click()
    expect(page.locator('dialog[open] tbody')).to_contain_text('APP-4')
    page.get_by_role('button',name='Close',exact=True).click()
    page.locator('#remove-chart-field').click()
    expect(board.locator('.analysis-level')).to_have_count(4)
    expect(page.locator('#add-chart-field')).to_be_visible()
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')


def test_browser_drilldown_pages_chart_context_and_filtered_denominators(browser_app,app,tmp_path):
    from playwright.sync_api import expect
    page,context,base,errors=browser_app
    lobs=['Medicaid','Medicare','Marketplace','Commercial','Employer Groups','Pharmacy','None']
    rows=[valid_row(str(index+1),Q18=lob) for index,lob in enumerate(lobs)]
    rows.append(valid_row('8',Q18='Medicaid',Q9='Vendor built',Q8='Vendor contact',Q16='Pilot',Q17=''))
    identifier=stage(app.extensions['store'],csv_file(rows))
    requests=[];page.on('request',lambda req:requests.append(req.url))
    page.goto(base+'/#run/'+identifier)
    expect(page.locator('#charts-content')).to_be_visible()
    page.locator('#more-charts > summary').click()
    page.locator('#extra-chart-field').select_option('lines_of_business')
    for index,field in enumerate(['ai_source_group','deployment_status','human_oversight','risk_tier'],2):
        page.locator('#add-chart-field').click()
        page.locator('#breakdown-chart-field' if index==2 else '#nested-chart-field-'+str(index)).select_option(field)
        expect(page.locator('.analysis-level')).to_have_count(index)
    board=page.locator('.analysis-board');level=board.locator('.analysis-level[data-level="1"]')
    expect(level.locator('.analysis-pagination')).to_contain_text('1–3 of 7')
    page.get_by_role('button',name='Next categories in Line of business',exact=True).click()
    expect(level.locator('.analysis-pagination')).to_contain_text('4–6 of 7')
    expect(level.locator('.analysis-axis')).to_contain_text('selection on page 1')
    expect(board.locator('.analysis-path-step').first).to_contain_text('Medicaid')
    with page.expect_download() as downloaded:
        page.get_by_role('button',name='Download data (CSV)').click()
    exported=list(csv.DictReader(StringIO(open(downloaded.value.path(),encoding='utf-8-sig').read())))
    first=[row for row in exported if row['Level']=='1']
    assert len(first)==7 and sum(row['Visible in PNG']=='Yes' for row in first)==3
    assert next(row for row in first if row['Selected on path']=='Yes')['Visible in PNG']=='No'
    page.get_by_role('button',name='View Line of business chart for all records',exact=True).click()
    dialog=page.locator('.comparison-chart-dialog')
    expect(dialog.locator('.chart-card')).to_have_attribute('data-chart','lines_of_business')
    with page.expect_download() as downloaded:
        dialog.get_by_role('button',name='Download summary (CSV)').click()
    exported=list(csv.DictReader(StringIO(open(downloaded.value.path(),encoding='utf-8-sig').read())))
    assert len(exported)==7 and all(row['Denominator']=='8' for row in exported)
    dialog.get_by_role('button',name='View underlying records').click()
    page.locator('dialog[open]').last.locator('select').select_option('Medicaid')
    expect(page.locator('dialog[open]').last.locator('[role="status"]')).to_contain_text('2 matching records')
    page.locator('dialog[open]').last.locator('tbody a').first.click()
    expect(page.locator('#record-content')).to_be_visible()
    expect(page.locator('dialog[open]')).to_have_count(0)
    page.locator('#back-to-results').click()
    expect(board).to_be_visible()
    expect(level.locator('.analysis-pagination')).to_contain_text('4–6 of 7')
    assert len([url for url in requests if '/analytics?' in url])==1
    page.locator('#search').fill('APP-1')
    expect(page.locator('#record-count')).to_contain_text('of 1 records')
    page.locator('#chart-scope').select_option('filtered')
    expect(page.locator('#charts-context')).to_contain_text('1 application records')
    expect(board.locator('.analysis-metrics > div').first.locator('strong')).to_have_text('1')
    expect(board.locator('.analysis-level[data-level="1"] tr[data-category="Medicaid"] td').last).to_have_text('12.5%')
    with page.expect_download() as downloaded:
        page.get_by_role('button',name='Download data (CSV)').click()
    exported=list(csv.DictReader(StringIO(open(downloaded.value.path(),encoding='utf-8-sig').read())))
    assert all(row['Percentage denominator']=='8' for row in exported)
    page.locator('#search').fill('no-such-record')
    expect(page.locator('#charts-context')).to_contain_text('0 application records')
    expect(page.get_by_role('button',name='Export slide (PNG)')).to_be_disabled()
    expect(board).to_contain_text('No matching records')


def test_browser_comparison_shows_distinct_flagged_records_and_concentration(browser_app,app):
    from playwright.sync_api import expect
    page,context,base,errors=browser_app
    identifier=stage(app.extensions['store'],csv_file([
        valid_row('1',Q20='High',Q11='Invalid',Q12='Invalid',Q6='<b>Business owner</b>',Q7='=Technical owner'),
        valid_row('2',Q20='High'),
        valid_row('3',Q20='High',Q9='Vendor built',Q8='N/A'),
        valid_row('4',Q20='Low',Q19='None;California'),
    ]))
    page.goto(base+'/#run/'+identifier)
    expect(page.locator('#charts-content')).to_be_visible()
    page.locator('#more-charts > summary').click()
    page.locator('#extra-chart-field').select_option('risk_tier')
    page.locator('#add-chart-field').click()
    page.locator('#breakdown-chart-field').select_option('ai_source_group')
    concentration=page.locator('.validation-concentration')
    expect(concentration.locator('.validation-concentration-total strong')).to_have_text('3')
    expect(concentration.locator('[data-group="counts"] strong')).to_have_text('1')
    expect(concentration.locator('.validation-concentration-detail')).to_contain_text('4 finding instances')
    first=page.locator('.analysis-level[data-level="1"] tr[data-category="High"]')
    expect(first.locator('.analysis-count')).to_have_text('3')
    expect(first.locator('.analysis-flagged-count')).to_have_text('2')
    first.get_by_role('button',name='View 2 records with findings for Risk tier: High',exact=True).click()
    expect(page.locator('dialog[open] [role="status"]')).to_contain_text('2 matching records')
    expect(page.locator('dialog[open] tbody')).to_contain_text('APP-1')
    expect(page.locator('dialog[open] tbody')).to_contain_text('APP-3')
    expect(page.locator('dialog[open] tbody')).not_to_contain_text('APP-2')
    page.get_by_role('button',name='Close',exact=True).click()
    page.locator('#validation-scope').select_option('path')
    expect(concentration.locator('.validation-concentration-scope')).to_have_text('Selected path · 2 records')
    expect(concentration.locator('.validation-concentration-total strong')).to_have_text('1')
    page.locator('#validation-grouping').select_option('rules')
    expect(concentration.locator('[data-group="COUNT-01"] strong')).to_have_text('1')
    page.locator('#validation-grouping').select_option('columns')
    expect(concentration.locator('[data-group="llm_count"] strong')).to_have_text('1')
    expect(concentration.locator('[data-group="ml_dl_count"] strong')).to_have_text('1')
    with page.expect_download() as downloaded:
        page.get_by_role('button',name='Download data (CSV)').click()
    rows=list(csv.DictReader(StringIO(open(downloaded.value.path(),encoding='utf-8-sig').read())))
    fields=[row for row in rows if row['Row type']=='Validation concentration']
    assert len(fields)==2 and all(row['Records']=='1' for row in fields)
    assert all(row['Concentration scope']=='Selected path' for row in fields)
    assert all(row['Percentage denominator']=='4' for row in fields)
    page.get_by_role('button',name='Review selected records',exact=True).click()
    queue=page.locator('.correction-queue-dialog[open]')
    expect(queue.locator('[role="status"]')).to_contain_text('2 matching records')
    expect(queue.locator('.correction-queue-context')).to_contain_text('Risk tier: High / AI source group: Developed in-house')
    expect(queue.locator('.correction-queue-baseline')).to_contain_text('File baseline: 4 records')
    expect(queue.locator('tbody')).to_contain_text('<b>Business owner</b>')
    expect(queue.locator('tbody b')).to_have_count(0)
    expect(queue.locator('tbody')).to_contain_text('LLM Count')
    expect(queue.locator('tbody')).to_contain_text('No current validation correction required.')
    with page.expect_download() as downloaded:
        queue.get_by_role('button',name='Download selected records (CSV)',exact=True).click()
    records=list(csv.DictReader(StringIO(open(downloaded.value.path(),encoding='utf-8-sig').read())))
    assert {row['Application / System ID'] for row in records}=={'APP-1','APP-2'}
    assert all(row['Selected records']=='2' and row['File baseline records']=='4' for row in records)
    assert all(row['Selected path']=='Risk tier: High / AI source group: Developed in-house' for row in records)
    flagged=next(row for row in records if row['Application / System ID']=='APP-1')
    assert flagged['Business Owner']=='<b>Business owner</b>' and flagged['Technical Owner']=="'=Technical owner"
    assert set(flagged['AI Inventory columns'].split('; '))=={'LLM Count','ML/DL Models Count'}
    assert flagged['Rule IDs']=='COUNT-01' and flagged['Required actions'].count('COUNT-01:')==2
    assert 'Invalid' in flagged['Submitted values'] and flagged['Requirements']
    queue.get_by_role('button',name='Close',exact=True).click()
    page.locator('#validation-grouping').select_option('families')
    concentration.locator('[data-group="counts"]').click()
    queue=page.locator('.correction-queue-dialog[open]')
    expect(queue.locator('[role="status"]')).to_contain_text('1 matching records')
    expect(queue.locator('.correction-queue-context')).to_contain_text('Risk tier: High / AI source group: Developed in-house')
    with page.expect_download() as downloaded:
        queue.get_by_role('button',name='Download selected records (CSV)',exact=True).click()
    records=list(csv.DictReader(StringIO(open(downloaded.value.path(),encoding='utf-8-sig').read())))
    assert len(records)==1 and records[0]['Application / System ID']=='APP-1'
    assert records[0]['Selected records']=='1' and records[0]['Rule IDs']=='COUNT-01'
    queue.get_by_role('link',name='Synthetic assistant 1',exact=True).click()
    expect(page.locator('#source-values')).to_contain_text('How to fix:')
    page.locator('#back-to-results').click()
    expect(page.locator('.analysis-path')).to_contain_text('Developed in-house')
