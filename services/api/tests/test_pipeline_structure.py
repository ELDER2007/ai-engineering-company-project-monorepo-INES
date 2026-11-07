"""Structure of the Prefect pipeline: a main flow that only COORDINATES, one subflow per phase (extract, transform, load) plus
the optional ones, tasks inside the subflows, explicit typed inputs and outputs, and ``return_state=True`` on the optional
subflows only (so their failure cannot stop extract -> transform -> load)."""

from __future__ import annotations

import ast
import inspect
import textwrap

import pytest
from prefect import Flow, Task

from data.pipelines import pipeline

MAIN = pipeline.weekly_office_performance_flow
TASKS = {name: obj for name, obj in vars(pipeline).items() if isinstance(obj, Task)}
SUBFLOWS = {name: obj for name, obj in vars(pipeline).items() if isinstance(obj, Flow) and obj is not MAIN}

PHASE_SUBFLOWS = ["extract_kpi_events_subflow", "transform_weekly_kpis_subflow", "load_weekly_office_program_performance_subflow"]
OPTIONAL_SUBFLOWS = {"window_liveness_count_subflow", "raw_events_snapshot_subflow", "validation_report_subflow"}
STAGE = {"extract": {"resolve_week_window", "extract_events", "count_window_events", "save_raw_snapshot"},
         "transform": {"validate_events", "check_currency_consistency", "deduplicate_events", "calculate_total_material_cost", "count_kits_delivered", "count_shortage_events", "count_cost_variance_events",
                       "build_weekly_kpi_rows", "reconcile"},
         "load": {"load_weekly_performance", "save_eval_report"}}
OPTIONAL_TASKS = {"count_window_events", "save_raw_snapshot", "save_eval_report"}
COORDINATION_TASKS = {"resolve_week_window", "start_pipeline_run", "finish_pipeline_run"}  # the main flow may call these itself


def _ast(flow_or_task) -> ast.FunctionDef:
    return ast.parse(textwrap.dedent(inspect.getsource(flow_or_task.fn))).body[0]  # type: ignore[return-value]


