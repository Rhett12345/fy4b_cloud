"""配置加载模块"""

import os
import yaml


def load_config(config_path=None):
    """加载 YAML 配置文件"""
    if config_path is None:
        config_path = os.path.join(
            os.path.dirname(__file__), "..", "config", "fy4b.yaml"
        )
    config_path = os.path.abspath(config_path)

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    return cfg


def get_channel_config(cfg, channel_id):
    """根据通道ID获取通道配置"""
    channel_id = channel_id.upper()
    for ch in cfg["channels"]:
        if ch["id"] == channel_id:
            return ch
    return None
