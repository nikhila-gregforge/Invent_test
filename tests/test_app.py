"""HTTP and opt-in Chrome acceptance tests with isolated synthetic data."""
import csv
import os
from io import BytesIO, StringIO
import pytest
from app import create_app
from test_inventory import csv_file, valid_row, dict_csv, xlsx_file, choices, stage, HEADERS, AS_OF

HEAD = {'X-Requested-With':'AIInventory'}


@pytest.fixture
def app(tmp_path):
    application=create_app(tmp_path); application.config['TESTING']=True
    return application


def upload(client,data=None,name='sample.csv',**kwargs):
    data = data if data is not None else csv_file([valid_row(),valid_row('002',Q3='test'),valid_row('003',Q20='Unknown')])
    preview=client.post('/api/preview',data={'file':(BytesIO(data),name),**kwargs},headers=HEAD)
    if preview.status_code!=200: return preview
    import json
    metadata=preview.json
    return client.post('/api/runs',data={'file':(BytesIO(data),name),'mapping':json.dumps({f:c or None for f,c in metadata['mapping'].items()}),
        'file_hash':metadata['file_hash'],'rules_version':metadata['rules_version'],**kwargs},headers=HEAD)


def test_upload_mapping_review_detail_reports_and_restart(app):
    client=app.test_client(); response=upload(client); assert response.status_code==201
    identifier=response.json['id']; result=client.get('/api/runs/'+identifier).json
    assert (result['run']['passed'],result['run']['review'],result['run']['failed'])==(1,1,1)
    assert result['matched']==2 and 'statistics' not in result
    filtered=client.get('/api/runs/'+identifier+'?status=all&field=business_purpose').json
    assert filtered['matched']==1 and filtered['records'][0]['response_id']=='002'
    detail=client.get(f'/api/runs/{identifier}/records/1').json
    assert detail['record']['cells']['business_purpose']=='test' and detail['run']['id']==identifier
    assert detail['record']['findings'][0]['why']
    report=client.get(f'/api/runs/{identifier}/export?kind=issues&status=all&field=business_purpose')
    rows=list(csv.DictReader(StringIO(report.data.decode('utf-8-sig'))))
    assert report.headers['X-Record-Count']=='1' and {r['Record ID'] for r in rows}=={'002'}
    full=client.get(f'/api/runs/{identifier}/export?kind=records&scope=all&field=business_purpose')
    assert full.headers['X-Record-Count']=='3'
    restarted=create_app(app.extensions['store'].path.parent).test_client()
    assert restarted.get('/api/runs/'+identifier).json==result


def test_preview_does_not_validate_and_confirmation_checks_integrity(app):
    import json
    client=app.test_client(); data=csv_file([valid_row()])
    preview=client.post('/api/preview',data={'file':(BytesIO(data),'sample.csv')},headers=HEAD).json
    assert not client.get('/api/runs').json['runs'] and len(preview['fields'])==24
    assert preview['samples'][HEADERS[2]]==['Synthetic assistant 001']
    for values in [{}, {'mapping':'{}'}, {'mapping':json.dumps(preview['mapping']),'file_hash':'wrong','rules_version':preview['rules_version']},
                   {'mapping':json.dumps(preview['mapping']),'file_hash':preview['file_hash'],'rules_version':'old'}]:
        assert client.post('/api/runs',data={'file':(BytesIO(data),'sample.csv'),**values},headers=HEAD).status_code==400
    assert not client.get('/api/runs').json['runs']
    assert len(client.get('/api/rules').json['fields'])==24


def test_xlsx_worksheet_selection(app):
    client=app.test_client()
    def several(wb): wb.copy_worksheet(wb.active).title='Second'
    data=xlsx_file([valid_row()],several)
    response=upload(client,data,'book.xlsx')
    assert response.status_code==422 and response.json['sheets']==['Disclosure','Second']
    first=upload(client,data,'book.xlsx',sheet='Disclosure').json['id']
    second=upload(client,data,'book.xlsx',sheet='Second').json['id']
    assert first!=second


def test_read_only_routes_headers_origins_and_error_privacy(app,caplog,monkeypatch):
    client=app.test_client()
    assert client.get('/').status_code==200 and b'streamlit' not in client.get('/').data.lower()
    for path in ['/assets/app.js','/assets/style.css','/assets/centene-logo.jpg']:
        response=client.get(path); assert response.status_code==200 and response.headers['X-Content-Type-Options']=='nosniff'
    for route in ['/api/preview','/api/runs']:
        assert client.post(route).status_code==403
        assert client.post(route,headers={**HEAD,'Origin':'https://untrusted.example'}).status_code==403
    identifier=upload(client).json['id']
    for path in [f'/api/runs/{identifier}/records/0',f'/api/runs/{identifier}/edit',f'/api/runs/{identifier}/commit']:
        for method in ['post','put','patch','delete']:
            assert getattr(client,method)(path,json={'name':'changed'}).status_code in {404,405}
    assert client.get('/api/runs').headers['Cache-Control']=='no-store'
    assert "frame-ancestors 'none'" in client.get('/').headers['Content-Security-Policy']
    assert client.get('/api/runs',headers={'Host':'attacker.example'}).status_code==400
    def fail(): raise RuntimeError('SENSITIVE SOURCE VALUE')
    monkeypatch.setattr(app.extensions['store'],'runs',fail)
    response=client.get('/api/runs')
    assert response.status_code==500 and b'SENSITIVE' not in response.data
    assert 'RuntimeError' in caplog.text and 'SENSITIVE' not in caplog.text


