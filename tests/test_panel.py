"""The Ops panel, against a real napari viewer.

These tests run ops for real, in their own Appose environments, so they need
the 'minimal' environment built. That is the cheapest one skop has -- python
plus numpy plus appose -- and building it once makes the difference between
testing the plumbing and testing a mock of it.
"""

from __future__ import annotations

import contextlib

import numpy as np
import pytest

from skop_napari import OpsPanel


@contextlib.contextmanager
def errors_raised():
    """Collect the error notifications raised inside the block.

    NB: notification_manager.records accumulates across the whole session,
    so a test that asserts on its length has to slice off what was already
    there or it will see the previous test's errors.
    """
    from napari.utils.notifications import notification_manager

    collected: list = []
    with notification_manager:
        already = len(notification_manager.records)
        yield collected
        collected.extend(
            n for n in notification_manager.records[already:] if n.severity == "error"
        )


@pytest.fixture
def panel(make_napari_viewer, qtbot):
    viewer = make_napari_viewer()
    widget = OpsPanel(viewer)
    viewer.window.add_dock_widget(widget)
    yield widget
    # Each panel holds its own Runner, and so its own worker processes.
    widget._runner.close()


def _choose(panel, function_name):
    label = next(
        lbl for lbl, spec in panel._by_label.items() if spec.function == function_name
    )
    panel._picker.value = label


def test_napari_supplies_the_viewer_when_it_builds_the_widget(make_napari_viewer):
    # Regression: the panel used to take `viewer: Any = None`, which napari
    # does not recognise, so it was built with no viewer and every layer
    # output was silently discarded. Built here through napari's own logic
    # rather than by calling OpsPanel directly, which is what hid the bug.
    from napari._qt.qt_main_window import _instantiate_dock_widget

    viewer = make_napari_viewer()
    widget = _instantiate_dock_widget(OpsPanel, viewer)
    try:
        assert widget._viewer is not None
    finally:
        widget._runner.close()


def test_layer_outputs_with_no_viewer_are_reported_not_dropped(qtbot):
    # A panel with no viewer must not look like a panel whose op did nothing.
    widget = OpsPanel()
    try:
        _choose(widget, "find_nothing")
        with errors_raised() as errors:
            widget._on_done((np.zeros((4, 4), np.uint16), np.zeros((0, 3), np.int32)))
    finally:
        widget._runner.close()

    assert len(errors) == 1
    assert "labels" in str(errors[0].message)
    assert "napari_viewer" in str(errors[0].message)


def test_lists_the_collection(panel):
    functions = {spec.function for spec in panel._by_label.values()}
    assert {"otsu", "stardist2d", "unseg", "add"} <= functions


def test_choosing_an_op_rebuilds_the_inputs(panel):
    _choose(panel, "otsu")
    assert [w.name for w in panel._inputs.widgets] == [
        "image",
        "invert",
        "label_objects",
    ]

    _choose(panel, "add")
    assert [w.name for w in panel._inputs.widgets] == ["a", "b"]
    assert "Environment: minimal" in panel._notes.value


def test_image_inputs_offer_the_viewers_layers(panel, make_napari_viewer):
    viewer = panel._viewer
    viewer.add_image(np.zeros((16, 16), dtype=np.uint8), name="first")
    viewer.add_image(np.ones((16, 16), dtype=np.uint8), name="second")

    _choose(panel, "otsu")
    image = next(w for w in panel._inputs.widgets if w.name == "image")
    # The role annotation is what turned this into a layer combo box. It
    # offers the layers' data, not the layers, which is what the op wants.
    assert len(image.choices) == 2
    assert [float(choice.mean()) for choice in image.choices] == [0.0, 1.0]


def test_a_layer_added_later_shows_up_in_the_combo(panel):
    _choose(panel, "otsu")
    image = next(w for w in panel._inputs.widgets if w.name == "image")
    assert image.choices == ()

    # napari refreshes the choices of the widgets it docks, so an op panel
    # built before the user opened an image still offers it.
    panel._viewer.add_image(np.zeros((4, 4), dtype=np.uint8), name="later")
    assert len(image.choices) == 1


