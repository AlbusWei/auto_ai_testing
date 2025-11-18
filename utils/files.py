import os
import shutil
import time
from typing import Tuple


def ensure_dir(path: str) -> None:
    """确保目录存在。"""
    if not path:
        return
    os.makedirs(path, exist_ok=True)


def timestamp_now() -> str:
    """返回当前时间戳字符串，格式YYYYMMDD_%H%M%S。"""
    return time.strftime('%Y%m%d_%H%M%S', time.localtime())


def detect_file_type(path: str) -> str:
    """检测文件类型：csv或excel。"""
    ext = os.path.splitext(path)[1].lower()
    if ext == '.csv':
        return 'csv'
    if ext in {'.xlsx', '.xls'}:
        return 'excel'
    raise ValueError(f'不支持的文件格式: {ext}')


def copy_with_timestamp(src_path: str, dest_dir: str) -> str:
    """
    将文件复制到dest_dir，并在文件名后追加时间戳。
    返回复制后的目标路径。
    """
    ensure_dir(dest_dir)
    base = os.path.basename(src_path)
    name, ext = os.path.splitext(base)
    ts = timestamp_now()
    dest_name = f"{name}_{ts}{ext}"
    dest_path = os.path.join(dest_dir, dest_name)
    shutil.copy2(src_path, dest_path)
    return dest_path


def derive_output_path(dest_dir: str, base_name: str, suffix: str, ext: str) -> str:
    """根据基本名与后缀生成输出/评估文件路径。ext应为带点的扩展名。"""
    ensure_dir(dest_dir)
    ts = timestamp_now()
    fname = f"{base_name}_{ts}_{suffix}{ext}"
    return os.path.join(dest_dir, fname)