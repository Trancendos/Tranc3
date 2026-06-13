"""
Tests for src/core/smart_container.py
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.smart_container import DIError, Lifetime, SmartContainer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class ServiceA:
    pass


class ServiceB:
    def __init__(self, a: ServiceA) -> None:
        self.a = a


class ServiceC:
    def __init__(self, a: ServiceA, b: ServiceB) -> None:
        self.a = a
        self.b = b


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_singleton_returns_same_instance():
    c = SmartContainer()
    c.register(ServiceA, lifetime=Lifetime.SINGLETON)
    inst1 = c.resolve(ServiceA)
    inst2 = c.resolve(ServiceA)
    assert inst1 is inst2


def test_transient_returns_new_instance_each_time():
    c = SmartContainer()
    c.register(ServiceA, lifetime=Lifetime.TRANSIENT)
    inst1 = c.resolve(ServiceA)
    inst2 = c.resolve(ServiceA)
    assert inst1 is not inst2


def test_autowire_resolves_dependencies():
    c = SmartContainer()
    c.register(ServiceA, lifetime=Lifetime.SINGLETON)
    c.register(ServiceB, lifetime=Lifetime.SINGLETON)
    b = c.resolve(ServiceB)
    assert isinstance(b, ServiceB)
    assert isinstance(b.a, ServiceA)


def test_autowire_resolves_multi_level_dependencies():
    c = SmartContainer()
    c.register(ServiceA, lifetime=Lifetime.SINGLETON)
    c.register(ServiceB, lifetime=Lifetime.SINGLETON)
    c.register(ServiceC, lifetime=Lifetime.SINGLETON)
    svc = c.resolve(ServiceC)
    assert isinstance(svc, ServiceC)
    assert isinstance(svc.a, ServiceA)
    assert isinstance(svc.b, ServiceB)


def test_request_scope_isolates_instances():
    c = SmartContainer()
    c.register(ServiceA, lifetime=Lifetime.REQUEST)
    with c.request_scope():
        inst1 = c.resolve(ServiceA)
        inst2 = c.resolve(ServiceA)
        # Same instance within the same scope
        assert inst1 is inst2
    with c.request_scope():
        inst3 = c.resolve(ServiceA)
        # Different scope → different instance
        assert inst3 is not inst1


def test_unregistered_type_raises_di_error():
    c = SmartContainer()
    with pytest.raises(DIError):
        c.resolve(ServiceA)


def test_register_instance_is_always_same():
    c = SmartContainer()
    obj = ServiceA()
    c.register_instance(ServiceA, obj)
    assert c.resolve(ServiceA) is obj
    assert c.resolve(ServiceA) is obj


def test_try_resolve_returns_none_for_missing():
    c = SmartContainer()
    assert c.try_resolve(ServiceA) is None


def test_is_registered():
    c = SmartContainer()
    assert not c.is_registered(ServiceA)
    c.register(ServiceA)
    assert c.is_registered(ServiceA)


def test_register_factory():
    c = SmartContainer()
    counter = [0]

    def factory() -> ServiceA:
        counter[0] += 1
        return ServiceA()

    c.register_factory(ServiceA, factory, lifetime=Lifetime.TRANSIENT)
    c.resolve(ServiceA)
    c.resolve(ServiceA)
    assert counter[0] == 2


def test_request_scope_raises_outside_scope():
    c = SmartContainer()
    c.register(ServiceA, lifetime=Lifetime.REQUEST)
    with pytest.raises(DIError):
        c.resolve(ServiceA)
