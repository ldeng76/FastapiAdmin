"""Prometheus Metrics 配置

集成 prometheus-fastapi-instrumentator，自动采集 HTTP 请求指标，
暴露 /metrics 端点供 Prometheus 抓取。

采集指标：
- http_requests_total: 请求总数（按 method、endpoint、status 分组）
- http_request_duration_seconds: 请求延迟直方图
- http_requests_in_progress: 当前处理中的请求数
"""

from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from prometheus_fastapi_instrumentator import Instrumentator, metrics


def setup_metrics(app: FastAPI) -> None:
    """初始化 Prometheus 指标采集

    自动为所有 HTTP 端点采集请求指标，暴露 /metrics 端点。

    参数:
        app: FastAPI 应用实例

    返回:
        None
    """
    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=False,
        should_instrument_requests_inprogress=True,
        excluded_handlers=[
            "/metrics",
            "/health",
            "/health/live",
            "/health/ready",
            "/docs",
            "/redoc",
            "/ljdoc",
            "/openapi.json",
            "/static/.*",
            "/favicon.ico",
        ],
        inprogress_name="http_requests_in_progress",
        inprogress_labels=True,
    )

    # 添加自定义指标
    instrumentator.add(
        metrics.request_size(
            should_include_handler=True,
            should_include_method=True,
            should_include_status=True,
            metric_name="http_request_size_bytes",
        )
    ).add(
        metrics.response_size(
            should_include_handler=True,
            should_include_method=True,
            should_include_status=True,
            metric_name="http_response_size_bytes",
        )
    ).add(
        metrics.latency(
            metric_name="http_request_duration_seconds",
            metric_doc="HTTP 请求延迟（秒）",
        )
    ).add(
        metrics.requests(
            metric_name="http_requests_total",
            metric_doc="HTTP 请求总数",
        )
    )

    # 启动采集
    instrumentator.instrument(app)

    # 手动注册 /metrics 端点，避免 prometheus_fastapi_instrumentator.expose()
    # 的 response_class=None 与 FastAPI OpenAPI 生成不兼容的问题
    @app.get("/metrics", include_in_schema=False)
    async def metrics_endpoint():
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
