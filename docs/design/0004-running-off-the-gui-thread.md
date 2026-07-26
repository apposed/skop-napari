# 0004 — Running an op off the GUI thread

## The constraints

- `Runner.run()` blocks until the op finishes. It may block for **minutes** if
  the environment has to be built first.
- Progress events arrive from the worker *process*, relayed by an Appose
  listener *thread*. Neither is the GUI thread.
- Qt widgets may only be touched from the GUI thread.
- The user must be able to cancel, including during the silent early part of a
  run when nothing has reported progress yet.
- The user may close the panel while an op is still running.

`_run.py` exists to satisfy all five at once.

## The shape

`OpRun` wraps one execution: a superqt worker running `runner.run()`, with
every callback marshalled back to the GUI thread by `ensure_main_thread`.

```python
self.worker = create_worker(
    work,
    _start_thread=False,
    _connect={"returned": on_done, "errored": on_error, "finished": finished},
)
```

## Three non-obvious pieces

**`_start_thread=False`, and callbacks via `_connect`.** `create_worker` starts
the thread immediately unless told not to, so connecting handlers on the line
after is a race — a fast op can finish before its `returned` handler is
attached. Worse, superqt re-raises worker errors into the Qt event loop unless
an `errored` handler was supplied *through `_connect`*; connecting one
afterwards does not suppress it. This was a genuine bug, not a stylistic
preference: op failures were being raised as unhandled exceptions in the event
loop instead of reaching `_on_error`.

**`on_start` for cancellation.** `Runner.run()` takes an `on_start` callback
invoked with the Appose `Task` the moment it is submitted, and `OpRun` stashes
it. Since `run()` blocks, this is the only way the GUI thread can obtain the
handle it needs to cancel. The alternative — grab the task from the first
progress event — leaves an op that reports no progress permanently
uncancellable, and "silent" and "hung" look identical to a user.

**A `_live` flag, checked at delivery time.** If the panel is closed mid-run,
the op keeps going in its own process and its progress events keep arriving at
Qt objects that have been destroyed:

```
RuntimeError: wrapped C/C++ object of type QProgressBar has been deleted
```

`OpRun.detach()` clears `_live`, and the relay checks it before forwarding. The
check is at *delivery*, not at subscription, because the event is already in
flight by then. `_show_progress` additionally catches `RuntimeError` and calls
`detach()` — belt and braces, since the flag can only be set once someone has
noticed the widget is gone, and the first notification is usually that
exception.

## Cancellation semantics

`Task.cancel()` is cooperative: it sets a flag the op observes via
`skop.cancel_requested()`. An op that never checks runs to completion. An op
that does may return partial results, and those are displayed — `toy.slow_sum`
returns its partial sum, and the test asserts the total lands strictly between
0 and what a full run would produce.

The panel disables Cancel and relabels it *"Canceling…"* rather than tearing
down immediately, because there is nothing to tear down: the op decides when it
stops.

## `finished` is emitted however the run ended

Completed, failed, or canceled. This is what anything driving the panel from
outside — the tests, principally — waits on. A signal that fired only on
success would make every failure test a timeout.

## Testing notes

- `qtbot.waitSignal(panel.finished, ...)` around `panel._start()`. An assertion
  that fails *inside* a `waitSignal` block hangs the suite rather than failing
  it, which cost a 600-second timeout before the cause was clear.
- `QT_QPA_PLATFORM=offscreen` **segfaults**: vispy's `get_max_texture_sizes`
  needs a real GL context. CI needs xvfb, not the offscreen plugin.
- Do not assert on `widget.visible`. magicgui reports actual Qt state and the
  test viewer is never shown, so it is always `False`. Assert on contents.