def test_errors_pagination_empty_reports_and_limits(app):
    client=app.test_client()
    assert upload(client,b'broken','bad.csv').status_code==400
    assert client.get('/api/runs').json['runs']==[]
    assert client.get('/api/runs/unknown').status_code==404
    identifier=upload(client,csv_file([valid_row(str(i).zfill(3)) for i in range(60)])).json['id']
    page=client.get(f'/api/runs/{identifier}?status=all&page=2&size=25').json
    assert page['matched']==60 and len(page['records'])==25 and page['records'][0]['source_row']==27
    assert client.get(f'/api/runs/{identifier}?page=abc').status_code==400
    assert client.get(f'/api/runs/{identifier}?field=unknown').status_code==400
    assert client.get(f'/api/runs/{identifier}/records/60').status_code==404
    empty=client.get(f'/api/runs/{identifier}/export?kind=issues&status=Failed')
    assert len(list(csv.reader(StringIO(empty.data.decode('utf-8-sig')))))==1 and empty.headers['X-Record-Count']=='0'
    assert client.get(f'/api/runs/{identifier}/export?kind=fields').status_code==400
    app.config['MAX_CONTENT_LENGTH']=1
    assert upload(client).status_code==413


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


def test_browser_mapping_review_and_download(browser_app,app):
    from playwright.sync_api import expect
    page,context,base,errors=browser_app
    page.goto(base)
    expect(page.locator('#home-empty')).to_be_visible()
    expect(page.locator('#summary')).to_be_hidden()
    data=csv_file([valid_row(),valid_row('002',Q3='test'),valid_row('003',Q20='Unknown')])
    choose_upload(page,data)
    expect(page.locator('#mapping-view')).to_be_visible()
    expect(page.locator('#mapping-rows tr')).to_have_count(24)
    expect(page.locator('#mapping-progress')).to_have_text('24 fields ready to validate')
    assert not app.extensions['store'].runs()
    expect(page.locator('[data-mapping-field="business_owner_email"] .mapping-preview')).to_contain_text('Alex Smith, Operations')
    page.locator('[data-mapping-field="business_owner_email"] button').click()
    expect(page.locator('#rules-list')).to_contain_text('person’s name')
    expect(page.locator('#rules-list')).to_contain_text('Why:')
    page.locator('[data-close="rules-dialog"]').click()
    page.locator('#mapping-submit').click()
    expect(page.locator('#review-view')).to_be_visible()
    expect(page.locator('#records tr')).to_have_count(2)
    expect(page.locator('#summary')).to_contain_text('Records3')
    expect(page.locator('#summary')).to_contain_text('Warnings1')
    page.locator('#field').select_option('business_purpose')
    expect(page.locator('#records tr')).to_have_count(1)
    page.locator('#records tr td').nth(2).click()
    expect(page.locator('#record-content')).to_be_visible()
    expect(page.locator('[data-field="business_purpose"]')).to_have_class('field-error')
    expect(page.locator('[data-field="business_purpose"] .field-value')).to_have_text('test')
    expect(page.locator('[data-field="business_purpose"]')).to_contain_text('Why this is an error:')
    expect(page.locator('#record-view input, #record-view textarea, #record-view select, #record-view [contenteditable]')).to_have_count(0)
    page.locator('#back-to-results').click()
    expect(page.locator('#field')).to_have_value('business_purpose')
    expect(page.locator('#records .record-open')).to_be_focused()
    page.locator('#download-open').click()
    with page.expect_download() as downloaded: page.locator('#issues-download').click()
    issue_rows=list(csv.DictReader(StringIO(downloaded.value.path().read_text(encoding='utf-8-sig'))))
    assert {r['Record ID'] for r in issue_rows}=={'002'} and all(r['Why this severity'] for r in issue_rows)
    page.locator('#report-scope').select_option('all')
    with page.expect_download() as downloaded: page.locator('#records-download').click()
    assert len(list(csv.DictReader(StringIO(downloaded.value.path().read_text(encoding='utf-8-sig')))))==3
    page.locator('[data-close="report-dialog"]').click()
    page.locator('#clear-filters').click(); expect(page.locator('#records tr')).to_have_count(3)
    page.locator('#status').select_option('Needs review'); expect(page.locator('#records tr')).to_have_count(1)
    page.locator('#records tr').click(); expect(page.locator('[data-field="risk_tier"]')).to_have_class('field-warning')
    page.locator('#back-to-results').click(); page.locator('#status').select_option('Passed')
    expect(page.locator('#records tr')).to_have_count(1); page.locator('#records tr').click()
    expect(page.locator('#record-status')).to_contain_text('All applicable checks passed.')
    page.locator('#home-button').click(); expect(page.locator('#history tr')).to_have_count(1)
    choose_upload(page,data,'renamed.csv'); expect(page.locator('#mapping-origin')).to_contain_text('last confirmed mapping')
    page.locator('#mapping-submit').click(); expect(page.locator('#review-view')).to_be_visible()
    assert len(app.extensions['store'].runs())==1
    corrected=csv_file([valid_row(),valid_row('002'),valid_row('003')])
    choose_upload(page,corrected); page.locator('#mapping-submit').click()
    expect(page.locator('#summary .passed')).to_have_text('Passed3')
    expect(page.locator('#records tr')).to_have_count(3)
    assert len(app.extensions['store'].runs())==2


