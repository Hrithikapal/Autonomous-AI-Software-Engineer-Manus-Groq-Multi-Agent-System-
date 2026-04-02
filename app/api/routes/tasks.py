"""
In-memory task store + CRUD routes.
In production, swap the dict for Redis or Postgres.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException

from app.models.task import Task, TaskCreate

router = APIRouter(prefix="/tasks", tags=["tasks"])

_store: dict[str, Task] = {}


def get_store() -> dict[str, Task]:
    return _store


@router.get("/", response_model=list[Task])
async def list_tasks(limit: int = 20, offset: int = 0):
    tasks = sorted(_store.values(), key=lambda t: t.created_at, reverse=True)
    return tasks[offset : offset + limit]


@router.get("/{task_id}", response_model=Task)
async def get_task(task_id: str):
    t = _store.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="Task not found")
    return t


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: str):
    if task_id not in _store:
        raise HTTPException(status_code=404, detail="Task not found")
    del _store[task_id]
