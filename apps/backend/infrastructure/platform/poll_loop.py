"""The one shape every background worker's thread takes.

Each of these workers does something different and none of them needs a
bespoke thread: run a pass, sleep the poll interval, repeat until asked to
stop, never let a raising pass end the thread. What varied between them was
spelling — two event-object names, three join timeouts, ``_stop.wait()``
before or after the first pass, a log line each — which is the kind of
variation that hides a real difference (a pass that can kill the loop)
inside seven copies of boilerplate.

``PollLoop`` owns the thread, the stop event, the wait, and the log lines.
A worker supplies one callable and the name it wants in ``threading`` and in
its log prefix, and says what differs about it: the thread's own event loop,
a first pass that must not wait (RUN_ON_STARTUP), a pass-count that decides
whether the thread stays alive at all.

The loop is a daemon thread and stop is a cooperative event: a pass in
flight is finished, then the loop exits. Nothing here waits on work that
ignores the stop signal — a pass that runs a whole batch of long runs
delays the join, exactly as it did before this class existed.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)


class PollLoop:
    """Run ``iteration`` on a daemon thread until :meth:`stop` is called.

    A pass that raises is logged with ``failure_log`` and the loop keeps
    going; that is the whole point of the wrapper — a worker must outlive a
    bad database round-trip. Passes never overlap.

    ``startup`` runs on the worker thread before the first pass and
    ``shutdown`` after the last one — in ``finally``, so it also runs when
    ``startup`` declined or raised and a loop never got to poll. Returning
    False from ``startup`` ends the thread without a single pass.

    ``poll_sec`` stays readable and writable: it is read again at every wait,
    so a worker whose interval comes from settings — or a test watching one
    pass instead of ninety seconds — can retune a running loop.
    """

    def __init__(
        self,
        *,
        name: str,
        iteration: Callable[[], None],
        poll_sec: float,
        join_sec: float = 20.0,
        startup: Callable[[], bool] | None = None,
        shutdown: Callable[[], None] | None = None,
        run_first_pass_immediately: bool = False,
        failure_log: str | None = None,
    ) -> None:
        self.name = name
        self.poll_sec = float(poll_sec)
        self._iteration = iteration
        self._join_sec = join_sec
        self._startup = startup
        self._shutdown = shutdown
        self._run_first_pass_immediately = run_first_pass_immediately
        self._failure_log = failure_log or f"{name} pass failed"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the thread. Starting a live loop is a no-op, not a second thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name=self.name)
        self._thread.start()

    def stop(self) -> None:
        """Ask the loop to finish and wait up to ``join_sec`` for it."""
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=self._join_sec)

    def stopping(self) -> bool:
        """True once stop was asked — for a batch pass that wants to abandon its rows."""
        return self._stop.is_set()

    def _run(self) -> None:
        try:
            if self._startup is not None and not self._startup():
                return
            logger.info("%s started", self.name)
            first = True
            while not self._stop.is_set():
                if first and self._run_first_pass_immediately:
                    first = False
                elif self._stop.wait(timeout=self.poll_sec):
                    break
                try:
                    self._iteration()
                except Exception:
                    logger.exception(self._failure_log)
        finally:
            if self._shutdown is not None:
                self._shutdown()
        logger.info("%s stopped", self.name)