def test_running_an_op_adds_its_output_as_the_right_layer_type(panel, qtbot):
    viewer = panel._viewer
    viewer.add_image(np.zeros((8, 8), dtype=np.uint16), name="blank")
    _choose(panel, "find_nothing")
    # The sole image layer is already selected: a combo built with choices
    # present picks the first one, which is what a user would have to do.
    image = next(w for w in panel._inputs.widgets if w.name == "image")
    assert image.value is viewer.layers["blank"].data

    with qtbot.waitSignal(panel.finished, timeout=300_000):
        panel._start()

    kinds = {layer.name: type(layer).__name__ for layer in viewer.layers}
    # labels -> Labels and points -> Points, from the op's role annotations.
    assert kinds["labels [find_nothing]"] == "Labels"
    assert kinds["points [find_nothing]"] == "Points"


def test_scalar_outputs_go_to_the_results_panel(panel, qtbot):
    _choose(panel, "add")
    next(w for w in panel._inputs.widgets if w.name == "a").value = 17
    next(w for w in panel._inputs.widgets if w.name == "b").value = 25

    with qtbot.waitSignal(panel.finished, timeout=300_000):
        panel._start()

    # NB: assert on contents, not on .visible -- a magicgui widget reports
    # the Qt state, and the test viewer is never actually shown.
    assert [(w.name, w.value) for w in panel._results] == [("result", "42")]
    # A scalar has no layer to be, so nothing was added to the viewer.
    assert len(panel._viewer.layers) == 0


def test_progress_reaches_the_panel_and_cancel_stops_the_op(panel, qtbot):
    panel._viewer.add_image(np.ones((10, 10), dtype=np.float32), name="ones")
    _choose(panel, "slow_sum")
    next(w for w in panel._inputs.widgets if w.name == "steps").value = 60

    with qtbot.waitSignal(panel.finished, timeout=300_000):
        panel._start()
        # Progress is reported from the worker process, relayed by an Appose
        # listener thread, and must arrive on the GUI thread to be shown.
        qtbot.waitUntil(
            lambda: "Summing chunk" in (panel._progress.label or ""),
            timeout=120_000,
        )
        assert panel._run is not None
        panel._stop()

    # slow_sum polls cancel_requested() and returns its partial sum, so a
    # canceled op still delivers -- 100.0 is what a full run would total.
    total = float(panel._results[0].value)
    assert 0.0 < total < 100.0


def test_a_failing_op_reports_through_napari(panel, qtbot):
    # No image layer exists, so scale gets None and fails in the worker.
    _choose(panel, "scale")
    assert next(w for w in panel._inputs.widgets if w.name == "image").value is None

    with (
        errors_raised() as errors,
        qtbot.waitSignal(panel.finished, timeout=300_000),
    ):
        panel._start()

    assert len(errors) == 1
    # The op failed in another process, and the notification carries that
    # process's traceback -- which is the whole reason not to use a LineEdit.
    message = str(errors[0].message)
    assert "Task failed" in message
    assert "toy.py" in message and "image * factor" in message
    assert "unsupported operand type(s)" in message

    # Nothing was written into the panel, and it is usable again.
    assert len(panel._results) == 0
    assert panel._button.enabled


def test_build_progress_drives_the_progress_bar(panel):
    # PixiInstallMonitor reports determinate progress per phase. These are
    # the real titles it emits, in order.
    panel._on_build_progress("Installing conda packages", 0, 30)
    assert panel._progress.label == "Installing conda packages"
    assert panel._progress.max == 30

    panel._on_build_progress("Installing conda packages", 21, 30)
    assert panel._progress.value == 21


def test_build_log_noise_is_logged_but_not_shown(panel, caplog):
    # Appose runs pixi under -vv to drive the monitor, so most of the stderr
    # stream is pixi's debug log rather than status worth showing.
    with caplog.at_level("INFO", logger="skop_napari"):
        panel._on_build_text(
            "DEBUG pixi_config: Loading config from /etc/pixi/config.toml\n"
            " INFO pixi_core::lock_file::update: Installed environment\n"
        )
    assert panel._progress.label == ""
    assert "pixi_config" in caplog.text  # Still recoverable from the log.

    # A human-facing line does reach the bar.
    panel._on_build_text("✔ The default environment has been installed.\n")
    assert panel._progress.label == "✔ The default environment has been installed."