def _calls(node: ast.AST) -> list[ast.Call]:
    """The plain-name calls of a function body, in the order they appear in the source."""
    found = [n for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    return sorted(found, key=lambda n: (n.lineno, n.col_offset))


def _called_names(node: ast.AST, aliases: dict[str, str] | None = None) -> list[str]:
    return [(aliases or {}).get(c.func.id, c.func.id) for c in _calls(node)]


# ---------------------------------------------------------------- the topology: main flow -> subflows -> tasks


def test_there_are_at_least_three_subflows_one_per_phase_and_each_is_a_prefect_flow():
    assert isinstance(MAIN, Flow) and MAIN.name == "weekly-office-performance"
    assert set(PHASE_SUBFLOWS) <= SUBFLOWS.keys() and len(SUBFLOWS) >= 3
    assert all(isinstance(SUBFLOWS[name], Flow) for name in PHASE_SUBFLOWS)


def test_the_subflows_are_named_after_the_kpis_and_the_destination_table_of_the_briefing():
    names = {f.name for f in SUBFLOWS.values()}
    assert {"extract-kpi-events", "transform-weekly-kpis", "load-weekly-office-program-performance"} <= names
    assert pipeline.storage.weekly_performance.name == "weekly_office_program_performance"  # the load subflow's name is this table's


def test_the_main_flow_calls_the_phases_in_order_extract_then_transform_then_load():
    calls = _called_names(_ast(MAIN))
    assert calls.index("extract_kpi_events_subflow") < calls.index("transform_weekly_kpis_subflow") \
        < calls.index("load_weekly_office_program_performance_subflow")


def test_the_main_flow_only_coordinates_it_calls_no_task_of_a_phase():
    """The phases' logic lives in the subflows: the main flow may call the subflows and the run-log tasks, nothing else."""
    called_tasks = set(_called_names(_ast(MAIN))) & TASKS.keys()
    assert called_tasks <= COORDINATION_TASKS, called_tasks - COORDINATION_TASKS


def test_each_phase_subflow_calls_the_tasks_of_its_own_phase_in_order():
    aliases = {"extract": "extract_events"}  # the local alias the extraction subflow uses for its refresh option
    of = lambda name: [c for c in _called_names(_ast(SUBFLOWS[name]), aliases) if c in TASKS]  # noqa: E731
    assert of("extract_kpi_events_subflow") == ["extract_events"]
    assert of("transform_weekly_kpis_subflow") == [
        "validate_events", "check_currency_consistency", "deduplicate_events",
        "calculate_total_material_cost", "count_kits_delivered", "count_shortage_events", "count_cost_variance_events",  # one per KPI
        "build_weekly_kpi_rows", "reconcile"]
    assert of("load_weekly_office_program_performance_subflow") == ["load_weekly_performance"]


def test_every_task_belongs_to_a_stage_and_is_tagged_with_it():
    for stage, names in STAGE.items():
        assert names <= TASKS.keys(), stage
        for name in names:
            assert stage in TASKS[name].tags, f"{name} is not tagged {stage}"


# ---------------------------------------------------------------- explicit inputs and outputs, and independence


@pytest.mark.parametrize("name", sorted(TASKS) + sorted(SUBFLOWS))
def test_every_task_and_subflow_declares_explicit_inputs_and_outputs(name):
    signature = inspect.signature((TASKS | SUBFLOWS)[name].fn)
    assert signature.return_annotation is not inspect.Signature.empty, f"{name} has no declared output"
    assert all(p.annotation is not inspect.Parameter.empty for p in signature.parameters.values()), f"{name} has an untyped input"


def test_tasks_are_independent_none_calls_another():
    for name, task in TASKS.items():
        assert not (set(_called_names(_ast(task))) & (TASKS.keys() - {name})), f"{name} calls another task"


def test_subflows_are_independent_none_calls_another_subflow():
    """Each phase can be run and reused by itself: it needs nothing another phase did."""
    for name, subflow in SUBFLOWS.items():
        assert not (set(_called_names(_ast(subflow))) & (SUBFLOWS.keys() - {name})), f"{name} calls another subflow"


def test_no_subflow_reads_a_global_variable_that_another_could_have_changed():
    """They talk through inputs and outputs only: no subflow touches a module-level dict, list or set."""
    shared = {name for name, value in vars(pipeline).items() if isinstance(value, (dict, list, set)) and not name.startswith("__")}
    assert "_ACTIVE_TARGETS" in shared  # (it exists: it belongs to the crash hook of the main flow)
    for name, subflow in SUBFLOWS.items():
        assert not (set(subflow.fn.__code__.co_names) & shared), f"{name} reads a shared global"


# ---------------------------------------------------------------- the optional subflows and return_state=True


def _with_return_state(node: ast.AST) -> set[str]:
    return {c.func.id for c in _calls(node)
            if any(k.arg == "return_state" and isinstance(k.value, ast.Constant) and k.value.value is True for k in c.keywords)}


def test_the_optional_subflows_are_called_from_the_main_flow_with_return_state_true():
    assert _with_return_state(_ast(MAIN)) == OPTIONAL_SUBFLOWS


def test_the_critical_phases_are_never_called_with_return_state_so_their_failure_stops_the_run():
    critical = set(PHASE_SUBFLOWS)
    for call in _calls(_ast(MAIN)):
        if call.func.id in critical:
            assert not any(k.arg == "return_state" for k in call.keywords), call.func.id


def test_the_optional_tasks_are_tagged_optional_and_live_inside_the_optional_subflows():
    assert {name for name, t in TASKS.items() if "optional" in t.tags} == OPTIONAL_TASKS
    inside = {c for s in OPTIONAL_SUBFLOWS for c in _called_names(_ast(SUBFLOWS[s])) if c in TASKS}
    assert inside == OPTIONAL_TASKS
