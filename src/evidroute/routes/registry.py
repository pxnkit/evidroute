from __future__ import annotations

from evidroute.datasets import CorpusStore
from evidroute.models import RouteName
from evidroute.routes.adapters import (
    BM25Route,
    DenseRoute,
    FrozenWebRoute,
    LiveWebRoute,
    MemoryRoute,
    ParametricRoute,
    StructuredRoute,
)
from evidroute.routes.base import RouteAdapter


class RouteRegistry:
    def __init__(self, store: CorpusStore) -> None:
        adapters: list[RouteAdapter] = [
            ParametricRoute(),
            MemoryRoute(store),
            BM25Route(store),
            DenseRoute(store),
            StructuredRoute(store),
            FrozenWebRoute(store),
            LiveWebRoute(),
        ]
        self._adapters = {adapter.name: adapter for adapter in adapters}

    def get(self, name: RouteName) -> RouteAdapter:
        return self._adapters[name]

    def all(self) -> list[RouteAdapter]:
        return list(self._adapters.values())

    def close(self) -> None:
        for adapter in self._adapters.values():
            adapter.close()
