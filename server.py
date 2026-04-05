"""WorkAgent FastAPI 服务

服务端启动入口，放在根目录便于直接运行。
"""

from __future__ import annotations

import structlog
import uvicorn

from api import create_app
from api.routes import init_app_state
from config import get_config


def main():
    """主入口"""
    import argparse

    # 先加载配置
    config = get_config()

    parser = argparse.ArgumentParser(description="WorkAgent Server")
    parser.add_argument("--host", default=config.server.host, help="绑定地址")
    parser.add_argument("--port", type=int, default=config.server.port, help="绑定端口")
    parser.add_argument("--reload", action="store_true", help="开发模式自动重载")

    args = parser.parse_args()

    # 配置结构化日志
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # 初始化应用状态
    init_app_state()

    # 启动服务
    uvicorn.run(
        "api:create_app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        factory=True,
    )


if __name__ == "__main__":
    main()