def test_build_callbacks_are_registered_on_the_runner(panel):
    assert panel._runner._build_progress
    assert panel._runner._build_output
    assert panel._runner._build_error


def test_build_text_crosses_from_the_build_thread_to_the_gui(panel, qtbot):
    import threading

    # Environments are built inside run(), on the worker thread, so every
    # build callback arrives off the GUI thread and has to be marshalled.
    subscriber = panel._runner._build_error[0]
    threading.Thread(target=subscriber, args=("✔ installed\n",)).start()

    qtbot.waitUntil(lambda: panel._progress.label == "✔ installed", timeout=10_000)


# -- axis awareness --------------------------------------------------------


def _row(panel, param="image"):
    return next(r for r in panel._adapt._rows if r.param.name == param)


def test_only_ops_that_declared_axes_get_an_adaptation_row(panel):
    _choose(panel, "add")
    assert panel._adapt._rows == []
    _choose(panel, "quadrants")
    assert [r.param.name for r in panel._adapt._rows] == ["image"]


def test_a_stack_offers_iteration_first_and_slicing_second(panel):
    panel._viewer.add_image(np.zeros((3, 8, 6), dtype=np.float32), name="stack")
    _choose(panel, "quadrants")

    row = _row(panel)
    # The axes were resolved from the viewer's layout, and written back so
    # the next run reads them off the layer instead of guessing again.
    assert row._axes.value == "z y x"
    assert panel._viewer.layers["stack"].metadata["skop_axes"] == ("z", "y", "x")

    summaries = [plan.summary for plan in row._plan.choices]
    assert "run 3 times" in summaries[0]
    assert "discarding" in summaries[1]
    # Lossless first, and selected: the default never throws data away.
    assert row.plan.lossless
    assert row.plan.iterate == ("z",)


def test_the_slice_plan_follows_the_viewers_slider(panel):
    panel._viewer.add_image(np.zeros((5, 8, 6), dtype=np.float32), name="stack")
    _choose(panel, "quadrants")
    panel._viewer.dims.set_current_step(0, 3)
    panel._replan()

    lossy = next(p for p in _row(panel)._plan.choices if not p.lossless)
    assert lossy.select == (("z", 3),)
    assert "z=3" in lossy.summary


def test_editing_the_axes_replans(panel):
    panel._viewer.add_image(np.zeros((3, 8, 6), dtype=np.float32), name="stack")
    _choose(panel, "quadrants")
    row = _row(panel)

    # A lifetime axis is not z, and skop has never heard of it -- which is
    # fine, because an op that iterates does not need to know what it is.
    row._axes.value = "lifetime y x"
    assert row.plan.iterate == ("lifetime",)
    assert row.plan.calls == 3


def test_an_input_the_op_cannot_use_blocks_the_run_with_a_reason(panel):
    panel._viewer.add_image(np.zeros((3, 8), dtype=np.float32), name="odd")
    _choose(panel, "quadrants")
    _row(panel)._axes.value = "z x"

    assert not panel._button.enabled
    assert "no y axis" in panel._notes.value


def test_a_2d_op_runs_over_a_stack_and_labels_the_result(panel, qtbot):
    viewer = panel._viewer
    viewer.add_image(np.zeros((3, 8, 6), dtype=np.float32), name="stack")
    _choose(panel, "quadrants")

    with qtbot.waitSignal(panel.finished, timeout=300_000):
        panel._start()

    result = viewer.layers["result [quadrants]"]
    assert type(result).__name__ == "Labels"
    # One call per plane, stacked back up, with label IDs made unique.
    assert result.data.shape == (3, 8, 6)
    assert result.data.max() == 12
    # Stamped, so the next op run against this layer does not guess.
    assert result.metadata["skop_axes"] == ("z", "y", "x")
    assert tuple(result.axis_labels) == ("z", "y", "x")


def test_choosing_the_slice_plan_runs_once(panel, qtbot):
    viewer = panel._viewer
    viewer.add_image(np.zeros((3, 8, 6), dtype=np.float32), name="stack")
    _choose(panel, "quadrants")
    row = _row(panel)
    row._plan.value = next(p for p in row._plan.choices if not p.lossless)

    with qtbot.waitSignal(panel.finished, timeout=300_000):
        panel._start()

    assert viewer.layers["result [quadrants]"].data.shape == (8, 6)
