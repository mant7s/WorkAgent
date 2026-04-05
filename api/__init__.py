"""WorkAgent API 模块

对外暴露 API 接口的路由定义。
"""

from .routes import create_app

__all__ = ["create_app"]
