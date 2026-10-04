"""HTTP acceptance checks for the read-only workspace."""
import csv
from io import BytesIO,StringIO
from concurrent.futures import ThreadPoolExecutor
import pytest
from app import create_app
from test_inventory import csv_file,valid_row,agent_row,agent_csv,xlsx_file,AS_OF

@pytest.fixture
def app(tmp_path):
    app=create_app(tmp_path);app.config['TESTING']=True
    return app


def upload(client,data=None,name='sample.csv',**kwargs):
    return client.post('/api/runs',data={'file':(BytesIO(data or csv_file([valid_row(),valid_row('002',Q3='test'),valid_row('003',Q20='Unknown')])),name),**kwargs},headers={'X-Requested-With':'AIInventory'})


def test_upload_review_filter_detail_download_and_restart(app):
    client=app.test_client();response=upload(client);assert response.status_code==201
    identifier=response.json['id']
    run=client.get('/api/runs/'+identifier).json
    assert (run['run']['passed'],run['run']['review'],run['run']['failed'])==(1,1,1)
    assert run['matched']==2
    filtered=client.get('/api/runs/'+identifier+'?status=all&field=business_purpose&rule=TEXT-01').json
    assert filtered['matched']==1 and filtered['records'][0]['response_id']=='002'
    detail=client.get(f'/api/runs/{identifier}/records/1').json
    assert detail['record']['cells']['business_purpose']=='test'
    report=client.get(f'/api/runs/{identifier}/export?kind=issues&status=all&field=business_purpose&rule=TEXT-01')
    assert report.status_code==200 and report.headers['X-Record-Count']=='1'
    rows=list(csv.DictReader(StringIO(report.data.decode('utf-8-sig'))))
    assert {r['Record ID'] for r in rows}=={'002'}
    full=client.get(f'/api/runs/{identifier}/export?kind=records&scope=all&field=business_purpose')
    assert full.headers['X-Record-Count']=='3'
    restarted=create_app(app.extensions['store'].path.parent).test_client()
    assert restarted.get('/api/runs/'+identifier).json==run


def test_raw_upload_and_sheet_selection(app):
    client=app.test_client()
    response=upload(client,agent_csv([agent_row()]),'agents.csv')
    assert response.status_code==201
    assert client.get('/api/runs/'+response.json['id']+'?status=all').json['run']['passed']==1
    def several(wb): wb.copy_worksheet(wb.active).title='Second'
    data=xlsx_file([valid_row()],several)
    response=upload(client,data,'book.xlsx')
    assert response.status_code==422 and response.json['sheets']==['Disclosure','Second']
    one=upload(client,data,'book.xlsx',sheet='Disclosure').json['id']
    two=upload(client,data,'book.xlsx',sheet='Second').json['id']
    assert one!=two


def test_read_only_routes_headers_and_upload_origin(app):
    client=app.test_client()
    assert client.get('/').status_code==200
    assert b'streamlit' not in client.get('/').data.lower()
    for path in ['/assets/app.js','/assets/style.css','/assets/centene-logo.jpg']:
        response=client.get(path);assert response.status_code==200
        assert response.headers['X-Content-Type-Options']=='nosniff'
    assert client.post('/api/runs').status_code==403
    assert client.post('/api/runs',headers={'X-Requested-With':'AIInventory','Origin':'https://untrusted.example'}).status_code==403
    identifier=upload(client).json['id']
    for path in [f'/api/runs/{identifier}/records/0',f'/api/runs/{identifier}/edit',f'/api/runs/{identifier}/commit']:
        for method in ['post','put','patch','delete']:
            assert getattr(client,method)(path,json={'name':'changed'}).status_code in {404,405}
    assert client.get('/api/runs').headers['Cache-Control']=='no-store'
    assert "frame-ancestors 'none'" in client.get('/').headers['Content-Security-Policy']
    assert client.get('/api/runs',headers={'Host':'attacker.example'}).status_code==400


def test_errors_pagination_and_export_empty(app):
    client=app.test_client()
    assert upload(client,b'broken','bad.csv').status_code==400
    assert client.get('/api/runs').json['runs']==[]
    assert client.get('/api/runs/unknown').status_code==404
    rows=[valid_row(str(i).zfill(3)) for i in range(60)]
    identifier=upload(client,csv_file(rows)).json['id']
    page=client.get(f'/api/runs/{identifier}?status=all&page=2&size=25&sort=source_row').json
    assert page['matched']==60 and len(page['records'])==25 and page['records'][0]['source_row']==27
    assert client.get(f'/api/runs/{identifier}?page=abc').status_code==400
    assert client.get(f'/api/runs/{identifier}?field=unknown').status_code==400
    assert client.get(f'/api/runs/{identifier}/records/60').status_code==404
    empty=client.get(f'/api/runs/{identifier}/export?kind=issues&status=Failed')
    assert len(list(csv.reader(StringIO(empty.data.decode('utf-8-sig')))))==1
    assert empty.headers['X-Record-Count']=='0'
    app.config['MAX_CONTENT_LENGTH']=1
    assert upload(client).status_code==413


def test_concurrent_identical_uploads_converge(app):
    store=app.extensions['store'];data=csv_file([valid_row()])
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids=list(pool.map(lambda _:store.stage(data,'same.csv',as_of=AS_OF),range(4)))
    assert len(set(ids))==1 and len(store.runs())==1


