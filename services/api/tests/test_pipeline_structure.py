"""Structure of the Prefect pipeline: flow -> stages -> independent tasks with explicit inputs and outputs, and
optional steps invoked with ``return_state=True`` (so their failure cannot stop extract -> transform -> load)."""

from __future__ import annotations

import ast
import inspect
import textwrap

import pytest
from prefect import Flow, Task

from data.pipelines import pipeline

FLOW = pipeline.weekly_office_performance_flow
TASKS = {name: obj for name, obj in vars(pipeline).items() if isinstance(obj, Task)}
STAGE = {"extract": {"resolve_week_window", "extract_events", "count_window_events", "save_raw_snapshot"},
         "transform": {"validate_events", "check_currency_consistency", "aggregate_by_office_programme", "reconcile"},
         "load": {"load_weekly_performance", "save_eval_report"}}
OPTIONAL = {"count_window_events", "save_raw_snapshot", "save_eval_report"}


def _flow_ast() -> ast.FunctionDef:
    return ast.parse(textwrap.dedent(inspect.getsource(FLOW.fn))).body[0]  # type: ignore[return-value]


def test_the_pipeline_is_one_prefect_flow_with_extract_transform_and_load_stages():
    assert isinstance(FLOW, Flow) and FLOW.name == "weekly-office-performance"
    for stage, names in STAGE.items():
        assert names <= TASKS.keys(), stage
        for name in names:
            assert stage in TASKS[name].tags, f"{name} is not tagged {stage}"


# the flow calls these two through a local alias (`extract_events.with_options(refresh_cache=True)` when refreshing)
ALIASES = {"extract": "extract_events", "aggregate": "aggregate_by_office_programme"}


def _flow_calls_in_source_order() -> list[str]:
    calls = [(n.lineno, n.col_offset, ALIASES.get(n.func.id, n.func.id))
             for n in ast.walk(_flow_ast()) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    return [name for _, _, name in sorted(calls)]


def test_each_stage_is_a_task_and_the_flow_runs_them_in_order():
    """The flow calls extract, then transform, then load: the order of the design."""
    calls = _flow_calls_in_source_order()
    first = lambda stage: min(calls.index(c) for c in STAGE[stage] if c in calls)  # noqa: E731
    assert first("extract") < first("transform") < first("load")
    assert calls.index("extract_events") < calls.index("validate_events") < calls.index("aggregate_by_office_programme") < calls.index("load_weekly_performance")


@pytest.mark.parametrize("name", sorted(TASKS))
def test_every_task_declares_explicit_inputs_and_outputs(name):
    signature = inspect.signature(TASKS[name].fn)
    assert signature.return_annotation is not inspect.Signature.empty, f"{name} has no declared output"
    assert all(p.annotation is not inspect.Parameter.empty for p in signature.parameters.values()), f"{name} has an untyped input"


def test_tasks_are_independent_none_calls_another():
    """A task gets everything through its inputs and returns everything: it never calls a sibling task."""
    for name, task in TASKS.items():
        tree = ast.parse(textwrap.dedent(inspect.getsource(task.fn)))
        called = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        assert not (called & (TASKS.keys() - {name})), f"{name} calls another task"


def test_the_optional_steps_are_invoked_with_return_state_true_inside_the_flow():
    with_state = {
        n.func.id
        for n in ast.walk(_flow_ast())
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        and any(k.arg == "return_state" and isinstance(k.value, ast.Constant) and k.value.value is True for k in n.keywords)
    }
    assert with_state == OPTIONAL


def test_the_critical_steps_are_never_invoked_with_return_state():
    """A critical failure must stop the run, so those calls let their error propagate."""
    for n in ast.walk(_flow_ast()):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in TASKS.keys() - OPTIONAL:
            assert not any(k.arg == "return_state" for k in n.keywords), n.func.id


def test_the_optional_tasks_are_tagged_optional():
    assert {name for name, t in TASKS.items() if "optional" in t.tags} == OPTIONAL
