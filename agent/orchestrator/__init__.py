"""Orchestrator package — re-exports the FastAPI app and helpers."""

from agent.orchestrator import app as app_module

app = app_module.app

for _name in dir(app_module):
    if _name.startswith("__"):
        continue
    globals()[_name] = getattr(app_module, _name)
