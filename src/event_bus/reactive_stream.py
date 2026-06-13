"""RxPY-inspired reactive streams — stdlib only."""
from __future__ import annotations

import queue
import threading
import time
from functools import reduce
from typing import Any, Callable, Generic, Iterable, Optional, TypeVar

T = TypeVar("T")
U = TypeVar("U")

_SENTINEL = object()


class Disposable:
    """Cancels a subscription when disposed."""

    def __init__(self, cancel_fn: Callable[[], None]) -> None:
        self._cancel = cancel_fn
        self._disposed = False
        self._lock = threading.Lock()

    def dispose(self) -> None:
        with self._lock:
            if not self._disposed:
                self._disposed = True
                self._cancel()

    @property
    def disposed(self) -> bool:
        return self._disposed

    def __enter__(self) -> "Disposable":
        return self

    def __exit__(self, *_: Any) -> None:
        self.dispose()


class Observer(Generic[T]):
    """Consumes values, errors, and completion signals."""

    def __init__(
        self,
        on_next: Optional[Callable[[T], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        on_complete: Optional[Callable[[], None]] = None,
    ) -> None:
        self._on_next = on_next or (lambda _: None)
        self._on_error = on_error or (lambda e: None)
        self._on_complete = on_complete or (lambda: None)
        self._done = False
        self._lock = threading.Lock()

    def on_next(self, value: T) -> None:
        with self._lock:
            if self._done:
                return
        self._on_next(value)

    def on_error(self, error: Exception) -> None:
        with self._lock:
            if self._done:
                return
            self._done = True
        self._on_error(error)

    def on_complete(self) -> None:
        with self._lock:
            if self._done:
                return
            self._done = True
        self._on_complete()


class Observable(Generic[T]):
    """Push-based stream with operator chaining."""

    def __init__(self, subscribe_fn: Callable[[Observer[T]], Disposable]) -> None:
        self._subscribe_fn = subscribe_fn

    def subscribe(
        self,
        on_next: Optional[Callable[[T], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        on_complete: Optional[Callable[[], None]] = None,
    ) -> Disposable:
        observer = Observer(on_next, on_error, on_complete)
        return self._subscribe_fn(observer)

    # ------------------------------------------------------------------ #
    #  Operators                                                            #
    # ------------------------------------------------------------------ #

    def map(self, fn: Callable[[T], U]) -> "Observable[U]":
        source = self

        def subscribe(observer: Observer[U]) -> Disposable:
            def _next(value: T) -> None:
                try:
                    observer.on_next(fn(value))
                except Exception as e:
                    observer.on_error(e)

            return source.subscribe(_next, observer.on_error, observer.on_complete)

        return Observable(subscribe)

    def filter(self, predicate: Callable[[T], bool]) -> "Observable[T]":
        source = self

        def subscribe(observer: Observer[T]) -> Disposable:
            def _next(value: T) -> None:
                try:
                    if predicate(value):
                        observer.on_next(value)
                except Exception as e:
                    observer.on_error(e)

            return source.subscribe(_next, observer.on_error, observer.on_complete)

        return Observable(subscribe)

    def take(self, count: int) -> "Observable[T]":
        source = self

        def subscribe(observer: Observer[T]) -> Disposable:
            remaining = [count]
            disposable_ref: list[Optional[Disposable]] = [None]

            def _next(value: T) -> None:
                if remaining[0] <= 0:
                    return
                remaining[0] -= 1
                observer.on_next(value)
                if remaining[0] == 0:
                    observer.on_complete()
                    if disposable_ref[0]:
                        disposable_ref[0].dispose()

            d = source.subscribe(_next, observer.on_error, observer.on_complete)
            disposable_ref[0] = d
            return d

        return Observable(subscribe)

    def skip(self, count: int) -> "Observable[T]":
        source = self

        def subscribe(observer: Observer[T]) -> Disposable:
            skipped = [0]

            def _next(value: T) -> None:
                if skipped[0] < count:
                    skipped[0] += 1
                else:
                    observer.on_next(value)

            return source.subscribe(_next, observer.on_error, observer.on_complete)

        return Observable(subscribe)

    def merge_with(self, other: "Observable[T]") -> "Observable[T]":
        source = self

        def subscribe(observer: Observer[T]) -> Disposable:
            completed = [0]
            lock = threading.Lock()

            def _complete() -> None:
                with lock:
                    completed[0] += 1
                    if completed[0] == 2:
                        observer.on_complete()

            d1 = source.subscribe(observer.on_next, observer.on_error, _complete)
            d2 = other.subscribe(observer.on_next, observer.on_error, _complete)

            def _cancel() -> None:
                d1.dispose()
                d2.dispose()

            return Disposable(_cancel)

        return Observable(subscribe)

    def zip_with(self, other: "Observable[Any]") -> "Observable[tuple]":
        source = self

        def subscribe(observer: Observer[tuple]) -> Disposable:
            q1: queue.Queue = queue.Queue()
            q2: queue.Queue = queue.Queue()
            lock = threading.Lock()

            def try_emit() -> None:
                with lock:
                    if not q1.empty() and not q2.empty():
                        observer.on_next((q1.get(), q2.get()))

            def _next1(v: Any) -> None:
                q1.put(v)
                try_emit()

            def _next2(v: Any) -> None:
                q2.put(v)
                try_emit()

            d1 = source.subscribe(_next1, observer.on_error, observer.on_complete)
            d2 = other.subscribe(_next2, observer.on_error, observer.on_complete)

            def _cancel() -> None:
                d1.dispose()
                d2.dispose()

            return Disposable(_cancel)

        return Observable(subscribe)

    def debounce(self, seconds: float) -> "Observable[T]":
        source = self

        def subscribe(observer: Observer[T]) -> Disposable:
            timer_ref: list[Optional[threading.Timer]] = [None]
            lock = threading.Lock()
            disposed = [False]

            def _next(value: T) -> None:
                with lock:
                    if timer_ref[0]:
                        timer_ref[0].cancel()

                    def emit() -> None:
                        if not disposed[0]:
                            observer.on_next(value)

                    t = threading.Timer(seconds, emit)
                    timer_ref[0] = t
                    t.start()

            def _cancel() -> None:
                disposed[0] = True
                with lock:
                    if timer_ref[0]:
                        timer_ref[0].cancel()

            d = source.subscribe(_next, observer.on_error, observer.on_complete)

            def _full_cancel() -> None:
                _cancel()
                d.dispose()

            return Disposable(_full_cancel)

        return Observable(subscribe)

    def throttle(self, seconds: float) -> "Observable[T]":
        source = self

        def subscribe(observer: Observer[T]) -> Disposable:
            last_emit = [0.0]
            lock = threading.Lock()

            def _next(value: T) -> None:
                now = time.monotonic()
                with lock:
                    if now - last_emit[0] >= seconds:
                        last_emit[0] = now
                        should_emit = True
                    else:
                        should_emit = False
                if should_emit:
                    observer.on_next(value)

            return source.subscribe(_next, observer.on_error, observer.on_complete)

        return Observable(subscribe)

    def with_backpressure(self, max_size: int = 64) -> "Observable[T]":
        """Drop oldest items when internal buffer is full."""
        source = self

        def subscribe(observer: Observer[T]) -> Disposable:
            buf: queue.Queue = queue.Queue(maxsize=max_size)
            stop_event = threading.Event()

            def _next(value: T) -> None:
                if buf.full():
                    try:
                        buf.get_nowait()  # drop oldest
                    except queue.Empty:
                        pass
                try:
                    buf.put_nowait(value)
                except queue.Full:
                    pass

            def _drain() -> None:
                while not stop_event.is_set() or not buf.empty():
                    try:
                        item = buf.get(timeout=0.05)
                        observer.on_next(item)
                    except queue.Empty:
                        continue

            drain_thread = threading.Thread(target=_drain, daemon=True)
            drain_thread.start()

            d = source.subscribe(_next, observer.on_error, observer.on_complete)

            def _cancel() -> None:
                stop_event.set()
                d.dispose()

            return Disposable(_cancel)

        return Observable(subscribe)


class ObservableSubject(Observable[T]):
    """An Observable that also acts as an Observer — multicast hub."""

    def __init__(self) -> None:
        self._observers: list[Observer[T]] = []
        self._lock = threading.Lock()
        self._completed = False
        self._error: Optional[Exception] = None

        def subscribe_fn(observer: Observer[T]) -> Disposable:
            with self._lock:
                if self._completed:
                    observer.on_complete()
                    return Disposable(lambda: None)
                if self._error is not None:
                    observer.on_error(self._error)
                    return Disposable(lambda: None)
                self._observers.append(observer)

            def _cancel() -> None:
                with self._lock:
                    try:
                        self._observers.remove(observer)
                    except ValueError:
                        pass

            return Disposable(_cancel)

        super().__init__(subscribe_fn)

    def emit(self, value: T) -> None:
        with self._lock:
            observers = list(self._observers)
        for obs in observers:
            obs.on_next(value)

    def error(self, exc: Exception) -> None:
        with self._lock:
            self._error = exc
            observers = list(self._observers)
        for obs in observers:
            obs.on_error(exc)

    def complete(self) -> None:
        with self._lock:
            self._completed = True
            observers = list(self._observers)
        for obs in observers:
            obs.on_complete()
