from __future__ import annotations

import os
import time
import uuid

os.environ.setdefault("AGENT_API_TOKEN", "test-token")
os.environ.setdefault("COMPANION_DB_PATH", "/tmp/neighborhood-companion-test.sqlite3")

from fastapi.testclient import TestClient

from companion.app import API_TOKEN, app
from companion.models import Envelope


def test_websocket_set_time_vertical_slice() -> None:
    with TestClient(app) as client:
        with client.websocket_connect(
            "/v1/gateway",
            headers={"Authorization": f"Bearer {API_TOKEN}"},
        ) as socket:
            socket.send_text(
                Envelope(
                    type="hello",
                    payload={
                        "server_id": "test",
                        "capabilities": ["set_time", "set_weather"],
                    },
                ).model_dump_json()
            )
            hello = Envelope.model_validate_json(socket.receive_text())
            assert hello.type == "hello.ack"

            job_id = str(uuid.uuid4())
            trace_id = str(uuid.uuid4())
            started = time.perf_counter()
            socket.send_text(
                Envelope(
                    type="job.submit",
                    trace_id=trace_id,
                    job_id=job_id,
                    deadline_ms=int(time.time() * 1000) + 10_000,
                    payload={
                        "prompt": "make it daytime",
                        "player": {
                            "name": "Builder",
                            "uuid": str(uuid.uuid4()),
                            "world": "minecraft:overworld",
                            "x": 0,
                            "y": 64,
                            "z": 0,
                            "gamemode": "creative",
                        },
                    },
                ).model_dump_json()
            )
            action = Envelope.model_validate_json(socket.receive_text())
            assert action.type == "action.execute"
            assert action.payload["tool"] == "set_time"
            assert action.payload["arguments"] == {"time": "day"}

            socket.send_text(
                Envelope(
                    type="action.result",
                    trace_id=trace_id,
                    job_id=job_id,
                    payload={
                        "action_id": action.payload["action_id"],
                        "ok": True,
                        "executed": True,
                        "verified": True,
                        "message": "Made it daytime.",
                        "execution_ms": 1,
                        "data": {},
                    },
                ).model_dump_json()
            )
            completed = Envelope.model_validate_json(socket.receive_text())
            assert completed.type == "job.complete"
            assert completed.payload["ok"] is True
            assert completed.payload["verified"] is True
            assert completed.payload["spoken_text"] == "Made it daytime."
            assert " · " not in completed.payload["spoken_text"]
            assert (time.perf_counter() - started) * 1000 < 500

            failed_job = str(uuid.uuid4())
            failed_trace = str(uuid.uuid4())
            socket.send_text(
                Envelope(
                    type="job.submit",
                    trace_id=failed_trace,
                    job_id=failed_job,
                    payload={
                        "prompt": "set weather to clear",
                        "player": {
                            "name": "Builder",
                            "uuid": str(uuid.uuid4()),
                            "world": "minecraft:overworld",
                            "x": 0,
                            "y": 64,
                            "z": 0,
                            "gamemode": "creative",
                        },
                    },
                ).model_dump_json()
            )
            failed_action = Envelope.model_validate_json(socket.receive_text())
            socket.send_text(
                Envelope(
                    type="action.result",
                    trace_id=failed_trace,
                    job_id=failed_job,
                    payload={
                        "action_id": failed_action.payload["action_id"],
                        "ok": True,
                        "executed": True,
                        "verified": False,
                        "message": "Verification failed.",
                        "execution_ms": 1,
                        "data": {},
                    },
                ).model_dump_json()
            )
            failed_complete = Envelope.model_validate_json(socket.receive_text())
            assert failed_complete.type == "job.complete"
            assert failed_complete.payload["ok"] is False
        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        assert "companion_gateway_connected 0" in metrics.text
        assert 'companion_jobs_total{status="done"}' in metrics.text

