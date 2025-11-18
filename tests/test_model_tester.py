import types

import pandas as pd

from model_tester import run_model


class DummyResponse:
    def __init__(self, status_code=200, text='OK', headers=None, json_data=None):
        self.status_code = status_code
        self.text = text
        self._json = json_data
        self.headers = headers or {'Content-Type': 'application/json'}

    def json(self):
        if self._json is None:
            raise ValueError('no json')
        return self._json


def test_run_model_success(monkeypatch):
    # 准备数据
    df = pd.DataFrame({
        'id': [1],
        'scenario': ['s1'],
        'input': ['hello'],
        'ground_truth': ['gt'],
        'output': [None],
        'label': [None],
    })

    # mock requests.Session.request
    import requests

    def fake_request(self, method, url, headers=None, params=None, json=None, data=None, timeout=None):
        return DummyResponse(status_code=200, json_data={'output': 'world'})

    monkeypatch.setattr(requests.Session, 'request', fake_request, raising=True)

    result = run_model(df, endpoint='http://fake', api_key='key')
    assert result.loc[0, 'output'] == 'world'
    assert result.loc[0, 'response_status'] == 200
    assert result.loc[0, 'request_elapsed_ms'] is not None