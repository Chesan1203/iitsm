from datetime import datetime, timedelta

import pytest

from app.domain.exceptions import InvalidInputError
from app.domain.time_provider import SimulatedTimeProvider, SystemTimeProvider, TimeProvider


def test_system_provider_is_close_to_real_time():
    assert abs(SystemTimeProvider().now() - datetime.now()) < timedelta(seconds=1)


def test_simulated_provider_advances_by_exactly_the_offset():
    clock = SimulatedTimeProvider()
    before = clock.now()
    clock.advance(timedelta(minutes=30))
    gap = clock.now() - before
    assert timedelta(minutes=30) <= gap < timedelta(minutes=30, seconds=1)
    assert clock.offset == timedelta(minutes=30)


def test_simulated_provider_accumulates_and_resets():
    clock = SimulatedTimeProvider()
    clock.advance(timedelta(minutes=5))
    clock.advance(timedelta(minutes=10))
    assert clock.offset == timedelta(minutes=15)
    clock.reset()
    assert clock.offset == timedelta(0)
    assert abs(clock.now() - datetime.now()) < timedelta(seconds=1)


def test_simulated_provider_rejects_negative_or_wrong_type():
    clock = SimulatedTimeProvider()
    with pytest.raises(InvalidInputError):
        clock.advance(timedelta(minutes=-1))
    with pytest.raises(InvalidInputError):
        clock.advance(30)


def test_time_provider_is_abstract():
    with pytest.raises(TypeError):
        TimeProvider()
