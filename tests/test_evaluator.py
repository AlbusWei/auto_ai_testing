import pandas as pd

from evaluator import evaluate


class DummyResponse:
    def __init__(self, status_code=200, json_data=None, text='OK', headers=None):
        self.status_code = status_code
        self._json = json_data or {'score': 1}
        self.text = text
        self.headers = headers or {'Content-Type': 'application/json'}

    def json(self):
        return self._json


def test_evaluate_single(monkeypatch, tmp_path):
    df = pd.DataFrame({
        'id': [1],
        'scenario': ['s1'],
        'input': ['hello'],
        'ground_truth': ['gt'],
        'output': ['world'],
        'label': [None],
    })

    import requests

    def fake_request(self, method, url, headers=None, params=None, json=None, data=None, timeout=None):
        return DummyResponse(status_code=200, json_data={'score': 1})

    monkeypatch.setattr(requests.Session, 'request', fake_request, raising=True)

    res_df, out_path = evaluate(
        df,
        copied_dataset_path=str(tmp_path / 'dummy.csv'),
        endpoint='http://fake-judge',
        api_key='key',
        batch_size=1,
        max_merge_rows=1,
        timeout=10,
        retries=1,
        base_name='dummy',
    )
    assert res_df.loc[0, 'label'] == 1
    assert out_path.endswith('.csv')