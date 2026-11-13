"""Contract tests for the versioned n8n workflow export.

The workflow is executed by n8n, not by Python, so these tests only pin the
import contract that the Stage 5 design depends on: two triggers, one HTTP
Request node, no credentials, no data logic, and no accidental activation.
"""

import json
import uuid
from pathlib import Path

import pytest

WORKFLOW_PATH = Path(__file__).resolve().parents[1] / "n8n" / "workflows" / "automotive-pipeline.json"

if not WORKFLOW_PATH.is_file():
    pytest.skip(
        "n8n workflow export is outside the API image build context",
        allow_module_level=True,
    )

MANUAL_TRIGGER = "n8n-nodes-base.manualTrigger"
SCHEDULE_TRIGGER = "n8n-nodes-base.scheduleTrigger"
HTTP_REQUEST = "n8n-nodes-base.httpRequest"

PIPELINE_RUN_URL = "http://pipeline-api:8000/pipeline/runs"


def load_workflow() -> dict:
    return json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))


def nodes_by_type(workflow: dict, node_type: str) -> list[dict]:
    return [node for node in workflow["nodes"] if node["type"] == node_type]


def test_workflow_is_named_inactive_and_utc() -> None:
    workflow = load_workflow()

    assert workflow["name"].strip()
    assert workflow["description"].strip()
    assert workflow["active"] is False
    assert workflow["settings"]["timezone"] == "UTC"
    assert workflow["pinData"] == {}
    uuid.UUID(workflow["versionId"])


def test_workflow_has_exactly_two_triggers_and_one_http_node() -> None:
    workflow = load_workflow()

    manual = nodes_by_type(workflow, MANUAL_TRIGGER)
    schedule = nodes_by_type(workflow, SCHEDULE_TRIGGER)
    http = nodes_by_type(workflow, HTTP_REQUEST)

    assert len(manual) == 1
    assert len(schedule) == 1
    assert len(http) == 1
    assert len(workflow["nodes"]) == 3

    assert manual[0]["typeVersion"] == 1
    assert schedule[0]["typeVersion"] == 1.3
    assert http[0]["typeVersion"] == 4.5

    for node in workflow["nodes"]:
        assert uuid.UUID(node["id"])
        assert isinstance(node["position"], list) and len(node["position"]) == 2


def test_both_triggers_call_the_http_node_directly() -> None:
    workflow = load_workflow()

    http_name = nodes_by_type(workflow, HTTP_REQUEST)[0]["name"]
    expected = [{"node": http_name, "type": "main", "index": 0}]

    connections = workflow["connections"]
    assert set(connections) == {"Manual Trigger", "Schedule Trigger"}
    for trigger_name, trigger_connections in connections.items():
        assert trigger_name in {node["name"] for node in workflow["nodes"]}
        assert trigger_connections["main"] == [expected]


def test_http_node_posts_to_the_pipeline_without_auth() -> None:
    workflow = load_workflow()
    parameters = nodes_by_type(workflow, HTTP_REQUEST)[0]["parameters"]

    assert parameters["method"] == "POST"
    assert parameters["url"] == PIPELINE_RUN_URL
    assert parameters["authentication"] == "none"
    assert parameters["options"]["timeout"] == 120_000
    assert "sendBody" not in parameters or parameters["sendBody"] is False
    assert "credentials" not in nodes_by_type(workflow, HTTP_REQUEST)[0]


def test_schedule_trigger_runs_daily_at_nine_utc() -> None:
    workflow = load_workflow()
    rule = nodes_by_type(workflow, SCHEDULE_TRIGGER)[0]["parameters"]["rule"]

    assert rule["interval"] == [
        {
            "field": "days",
            "daysInterval": 1,
            "triggerAtHour": 9,
            "triggerAtMinute": 0,
        }
    ]
