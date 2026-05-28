"""In-memory job store with LRU eviction."""

from __future__ import annotations

import os
from collections import OrderedDict
from typing import Generic, TypeVar

T = TypeVar("T")

_MAX_JOBS = int(os.environ.get("AGENT_MAX_JOBS", "500"))


class JobStore(Generic[T]):
    def __init__(self, max_size: int = _MAX_JOBS) -> None:
        self._max = max(1, max_size)
        self._items: OrderedDict[str, T] = OrderedDict()

    def set(self, job_id: str, job: T) -> None:
        if job_id in self._items:
            self._items.move_to_end(job_id)
        self._items[job_id] = job
        while len(self._items) > self._max:
            self._items.popitem(last=False)

    def get(self, job_id: str) -> T | None:
        job = self._items.get(job_id)
        if job is not None:
            self._items.move_to_end(job_id)
        return job

    def __len__(self) -> int:
        return len(self._items)
