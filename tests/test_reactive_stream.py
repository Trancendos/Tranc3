"""
Tests for src/event_bus/reactive_stream.py
"""
import sys
import os
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Import directly from the module file to avoid triggering src/event_bus/__init__.py
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location(
    "reactive_stream",
    os.path.join(os.path.dirname(__file__), "..", "src", "event_bus", "reactive_stream.py"),
)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

Observable = _mod.Observable
ObservableSubject = _mod.ObservableSubject
Observer = _mod.Observer
from_iterable = _mod.from_iterable


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_observable_emits_values_to_observer():
    received = []
    obs = from_iterable([1, 2, 3])
    obs.subscribe(on_next=received.append)
    assert received == [1, 2, 3]


def test_map_operator_transforms_values():
    received = []
    from_iterable([1, 2, 3]).map(lambda x: x * 2).subscribe(on_next=received.append)
    assert received == [2, 4, 6]


def test_filter_operator_excludes_values():
    received = []
    from_iterable([1, 2, 3, 4, 5]).filter(lambda x: x % 2 == 0).subscribe(
        on_next=received.append
    )
    assert received == [2, 4]


def test_subject_multicasts_to_multiple_subscribers():
    sub = ObservableSubject()
    a: list = []
    b: list = []
    sub.subscribe(on_next=a.append)
    sub.subscribe(on_next=b.append)
    sub.emit(10)
    sub.emit(20)
    assert a == [10, 20]
    assert b == [10, 20]


def test_take_operator_limits_emissions():
    received = []
    completed = []
    from_iterable(range(10)).take(3).subscribe(
        on_next=received.append,
        on_complete=lambda: completed.append(True),
    )
    assert received == [0, 1, 2]
    assert completed == [True]


def test_skip_operator_skips_first_n():
    received = []
    from_iterable([1, 2, 3, 4, 5]).skip(2).subscribe(on_next=received.append)
    assert received == [3, 4, 5]


def test_merge_with_combines_two_observables():
    received = []
    o1 = from_iterable([1, 2])
    o2 = from_iterable([3, 4])
    o1.merge_with(o2).subscribe(on_next=received.append)
    assert sorted(received) == [1, 2, 3, 4]


def test_zip_with_pairs_values():
    received = []
    o1 = from_iterable([1, 2, 3])
    o2 = from_iterable(["a", "b", "c"])
    o1.zip_with(o2).subscribe(on_next=received.append)
    assert received == [(1, "a"), (2, "b"), (3, "c")]


def test_on_complete_called_once():
    completions = []
    from_iterable([1, 2]).subscribe(on_complete=lambda: completions.append(1))
    assert completions == [1]


def test_disposable_cancels_subject_subscription():
    sub = ObservableSubject()
    received: list = []
    d = sub.subscribe(on_next=received.append)
    sub.emit(1)
    d.dispose()
    sub.emit(2)
    assert received == [1]


def test_throttle_limits_emission_rate():
    received = []
    subject = ObservableSubject()
    subject.throttle(0.1).subscribe(on_next=received.append)

    for _ in range(10):
        subject.emit(1)

    # Only 1 emission should pass through immediately
    assert len(received) <= 3  # generous bound


def test_on_error_propagates():
    errors = []

    def bad_transform(x: int) -> int:
        raise ValueError("boom")

    from_iterable([1]).map(bad_transform).subscribe(
        on_next=lambda v: None,
        on_error=errors.append,
    )
    assert len(errors) == 1
    assert isinstance(errors[0], ValueError)
