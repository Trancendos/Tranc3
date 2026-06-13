"""
RxPY-inspired reactive streams — stdlib only.
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Any, Callable, Generic, Iterable, List, Optional, TypeVar

T = TypeVar("T")
U = TypeVar("U")


class Disposable:
    """Cancel a subscription."""

    def __init__(self, cancel_fn: Callable[[], None]) -> None:
        self._cancel = cancel_fn
        self._disposed = False

    def dispose(self) -> None:
        if not self._disposed:
            self._disposed = True
            self._cancel()

    @property
    def is_disposed(self) -> bool:
        return self._disposed


class Observer(Generic[T]):
    def __init__(
        self,
        on_next: Optional[Callable[[T], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        on_complete: Optional[Callable[[], None]] = None,
    ) -> None:
        self._on_next = on_next or (lambda _: None)
        self._on_error = on_error or (lambda e: None)
        self._on_complete = on_complete or (lambda: None)
        self._completed = False
        self._lock = threading.Lock()

    def on_next(self, value: T) -> None:
        with self._lock:
            if self._completed:
                return
        try:
            self._on_next(value)
        except Exception as exc:
            self.on_error(exc)

    def on_error(self, error: Exception) -> None:
        with self._lock:
            if self._completed:
                return
            self._completed = True
        self._on_error(error)

    def on_complete(self) -> None:
        with self._lock:
            if self._completed:
                return
            self._completed = True
        self._on_complete()


class Observable(Generic[T]):
    """Cold observable — subscriptions run independently."""

    def __init__(
        self,
        subscribe_fn: Callable[[Observer[T]], Optional[Disposable]],
    ) -> None:
        self._subscribe_fn = subscribe_fn

    def subscribe(
        self,
        on_next: Optional[Callable[[T], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        on_complete: Optional[Callable[[], None]] = None,
        observer: Optional[Observer[T]] = None,
    ) -> Disposable:
        obs = observer or Observer(on_next, on_error, on_complete)
        result = self._subscribe_fn(obs)
        if result is None:
            return Disposable(lambda: None)
        return result

    # ------------------------------------------------------------------
    # Operators
    # ------------------------------------------------------------------

    def map(self, transform: Callable[[T], U]) -> "Observable[U]":
        source = self

        def subscribe_fn(observer: Observer[U]) -> Optional[Disposable]:
            def _next(v: T) -> None:
                try:
                    observer.on_next(transform(v))
                except Exception as exc:
                    observer.on_error(exc)

            return source.subscribe(
                on_next=_next,
                on_error=observer.on_error,
                on_complete=observer.on_complete,
            )

        return Observable(subscribe_fn)

    def filter(self, predicate: Callable[[T], bool]) -> "Observable[T]":
        source = self

        def subscribe_fn(observer: Observer[T]) -> Optional[Disposable]:
            def _next(v: T) -> None:
                try:
                    if predicate(v):
                        observer.on_next(v)
                except Exception as exc:
                    observer.on_error(exc)

            return source.subscribe(
                on_next=_next,
                on_error=observer.on_error,
                on_complete=observer.on_complete,
            )

        return Observable(subscribe_fn)

    def take(self, count: int) -> "Observable[T]":
        source = self

        def subscribe_fn(observer: Observer[T]) -> Optional[Disposable]:
            remaining = [count]
            disposable: List[Optional[Disposable]] = [None]

            def _next(v: T) -> None:
                if remaining[0] <= 0:
                    return
                remaining[0] -= 1
                observer.on_next(v)
                if remaining[0] == 0:
                    observer.on_complete()
                    if disposable[0]:
                        disposable[0].dispose()

            d = source.subscribe(
                on_next=_next,
                on_error=observer.on_error,
                on_complete=observer.on_complete,
            )
            disposable[0] = d
            return d

        return Observable(subscribe_fn)

    def skip(self, count: int) -> "Observable[T]":
        source = self

        def subscribe_fn(observer: Observer[T]) -> Optional[Disposable]:
            skipped = [0]

            def _next(v: T) -> None:
                if skipped[0] < count:
                    skipped[0] += 1
                    return
                observer.on_next(v)

            return source.subscribe(
                on_next=_next,
                on_error=observer.on_error,
                on_complete=observer.on_complete,
            )

        return Observable(subscribe_fn)

    def merge_with(self, other: "Observable[T]") -> "Observable[T]":
        source = self

        def subscribe_fn(observer: Observer[T]) -> Optional[Disposable]:
            completed = [0]
            lock = threading.Lock()

            def _complete() -> None:
                with lock:
                    completed[0] += 1
                    if completed[0] == 2:
                        observer.on_complete()

            d1 = source.subscribe(
                on_next=observer.on_next,
                on_error=observer.on_error,
                on_complete=_complete,
            )
            d2 = other.subscribe(
                on_next=observer.on_next,
                on_error=observer.on_error,
                on_complete=_complete,
            )

            def cancel() -> None:
                d1.dispose()
                d2.dispose()

            return Disposable(cancel)

        return Observable(subscribe_fn)

    def zip_with(self, other: "Observable[U]") -> "Observable[tuple]":
        source = self

        def subscribe_fn(observer: Observer[tuple]) -> Optional[Disposable]:
            q1: queue.Queue = queue.Queue()
            q2: queue.Queue = queue.Queue()
            lock = threading.Lock()

            def _try_emit() -> None:
                with lock:
                    if not q1.empty() and not q2.empty():
                        observer.on_next((q1.get_nowait(), q2.get_nowait()))

            def _next1(v: Any) -> None:
                q1.put(v)
                _try_emit()

            def _next2(v: Any) -> None:
                q2.put(v)
                _try_emit()

            d1 = source.subscribe(on_next=_next1, on_error=observer.on_error)
            d2 = other.subscribe(on_next=_next2, on_error=observer.on_error)

            def cancel() -> None:
                d1.dispose()
                d2.dispose()

            return Disposable(cancel)

        return Observable(subscribe_fn)

    def debounce(self, delay_secs: float) -> "Observable[T]":
        """Emit only after silence of `delay_secs`."""
        source = self

        def subscribe_fn(observer: Observer[T]) -> Optional[Disposable]:
            timer: List[Optional[threading.Timer]] = [None]
            lock = threading.Lock()

            def _next(v: T) -> None:
                with lock:
                    if timer[0] is not None:
                        timer[0].cancel()

                    def emit() -> None:
                        observer.on_next(v)

                    t = threading.Timer(delay_secs, emit)
                    timer[0] = t
                    t.start()

            def _cancel() -> None:
                with lock:
                    if timer[0]:
                        timer[0].cancel()

            d = source.subscribe(
                on_next=_next,
                on_error=observer.on_error,
                on_complete=observer.on_complete,
            )

            def dispose() -> None:
                _cancel()
                d.dispose()

            return Disposable(dispose)

        return Observable(subscribe_fn)

    def throttle(self, interval_secs: float) -> "Observable[T]":
        """Emit at most once per `interval_secs`."""
        source = self

        def subscribe_fn(observer: Observer[T]) -> Optional[Disposable]:
            last_emit = [0.0]
            lock = threading.Lock()

            def _next(v: T) -> None:
                now = time.monotonic()
                with lock:
                    if now - last_emit[0] >= interval_secs:
                        last_emit[0] = now
                        should_emit = True
                    else:
                        should_emit = False
                if should_emit:
                    observer.on_next(v)

            return source.subscribe(
                on_next=_next,
                on_error=observer.on_error,
                on_complete=observer.on_complete,
            )

        return Observable(subscribe_fn)

    def with_backpressure(self, buffer_size: int = 100) -> "Observable[T]":
        """Drop oldest items when buffer is full."""
        source = self

        def subscribe_fn(observer: Observer[T]) -> Optional[Disposable]:
            buf: queue.Queue = queue.Queue(maxsize=buffer_size)
            active = [True]

            def _drain() -> None:
                while active[0]:
                    try:
                        v = buf.get(timeout=0.05)
                        observer.on_next(v)
                    except queue.Empty:
                        continue

            def _next(v: T) -> None:
                if buf.full():
                    try:
                        buf.get_nowait()  # drop oldest
                    except queue.Empty:
                        pass
                buf.put_nowait(v)

            drain_thread = threading.Thread(target=_drain, daemon=True)
            drain_thread.start()

            d = source.subscribe(
                on_next=_next,
                on_error=observer.on_error,
                on_complete=observer.on_complete,
            )

            def cancel() -> None:
                active[0] = False
                d.dispose()

            return Disposable(cancel)

        return Observable(subscribe_fn)


class ObservableSubject(Observable[T]):
    """Hot observable — multicasts to all current subscribers."""

    def __init__(self) -> None:
        self._observers: List[Observer[T]] = []
        self._lock = threading.Lock()
        self._completed = False

        def subscribe_fn(observer: Observer[T]) -> Disposable:
            with self._lock:
                self._observers.append(observer)

            def cancel() -> None:
                with self._lock:
                    if observer in self._observers:
                        self._observers.remove(observer)

            return Disposable(cancel)

        super().__init__(subscribe_fn)

    def emit(self, value: T) -> None:
        with self._lock:
            observers = list(self._observers)
        for obs in observers:
            obs.on_next(value)

    def error(self, exc: Exception) -> None:
        with self._lock:
            observers = list(self._observers)
        for obs in observers:
            obs.on_error(exc)

    def complete(self) -> None:
        with self._lock:
            observers = list(self._observers)
            self._completed = True
        for obs in observers:
            obs.on_complete()


def from_iterable(iterable: Iterable[T]) -> Observable[T]:
    """Create an Observable from any iterable."""

    def subscribe_fn(observer: Observer[T]) -> None:
        try:
            for item in iterable:
                observer.on_next(item)
            observer.on_complete()
        except Exception as exc:
            observer.on_error(exc)

    return Observable(subscribe_fn)
