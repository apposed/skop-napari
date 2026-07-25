"""The Ops panel: pick an op, fill in its inputs, run it.

One widget for the whole collection, rather than one contribution per op.
npe2 wants a static manifest, and skop discovers its ops by importing them,
so a per-op contribution would mean generating the manifest at build time and
losing the ability to drop a new op into the collection and see it appear.
The napari team is working on dynamic registration; when it lands, this file
is what gets split up.
"""

from __future__ import annotations

from typing import Any

from magicgui.widgets import (
    ComboBox,
    Container,
    Label,
    LineEdit,
    ProgressBar,
    PushButton,
)
from napari.layers import Layer
from psygnal import Signal

from skop import OpSpec, Runner, discover

from ._roles import annotation_for, layer_type_for
from ._run import OpRun, outputs_of
from ._widget import Inputs, build_inputs

# Output names too generic to serve as layer names on their own.
_GENERIC = frozenset(
    {"out", "output", "result", "image", "labels", "points", "mask", "nuclei", "cells"}
)


def _label_for(spec: OpSpec) -> str:
    """A human-facing name for an op, e.g. 'segment: stardist2d'."""
    namespace = spec.module.removeprefix("skop.ops.").split(".")[0]
    return (
        spec.function if namespace == spec.function else f"{namespace}: {spec.function}"
    )


def _layer_name(spec: OpSpec, output: str) -> str:
    if output.lower() in _GENERIC:
        return f"{output} [{spec.function}]"
    return output


class OpsPanel(Container):
    """Runs any op in the collection, against the layers in the viewer."""

    #: Emitted when a run ends, however it ended -- completed, failed or
    #: canceled. Ops finish on a worker thread, so this is how anything
    #: driving the panel from outside knows the outputs have landed.
    finished = Signal()

    def __init__(self, viewer: Any = None, runner: Runner | None = None) -> None:
        self._viewer = viewer
        # One Runner for the session: workers stay warm between invocations,
        # which is most of why running an op a second time is fast.
        self._runner = runner if runner is not None else Runner()
        self._run: OpRun | None = None

        self._specs, self._failures = discover()
        self._by_label = {_label_for(s): s for s in self._specs}

        self._picker = ComboBox(
            name="op",
            label="op",
            choices=sorted(self._by_label),
            tooltip="Which op to run.",
        )
        self._doc = Label(value="")
        self._inputs_box = Container(labels=True)
        self._notes = Label(value="")
        self._button = PushButton(text="Run")
        self._cancel = PushButton(text="Cancel", visible=False)
        self._progress = ProgressBar(visible=False, min=0, max=0)
        self._results = Container(labels=True, visible=False)

        super().__init__(
            widgets=[
                self._picker,
                self._doc,
                self._inputs_box,
                self._notes,
                self._button,
                self._cancel,
                self._progress,
                self._results,
            ],
            labels=False,
        )

        self._picker.changed.connect(self._select)
        self._button.changed.connect(self._start)
        self._cancel.changed.connect(self._stop)

        if self._by_label:
            self._select()
        else:
            self._doc.value = "No ops found."
            self._button.enabled = False

    # -- op selection ----------------------------------------------------

    @property
    def spec(self) -> OpSpec:
        return self._by_label[self._picker.value]

    def _select(self) -> None:
        """Rebuild the input widgets for the newly chosen op."""
        spec = self.spec
        summary = (spec.doc or "").strip().splitlines()
        self._doc.value = summary[0] if summary else ""

        self._inputs: Inputs = build_inputs(spec, annotation_for)
        self._inputs_box.clear()
        self._inputs_box.extend(self._inputs.widgets)

        self._notes.value = self._notes_for(self._inputs, spec)
        self._button.enabled = self._inputs.runnable
        self._results.clear()
        self._results.visible = False

    def _notes_for(self, inputs: Inputs, spec: OpSpec) -> str:
        notes = [f"Environment: {spec.env}"]
        if inputs.defaulted:
            names = ", ".join(name for name, _ in inputs.defaulted)
            notes.append(f"Not editable here, using defaults: {names}")
        if inputs.blocking:
            names = ", ".join(name for name, _ in inputs.blocking)
            notes.append(f"Cannot run: no widget for required input(s) {names}")
        return "\n".join(notes)

    # -- running ---------------------------------------------------------

    def _start(self) -> None:
        if self._run is not None:
            return

        spec = self.spec
        self._results.clear()
        self._results.visible = False
        self._button.enabled = False
        self._cancel.visible = True
        self._progress.visible = True
        self._progress.max = 0  # Indeterminate until the op says otherwise.

        self._run = OpRun(
            self._runner,
            spec,
            self._inputs.values(),
            on_progress=self._on_progress,
            on_done=self._on_done,
            on_error=self._on_error,
            on_finish=self._on_finish,
        )
        self._run.start()

    def _stop(self) -> None:
        if self._run is not None:
            self._cancel.enabled = False
            self._cancel.text = "Canceling..."
            self._run.cancel()

    def _on_progress(
        self, message: str | None, current: int | None, maximum: int | None
    ) -> None:
        try:
            if maximum:
                self._progress.max = maximum
                self._progress.value = current or 0
            if message:
                self._progress.label = message
        except RuntimeError:
            # The panel was closed while its op was still running, so the Qt
            # objects behind these widgets are gone. The op carries on in its
            # own process; there is simply nowhere left to report it.
            if self._run is not None:
                self._run.detach()

    def _on_done(self, result: Any) -> None:
        spec = self.spec
        values = outputs_of(spec, result)
        scalars: list[tuple[str, Any]] = []

        for output in spec.output_specs:
            value = values.get(output.name)
            if value is None:
                continue
            layer_type = layer_type_for(output)
            if layer_type is None:
                scalars.append((output.name, value))
            elif self._viewer is not None:
                self._viewer.add_layer(
                    Layer.create(
                        value, {"name": _layer_name(spec, output.name)}, layer_type
                    )
                )

        self._show_scalars(scalars)

    def _show_scalars(self, scalars: list[tuple[str, Any]]) -> None:
        """Display outputs that are not layers -- counts, measurements."""
        self._results.clear()
        for name, value in scalars:
            field = LineEdit(name=name, label=name, value=str(value))
            field.enabled = False
            self._results.append(field)
        self._results.visible = bool(scalars)

    def _on_error(self, exc: Exception) -> None:
        self._results.clear()
        field = LineEdit(
            name="error", label="error", value=f"{type(exc).__name__}: {exc}"
        )
        field.enabled = False
        self._results.append(field)
        self._results.visible = True

    def _on_finish(self) -> None:
        self._run = None
        self._button.enabled = self._inputs.runnable
        self._cancel.visible = False
        self._cancel.enabled = True
        self._cancel.text = "Cancel"
        self._progress.visible = False
        self._progress.label = ""
        self.finished.emit()
