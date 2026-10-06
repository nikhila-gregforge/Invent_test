"""HTTP and opt-in Chrome acceptance for direct, fixed-format validation."""
import csv
import os
from io import BytesIO, StringIO
import pytest
from app import create_app
from test_inventory import csv_file, valid_row, xlsx_file, stage, HEADERS, AS_OF, create_legacy_database

HEAD = {'X-Requested-With':'AIInventory'}


@pytest.fixture
def app(tmp_path,request):
    if getattr(request,'param',False): create_legacy_database(tmp_path)
    application=create_app(tmp_path); application.config['TESTING']=True
    return application


def upload(client,data=None,name='sample.csv',**kwargs):
    data = data if data is not None else csv_file([valid_row(),valid_row('002',Q3='test'),valid_row('003',Q12='0')])
    return client.post('/api/runs',data={'file':(BytesIO(data),name),**kwargs},headers=HEAD)


def test_direct_upload_review_detail_reports_and_restart(app):
    client=app.test_client(); response=upload(client); assert response.status_code==201
    identifier=response.json['id']; result=client.get('/api/runs/'+identifier).json
    assert (result['run']['passed'],result['run']['errors'])==(1,2) and result['matched']==2
    assert all('warnings' not in record and 'response_id' not in record for record in result['records'])
    filtered=client.get('/api/runs/'+identifier+'?status=all&field=business_purpose').json
    assert filtered['matched']==1 and filtered['records'][0]['application_id']=='APP-002'
    detail=client.get(f'/api/runs/{identifier}/records/1').json
    assert detail['record']['cells']['business_purpose']=='test' and detail['run']['id']==identifier
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


def test_xlsx_worksheet_selection_and_strict_headers(app):
    client=app.test_client()
    def several(wb): wb.copy_worksheet(wb.active).title='Second'
    data=xlsx_file([valid_row()],several)
    response=upload(client,data,'book.xlsx')
    assert response.status_code==422 and response.json['sheets']==['Disclosure','Second']
    first=upload(client,data,'book.xlsx',sheet='Disclosure').json['id']
    second=upload(client,data,'book.xlsx',sheet='Second').json['id']
    assert first!=second
    def bad(wb): wb.active['A1']='Wrong ID heading'
    assert upload(client,xlsx_file([valid_row()],bad),'bad.xlsx').json['columns']['missing']==[HEADERS[0]]


def test_read_only_routes_headers_origins_and_error_privacy(app,caplog,monkeypatch):
    client=app.test_client()
    html=client.get('/'); assert html.status_code==200 and b'streamlit' not in html.data.lower()
    for path in ['/assets/app.js','/assets/style.css','/assets/centene-logo.jpg']:
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


def test_browser_direct_upload_errors_and_download(browser_app,app):
    from playwright.sync_api import expect
    page,context,base,errors=browser_app; page.goto(base)
    expect(page.locator('#home-empty')).to_be_visible(); expect(page.locator('#summary')).to_be_hidden()
    page.locator('.upload-trigger').click()
    with page.expect_download() as downloaded: page.locator('#upload-dialog a[download]').click()
    assert list(csv.reader(StringIO(downloaded.value.path().read_text(encoding='utf-8-sig'))))==[HEADERS]
    page.locator('[data-close="upload-dialog"]').click()
    data=csv_file([valid_row(),valid_row('002',Q3='test'),valid_row('003',Q12='0')])
    choose_upload(page,data)
    expect(page.locator('#review-content')).to_be_visible(); expect(page.locator('#records tr')).to_have_count(2)
    expect(page.locator('#summary')).to_have_text('Total records3Records with errors2Passed1')
    assert page.locator('#status option').all_text_contents()==['All records','Errors','Passed']
    page.locator('#field').select_option('business_purpose'); expect(page.locator('#records tr')).to_have_count(1)
    page.locator('#records tr td').nth(2).click(); expect(page.locator('#record-content')).to_be_visible()
    expect(page.locator('[data-field="business_purpose"]')).to_have_class('field-error')
    expect(page.locator('[data-field="business_purpose"] .field-value')).to_have_text('test')
    expect(page.locator('[data-field="business_purpose"]')).to_contain_text('How to fix: Describe what the system does')
    expect(page.locator('#record-view input, #record-view textarea, #record-view select, #record-view [contenteditable]')).to_have_count(0)
    page.locator('[data-field="business_owner_email"] button').click()
    expect(page.locator('#rules-list')).to_contain_text('person’s name')
    expect(page.locator('#rules-list')).to_contain_text('any domain is allowed')
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


def test_browser_header_failures_reupload_and_worksheets(browser_app,app):
    from playwright.sync_api import expect
    page,context,base,errors=browser_app; page.goto(base)
    headers=HEADERS.copy(); headers[0]='Application ID'; headers[1]='<img src=x onerror="window.injected=1">'
    choose_upload(page,csv_file([valid_row()],headers))
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
    expect(page.locator('[data-field="business_owner_email"]')).to_contain_text('person’s name')
    expect(page.locator('[data-field="llm_count"]')).to_contain_text('How to fix: Count the actual models used')
    expect(page.locator('#not-checked')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.set_viewport_size({'width':1440,'height':1000})
    def several(wb): wb.copy_worksheet(wb.active).title='Second'
    choose_upload(page,xlsx_file([valid_row()],several),'book.xlsx')
    expect(page.locator('#sheet-label')).to_be_visible()
    page.locator('#sheet').select_option('Second'); page.locator('#upload-submit').click()
    expect(page.locator('#run-meta')).to_contain_text('Second'); expect(page.locator('#summary .passed')).to_have_text('Passed1')


def test_browser_record_navigation_retry_and_html_safety(browser_app,app):
    from playwright.sync_api import expect
    page,context,base,errors=browser_app
    rows=[valid_row(str(i).zfill(3),Q3='test') for i in range(1,31)]
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
    expect(page.locator('#history')).to_contain_text('Previous rules · Upload again')
    expect(page.locator('#history .badge')).to_have_count(0)
    page.locator('#history tr').click(); expect(page.locator('#archived-review')).to_be_visible()
    expect(page.locator('#archived-message')).to_contain_text('original upload and results are preserved')
    expect(page.locator('#review-content')).to_be_hidden(); expect(page.locator('#download-open')).to_be_disabled()
    page.goto(base+'/#run/old-run/record/0'); expect(page.locator('#record-error')).to_be_visible()
    expect(page.locator('#record-retry')).to_be_hidden()
    choose_upload(page,csv_file([valid_row(Q6='owner@example.com',Q20='Unknown')]))
    expect(page.locator('#summary .passed')).to_have_text('Passed1')
    expect(page.locator('#records')).to_contain_text('Passed')
    page.locator('#home-button').click(); expect(page.locator('#history tr')).to_have_count(2)
