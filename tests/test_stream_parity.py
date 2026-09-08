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
    for key in ('answer', 'verdict', 'request', 'expenses', 'tool_trace'):
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
    assert (kind, final) == ('final', {'answer': 'Veuillez préciser la période.'})
