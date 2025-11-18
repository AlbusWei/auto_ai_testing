import os
from typing import Tuple

import pandas as pd

from utils.files import copy_with_timestamp, detect_file_type, ensure_dir
from utils.logger import get_logger


logger = get_logger(__name__)


REQUIRED_COLUMNS = {
    'id': ['序号', 'id', 'ID'],
    'scenario': ['scenario', '场景'],
    'input': ['input', '模型输入', '输入'],
    'ground_truth': ['ground_truth', '参考答案', '要求描述', '标准答案'],
}


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    col_map = {}
    for unified, candidates in REQUIRED_COLUMNS.items():
        for c in df.columns:
            if c.strip() in candidates:
                col_map[c] = unified
                break
    # 重命名匹配到的列
    df = df.rename(columns=col_map)
    missing = [k for k in REQUIRED_COLUMNS.keys() if k not in df.columns]
    if missing:
        raise ValueError(f'缺少必要列: {missing}，必须包含: 序号、scenario、input、ground_truth')
    return df


def _validate(df: pd.DataFrame) -> None:
    # id唯一
    if df['id'].duplicated().any():
        dup = df[df['id'].duplicated()]['id'].tolist()
        raise ValueError(f'序号(id)必须唯一，重复值: {dup[:5]}')
    # input非空
    if df['input'].isna().any():
        rows = df[df['input'].isna()].index.tolist()
        raise ValueError(f'input列存在空值，行索引: {rows[:5]}')


def load_and_copy_testset(dataset_path: str, test_sets_dir: str = 'test_sets') -> Tuple[str, pd.DataFrame, str]:
    """
    读取测试集并复制到专用目录(带时间戳)。返回(复制后路径, 数据框, 基础文件名不含扩展)。
    """
    if not os.path.exists(dataset_path):
        raise FileNotFoundError(f'测试集文件不存在: {dataset_path}')
    ensure_dir(test_sets_dir)
    copied_path = copy_with_timestamp(dataset_path, test_sets_dir)
    ftype = detect_file_type(copied_path)
    logger.info(f'加载测试集: {copied_path} (类型: {ftype})')
    if ftype == 'csv':
        df = pd.read_csv(copied_path, encoding='utf-8')
    else:
        df = pd.read_excel(copied_path)
    df = _normalize_columns(df)
    _validate(df)
    # 若不存在output/label列则补充
    if 'output' not in df.columns:
        df['output'] = None
    if 'label' not in df.columns:
        df['label'] = None
    base_name = os.path.splitext(os.path.basename(copied_path))[0]
    return copied_path, df, base_name