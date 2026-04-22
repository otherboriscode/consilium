"""
Тонкая обёртка над YAML-шаблоном `product_concept` для обратной совместимости.
Реальная конфигурация — в `templates_default/product_concept.yaml`.
"""
from consilium.models import JobConfig
from consilium.templates import load_template


def build_default_council(topic: str) -> JobConfig:
    """Backwards-compatible entry point. Loads templates_default/product_concept.yaml."""
    template = load_template("product_concept")
    return template.build_config(topic=topic)