def test_browser_custom_mapping_missing_fields_and_sheets(browser_app,app):
    from playwright.sync_api import expect
    page,context,base,errors=browser_app; page.goto(base)
    choose_upload(page,dict_csv([{'Tool label':'Claims assistant','Purpose text':'Find approved guidance.','Owner':'Alex Smith','Publisher':'Taylor Jones','Created':'2026-01-02'}]))
    expect(page.locator('#mapping-submit')).to_be_disabled()
    def select(fid): return page.locator('[data-mapping-field="'+fid+'"] select')
    select('system_name').select_option('column:0'); select('business_purpose').select_option('column:1')
    assert select('technical_owner_email').locator('option[value="column:0"]').is_disabled()
    expect(select('technical_owner_email')).to_have_value('')
    expect(select('go_live_date')).to_have_value('')
    select('business_owner_email').select_option('column:2'); select('technical_owner_email').select_option('column:3')
    page.locator('#mapping-fill').click(); expect(page.locator('#mapping-missing')).to_be_visible()
    page.locator('#mapping-submit').click(); expect(page.locator('#missing-columns')).to_be_visible()
    page.locator('#records tr').click(); expect(page.locator('#not-checked')).to_be_visible()
    expect(page.locator('[data-field="business_owner_email"]')).not_to_have_class('field-error')
    page.locator('#extra-values summary').click(); expect(page.locator('#extra-values-body')).to_contain_text('Created')
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    choose_upload(page,dict_csv([{'Unfamiliar title':'New source'}]))
    expect(page.locator('#mapping-view')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.reload(); expect(page.locator('#home-view')).to_be_visible()
    expect(page.locator('#notice')).to_contain_text('Choose the file again')
    page.set_viewport_size({'width':1440,'height':1000})
    choose_upload(page,b'a,a\nx,y\n'); expect(page.locator('#upload-error')).to_contain_text('Duplicate column')
    def several(wb): wb.copy_worksheet(wb.active).title='Second'
    data=xlsx_file([valid_row()],several)
    page.locator('#file').set_input_files({'name':'book.xlsx','mimeType':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','buffer':data})
    page.locator('#upload-submit').click(); expect(page.locator('#sheet-label')).to_be_visible()
    page.locator('#sheet').select_option('Second'); page.locator('#upload-submit').click()
    expect(page.locator('#mapping-file')).to_contain_text('Second')
    page.locator('#mapping-submit').click(); expect(page.locator('#run-meta')).to_contain_text('Second')
    expect(page.locator('#summary .passed')).to_have_text('Passed1')


def test_browser_record_navigation_pagination_retry_and_html_safety(browser_app,app):
    from playwright.sync_api import expect
    page,context,base,errors=browser_app
    rows=[valid_row(str(i).zfill(3),Q3='test') for i in range(1,31)]
    literal='<img src=x onerror="window.injected=1">'; rows[25]['Q2']=literal
    identifier=stage(app.extensions['store'],csv_file(rows),'browser.csv')
    page.goto(base+f'/#run/{identifier}')
    expect(page.locator('#records tr')).to_have_count(25)
    page.locator('#field').select_option('business_purpose'); page.locator('#next').click()
    expect(page.locator('#page-info')).to_have_text('Page 2 of 2')
    expect(page.locator('#records tr')).to_have_count(5)
    for column in range(4):
        page.locator('#records tr').first.locator('td').nth(column).click(position={'x':6,'y':6})
        expect(page.locator('#record-content')).to_be_visible()
        expect(page.locator('#record-title')).to_have_text(literal)
        assert not page.evaluate('window.injected')
        page.locator('#back-to-results').click()
        expect(page.locator('#page-info')).to_have_text('Page 2 of 2')
        expect(page.locator('#records tr').first.locator('.record-open')).to_be_focused()
    page.keyboard.press('Enter'); expect(page.locator('#record-content')).to_be_visible(); record_url=page.url
    page.go_back(); expect(page.locator('#review-view')).to_be_visible()
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
