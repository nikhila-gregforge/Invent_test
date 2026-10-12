"""Chart counts, percentage bases, filtering, historical data and inventory totals."""
import json
from inventory.analytics import distributions, inventory_error_count
from app import create_app
from test_inventory import snapshot, valid_row, csv_file, stage


def by_id(result): return {chart['id']:chart for chart in result['charts']}
def buckets(chart): return {item['label']:item for item in chart['buckets']}


def test_risk_unknown_missing_invalid_are_distinct_and_counts_cover_every_record():
    data=snapshot([valid_row(str(i),Q20=risk) for i,risk in enumerate(['High','Low','Unknown','',';'])])
    chart=by_id(distributions(data,data['records']))['risk_tier']; values=buckets(chart)
    assert sum(b['count'] for b in chart['buckets'])==5
    assert values['Medium']['count']==0
    for label in ['High','Low','Unknown','Missing','Invalid']:
        assert values[label]['count']==1 and values[label]['percent']==20
    assert (chart['valid_records'],chart['missing_records'],chart['invalid_records'])==(3,1,1)


def test_lob_bars_use_record_percentages_including_missing_and_invalid_rows():
    data=snapshot([valid_row('1',Q18='Medicaid;Medicare;Medicaid'),
                   valid_row('2',Q18='Medicare'),valid_row('3',Q18='None;Commercial'),valid_row('4',Q18='')])
    chart=by_id(distributions(data,data['records']))['lines_of_business']; values=buckets(chart)
    assert chart['kind']=='bar' and chart['denominator']==4 and chart['selection_count']==3
    assert values['Medicaid']['count']==1 and values['Medicaid']['percent']==25
    assert values['Medicare']['count']==2 and values['Medicare']['percent']==50
    assert (chart['valid_records'],chart['missing_records'],chart['invalid_records'])==(2,1,1)
    assert 'None' not in values  # Contradictory selections never become valid bars.


def test_other_charts_use_canonical_aliases_and_include_records_with_unrelated_errors():
    data=snapshot([valid_row('1',Q3='',Q10='LLM;GenAI;LLM',Q19='CA;NY'),
                   valid_row('2',Q10='Large Language Model (LLM)',Q21='Yes—at final stage; Override: No')])
    charts=by_id(distributions(data,data['records']))
    assert buckets(charts['ai_types'])['Large Language Model (LLM)']['count']==2
    assert buckets(charts['ai_types'])['Large Language Model (LLM)']['record_percent']==100
    assert buckets(charts['human_oversight'])['Partially']['count']==1
    assert buckets(charts['states'])['California']['count']==2
    assert buckets(charts['impact.financial'])['Yes']['count']==2
    for chart in charts.values():
        assert chart['denominator']==2
        assert not chart['multi'] or chart['kind']=='bar'
        for bucket in chart['buckets']:
            assert bucket['percent']==bucket['record_percent']==bucket['count']/2*100
    assert not {'application_id','system_name','business_owner_email','go_live_date','llm_count'} & set(charts)


def test_empty_charts_and_legacy_snapshots_do_not_change_saved_results():
    data=snapshot([valid_row(Q20='Unknown')])
    for record in data['records']:
        record.pop('normalized'); record.pop('chart_invalid_fields')
    before=json.dumps(data,sort_keys=True)
    assert buckets(by_id(distributions(data,data['records']))['risk_tier'])['Unknown']['count']==1
    empty=distributions(data,[])
    assert all(c['denominator']==0 and all(b['percent']==0 for b in c['buckets']) for c in empty['charts'])
    assert json.dumps(data,sort_keys=True)==before


def test_free_text_chart_categories_are_unclassified_without_validation_errors():
    data=snapshot([valid_row(Q20='Very Low',Q18='Corporate',Q5='Financial and regulatory')])
    assert data['records'][0]['status']=='Passed'
    charts=by_id(distributions(data,data['records']))
    for name in ['risk_tier','lines_of_business','impact.member']:
        assert charts[name]['invalid_records']==0
        assert charts[name]['unclassified_records']==1
    assert buckets(charts['risk_tier'])['Unclassified']['count']==1


def test_inventory_error_count_counts_records_once_and_excludes_only_submitter_errors():
    data=snapshot([valid_row('1',Q3='',Q12='0'),valid_row('2',Q22='',Q23=''),valid_row('3')])
    assert inventory_error_count(data['records'])==1
    assert sum(record['status']=='Errors' for record in data['records'])==2


def test_analytics_endpoint_scopes_all_pages_and_matches_inventory_result_count(tmp_path):
    app=create_app(tmp_path); client=app.test_client()
    rows=[valid_row(str(i),Q20='High' if i<30 else 'Low',Q3='' if i<30 else 'Helps staff find approved guidance') for i in range(35)]
    rows.append(valid_row('submitter-only',Q23=''))
    identifier=stage(app.extensions['store'],csv_file(rows))
    result=client.get(f'/api/runs/{identifier}?status=Errors&size=10&page=2').json
    assert len(result['records'])==10 and result['inventory_error_records']==30
    all_data=client.get(f'/api/runs/{identifier}/analytics?scope=all&status=Errors&page=2&size=10').json
    assert all_data['total_records']==36
    filtered=client.get(f'/api/runs/{identifier}/analytics?scope=filtered&status=Errors&field=business_purpose&page=2&size=10').json
    assert filtered['total_records']==30 and buckets(by_id(filtered)['risk_tier'])['High']['percent']==100
    assert client.get(f'/api/runs/{identifier}/analytics?scope=filtered&status=all&q=no-match').json['total_records']==0
    assert client.get(f'/api/runs/{identifier}/analytics?scope=invalid').status_code==400
    assert client.get(f'/api/runs/{identifier}/analytics?scope=filtered&field=invalid').status_code==400
    assert client.get('/api/runs/missing/analytics').status_code==404
