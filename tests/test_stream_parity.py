"""Streaming and classic responses share one verified, persisted detail."""
import io
import json

import pytest
from conftest import CSV_CONTENT


def stream_events(client):
    response = client.post('/chat/stream', json={'question': 'Combien en alimentation ?'})
    assert response.status_code == 200
    return [(frame.splitlines()[0][7:], json.loads(frame.splitlines()[1][6:]))
            for frame in response.get_data(as_text=True).strip().split('\n\n')]


@pytest.mark.parametrize('divergent', [False, True])
def test_stream_matches_classic_detail(client, claude, monkeypatch, divergent):
    client.post('/imports', data={'file': (io.BytesIO(CSV_CONTENT), 'expenses.csv')})
    if divergent:
        monkeypatch.setattr('app.verification.calculate_sql', lambda *_: {
            'ok': True, 'value': {'result_cents': 100, 'expense_ids': [1], 'duration_ms': 1}})
    calc_id = client.post('/chat', json={'question': 'Combien en alimentation ?'}).get_json()['calculation_id']
    classic = client.get(f'/calculations/{calc_id}').get_json()
    before = len(claude['calls'])
    events = stream_events(client)
    assert [kind for kind, _ in events].count('tool_call') == 1
    assert len(claude['calls']) - before == 2
    kind, final = events[-1]
    assert kind == 'final'
    for key in ('answer', 'verdict', 'request', 'expenses', 'tool_trace', 'request_info'):
        assert final[key] == classic[key]
    for method in ('python', 'sql'):
        for key in ('result_cents', 'expense_ids'):
            assert final[method]['value'][key] == classic[method]['value'][key]
    assert final == client.get(f"/calculations/{final['id']}").get_json()
    assert final['total_duration_ms'] >= 0


def test_stream_clarification_has_no_invented_comparison(client, claude):
    claude['tool_call'] = False
    claude['final_text'] = 'Veuillez préciser la période.'
    kind, final = stream_events(client)[-1]
    assert kind == 'final'
    assert final['answer'] == 'Veuillez préciser la période.'
    assert 'verdict' not in final and 'python' not in final and 'sql' not in final
    assert final['request_info'] == client.post('/chat', json={'question': 'Récemment ?'}).get_json()['request_info']


@pytest.mark.parametrize('tool_call', [False, True])
@pytest.mark.parametrize('endpoint', ['/chat', '/chat/stream'])
def test_stop_at_final_publication_preserves_usage_without_validation(client, claude, monkeypatch, application, endpoint, tool_call):
    import app.agent_state as agent_state
    from app.db import get_connection

    claude['tool_call'] = tool_call
    claude['final_text'] = 'Veuillez préciser la période.'
    original = agent_state.run_if_execution_active

    def cancel_before_publication(token, callback):
        agent_state.stop_agent()
        agent_state.start_agent()
        return original(token, callback)

    monkeypatch.setattr('app.routes.run_if_execution_active', cancel_before_publication)
    response = client.post(endpoint, json={'question': 'Total ?'})
    if endpoint == '/chat':
        assert response.status_code == 503
        data = response.get_json()
    else:
        frame = response.get_data(as_text=True).strip().split('\n\n')[-1]
        assert frame.startswith('event: error\n')
        data = json.loads(frame.split('data: ', 1)[1])
    assert 'verdict' not in data and 'answer' not in data and 'calculation_id' not in data
    assert data['request_info']['metrics']['model_calls'] == (2 if tool_call else 1)
    assert data['request_info']['cost']['amount'] == ('0.00044000' if tool_call else '0.00022000')
    with get_connection(application.config['DATABASE_PATH']) as conn:
        assert conn.execute('SELECT COUNT(*) FROM calculations').fetchone()[0] == 0


@pytest.mark.parametrize('endpoint', ['/chat', '/chat/stream'])
def test_storage_failure_keeps_consumption(client, claude, monkeypatch, endpoint):
    import sqlite3

    def broken_storage(*args):
        raise sqlite3.OperationalError('storage failed')

    monkeypatch.setattr('app.routes._store_calculation', broken_storage)
    response = client.post(endpoint, json={'question': 'Total ?'})
    if endpoint == '/chat':
        assert response.status_code == 503
        data = response.get_json()
    else:
        frame = response.get_data(as_text=True).strip().split('\n\n')[-1]
        assert frame.startswith('event: error\n')
        data = json.loads(frame.split('data: ', 1)[1])
    assert data['request_info']['cost']['amount'] == '0.00044000'
    assert 'verdict' not in data