def test_browser_record_review(app):
    """Opt-in browser regression: cell clicks must open an independent record view."""
    import os
    if os.getenv('AI_INVENTORY_BROWSER_TESTS')!='1':
        pytest.skip('Set AI_INVENTORY_BROWSER_TESTS=1 to run the browser regression.')
    from playwright.sync_api import sync_playwright, expect
    from threading import Thread
    from werkzeug.serving import make_server

    rows=[valid_row(str(i).zfill(3),Q3='test') for i in range(1,31)]
    literal='<img src=x onerror="window.injected=1">'
    rows[25]=valid_row('026',Q2=literal,Q3='test',Q12='0',Q20='Unknown')
    rows[26]=valid_row('027',Q3='')
    rows[28]=valid_row('029')
    rows[29]=valid_row('030',Q20='Unknown')
    identifier=app.extensions['store'].stage(csv_file(rows),'browser.csv',as_of=AS_OF)
    server=make_server('127.0.0.1',0,app,threaded=True)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    try:
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True,channel=os.getenv('AI_INVENTORY_BROWSER_CHANNEL') or None)
            page=browser.new_page(viewport={'width':1440,'height':1000})
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(base)
            expect(page.locator('#records tr')).to_have_count(25)
            page.locator('#field').select_option('business_purpose')
            expect(page.locator('#match-count')).to_contain_text('28')
            page.locator('#sort').select_option('source_row')
            expect(page.locator('#records tr').first).to_contain_text('001')
            page.locator('#next').click()
            expect(page.locator('#page-info')).to_have_text('Page 2 of 2')
            expect(page.locator('#records tr')).to_have_count(3)

            # Every cell is clickable, including status, owner, counts and whitespace.
            for column in range(6):
                page.locator('#records tr').first.locator('td').nth(column).click(position={'x':6,'y':6})
                expect(page.locator('#record-content')).to_be_visible()
                expect(page.locator('#workspace')).to_be_hidden()
                expect(page.locator('#record-title')).to_have_text(literal)
                expect(page.locator('[data-field="business_purpose"] .field-value')).to_have_text('test')
                expect(page.locator('[data-field="business_purpose"]')).to_have_class('field-error')
                expect(page.locator('[data-field="llm_count"] .field-value')).to_have_text('0')
                expect(page.locator('[data-field="llm_count"] .expected')).to_contain_text('positive count')
                expect(page.locator('[data-field="risk_tier"]')).to_have_class('field-warning')
                expect(page.locator('#record-view input, #record-view textarea, #record-view select, #record-view [contenteditable]')).to_have_count(0)
                assert not page.evaluate('window.injected')
                page.locator('#back-to-results').click()
                expect(page.locator('#workspace')).to_be_visible()
                expect(page.locator('#page-info')).to_have_text('Page 2 of 2')
                expect(page.locator('#field')).to_have_value('business_purpose')
                expect(page.locator('#records tr').first.locator('.record-open')).to_be_focused()

            # Keyboard, native Back/Forward, refresh and opening a record URL directly.
            page.keyboard.press('Enter')
            expect(page.locator('#record-content')).to_be_visible()
            record_url=page.url
            page.go_back();expect(page.locator('#workspace')).to_be_visible()
            page.go_forward();expect(page.locator('#record-content')).to_be_visible()
            page.reload();expect(page.locator('#record-content')).to_be_visible()
            page.locator('#record-findings button').filter(has_text='LLM Count').click()
            expect(page.locator('[data-field="llm_count"]')).to_be_focused()
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.locator('#back-to-results').click()
            expect(page.locator('#page-info')).to_have_text('Page 2 of 2')
            page.set_viewport_size({'width':1440,'height':1000})
            page.locator('#records tr').nth(1).locator('td').first.click()
            expect(page.locator('[data-field="business_purpose"] .field-value')).to_have_text('(blank)')
            expect(page.locator('[data-field="business_purpose"]')).to_have_class('field-error')
            page.locator('#back-to-results').click()

            # A failed detail request stays in the record view with a working retry.
            detail=f'**/api/runs/{identifier}/records/25'
            page.route(detail,lambda route:route.fulfill(status=503,json={'error':'Temporary review failure.'}))
            page.locator('#records tr').first.locator('td').first.click()
            expect(page.locator('#record-error')).to_be_visible()
            expect(page.locator('#record-error-message')).to_have_text('Temporary review failure.')
            page.unroute(detail)
            page.locator('#record-retry').click()
            expect(page.locator('#record-content')).to_be_visible()
            page.locator('#back-to-results').click()
            page.locator('#clear-filters').click()
            expect(page.locator('#match-count')).to_contain_text('30')
            for status in ['Passed','Needs review']:
                page.locator('#status').select_option(status)
                expect(page.locator('#records tr')).to_have_count(1)
                page.locator('#records tr').first.click()
                expect(page.locator('#record-status')).to_contain_text(status)
                expect(page.locator('#source-values .field-error')).to_have_count(0)
                if status=='Passed':
                    expect(page.locator('#record-findings')).to_have_text('All applicable checks passed.')
                else:
                    expect(page.locator('[data-field="risk_tier"]')).to_have_class('field-warning')
                page.locator('#back-to-results').click()
                expect(page.locator('#workspace')).to_be_visible()
            direct=browser.new_page()
            direct.goto(record_url)
            expect(direct.locator('#record-content')).to_be_visible()
            expect(direct.locator('#record-title')).to_have_text(literal)
            direct.locator('#back-to-results').click()
            expect(direct.locator('#workspace')).to_be_visible()
            direct.goto(base+f'/#run/{identifier}/record/999')
            expect(direct.locator('#record-error-message')).to_have_text('Record not found.')
            assert not errors,errors
            browser.close()
    finally:
        server.shutdown();thread.join(timeout=5);server.server_close()
