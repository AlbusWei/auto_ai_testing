import configparser
from typing import Any, Dict, Optional


def load_config(config_path: Optional[str]) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    if config_path:
        cfg.read(config_path, encoding='utf-8')
    return cfg


def get_config_value(cfg: configparser.ConfigParser, section: str, key: str, default: Optional[str] = None) -> Optional[str]:
    if cfg.has_section(section) and cfg.has_option(section, key):
        return cfg.get(section, key)
    return default


def merge_cli_overrides(base: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in overrides.items():
        if v is not None:
            out[k] = v
    return out