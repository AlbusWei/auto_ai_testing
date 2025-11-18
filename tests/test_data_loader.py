import os
import re

import pandas as pd

from data_loader import load_and_copy_testset


def test_load_and_copy_csv(tmp_path):
    # 构造一个临时CSV
    p = tmp_path / 'sample.csv'
    df = pd.DataFrame({
        '序号': [1, 2],
        'scenario': ['s1', 's2'],
        'input': ['hello', 'world'],
        'ground_truth': ['gt1', 'gt2'],
    })
    df.to_csv(p, index=False, encoding='utf-8')

    copied_path, loaded_df, base_name = load_and_copy_testset(str(p), test_sets_dir='test_sets')

    assert os.path.exists(copied_path)
    # 文件名应带时间戳
    assert re.search(r"_\d{8}_\d{6}", os.path.basename(copied_path))
    # 列名规范化与预置列
    assert set(['id', 'scenario', 'input', 'ground_truth']).issubset(set(loaded_df.columns))
    assert 'output' in loaded_df.columns
    assert 'label' in loaded_df.columns