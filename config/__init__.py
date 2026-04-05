"""WorkAgent 配置管理模块

支持 YAML 配置文件加载和管理。
"""

from .loader import Config, load_config, get_config, reload_config

__all__ = ["Config", "load_config", "get_config", "reload_config"]
