"""Read-only AI Inventory validation workspace. Run: python app.py"""
import os
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory, Response
from werkzeug.exceptions import HTTPException
import inventory as config
from inventory.ingestion import ImportFailure, SheetSelectionRequired
from inventory.storage import Store
from inventory.exports import select_records, field_summary, export_report

ROOT=Path(__file__).resolve().parent


def create_app(data_dir=None):
    app=Flask(__name__,static_folder=str(ROOT/'assets'),static_url_path='/assets')
    app.config.update(MAX_CONTENT_LENGTH=config.MAX_BYTES+1024*1024,
        TRUSTED_HOSTS=os.getenv('AI_INVENTORY_HOSTS','localhost,127.0.0.1,[::1]').split(','))
    store=Store(data_dir)
    app.extensions['store']=store

    @app.after_request
    def response_headers(response):
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='same-origin'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        response.headers['Cache-Control']='no-store' if request.path.startswith('/api/') else 'no-cache'
        return response

    @app.get('/')
    def index(): return send_from_directory(ROOT/'assets','index.html')

    @app.get('/api/health')
    def health(): return jsonify(status='ok',rules_version=config.RULES_VERSION)

    @app.get('/api/runs')
    def runs(): return jsonify(runs=store.runs(),max_bytes=config.MAX_BYTES,max_rows=config.MAX_ROWS)

    @app.post('/api/runs')
    def upload():
        if request.headers.get('X-Requested-With')!='AIInventory':
            return jsonify(error='Upload requests must originate from this application.'),403
        origin=request.headers.get('Origin')
        if origin and origin!=request.host_url.rstrip('/'):
            return jsonify(error='Cross-origin uploads are not allowed.'),403
        file=request.files.get('file')
        if file is None or not file.filename: raise ValueError('Choose a CSV or XLSX file.')
        data=file.read(config.MAX_BYTES+1)
        identifier=store.stage(data,file.filename,request.form.get('sheet') or None)
        return jsonify(id=identifier),201

    @app.get('/api/runs/<identifier>')
    def results(identifier):
        snapshot=store.snapshot(identifier)
        records=select_records(snapshot,request.args)
        try:
            page=max(1,int(request.args.get('page',1)))
            size=min(100,max(10,int(request.args.get('size',25))))
        except ValueError: raise ValueError('Invalid pagination.')
        pages=max(1,(len(records)+size-1)//size)
        page=min(page,pages)
        summary=field_summary(snapshot,records)
        return jsonify(run=snapshot['run'],fields=summary,matched=len(records),page=page,pages=pages,size=size,
            findings=sum(len(r['findings']) for r in records),
            rules=sorted({(f['rule_id'],f['title']) for r in snapshot['records'] for f in r['findings']}),
            records=[{k:r[k] for k in ['key','source_row','response_id','name','owner','status','errors','warnings','affected_fields']}
                     for r in records[(page-1)*size:page*size]])

    @app.get('/api/runs/<identifier>/records/<int:key>')
    def record(identifier,key):
        snapshot=store.snapshot(identifier)
        if key<0 or key>=len(snapshot['records']): raise KeyError('Record not found.')
        return jsonify(record=snapshot['records'][key],fields=snapshot['fields'])

    @app.get('/api/runs/<identifier>/export')
    def export(identifier):
        snapshot=store.snapshot(identifier)
        args={'status':'all'} if request.args.get('scope')=='all' else request.args
        records=select_records(snapshot,args)
        kind=request.args.get('kind','issues')
        payload=export_report(snapshot,records,kind)
        scope='all' if request.args.get('scope')=='all' else 'filtered'
        return Response(payload,mimetype='text/csv',headers={
            'Content-Disposition':f'attachment; filename="ai-inventory-{scope}-{kind}-{identifier[:8]}.csv"',
            'X-Record-Count':str(len(records))})

    @app.errorhandler(SheetSelectionRequired)
    def sheets(exc): return jsonify(error=str(exc),sheets=exc.sheets),422

    @app.errorhandler(ImportFailure)
    @app.errorhandler(ValueError)
    def bad_input(exc): return jsonify(error=str(exc)),400

    @app.errorhandler(KeyError)
    def not_found(exc): return jsonify(error=exc.args[0]),404

    @app.errorhandler(Exception)
    def unexpected(exc):
        if isinstance(exc,HTTPException):
            return jsonify(error='Upload exceeds the file-size limit.' if exc.code==413 else exc.description),exc.code
        # Do not log uploaded values or exception messages containing source data.
        app.logger.error('Request failed: %s',type(exc).__name__)
        return jsonify(error='The request could not be completed. Retry; saved validation runs remain available.'),500

    return app


if __name__=='__main__':
    from waitress import serve
    port=int(os.getenv('PORT','8501'))
    print(f'AI Inventory: http://127.0.0.1:{port}',flush=True)
    serve(create_app(),host='127.0.0.1',port=port,threads=4,max_request_body_size=config.MAX_BYTES+1024*1024)
