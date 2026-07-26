"""Choosing how an array gets fitted to the op that is about to receive it.

skop turns "this op wants `y x`" plus "this array is `z y x`" into a list of
`AdaptationPlan`s rather than a decision, precisely so that a front end can
show the choice. This is the showing: one row per adaptable image input, with
the resolved axes on the left and what will be done with them on the right.

The rule the ordering encodes is that skop's `choose` also encodes -- lossless
plans come first, so the default selection never silently throws data away,
while the plan that does is one visible click away rather than forbidden.
"""

from __future__ import annotations

from typing import Any

from magicgui.widgets import ComboBox, Container, Label, LineEdit
from psygnal import Signal

import skop
from skop import AdaptationPlan, OpSpec, ParamSpec

from . import _axes


class _Row(Container):
    """Axis labels and adaptation choice for one image parameter."""

    #: Emitted when the axis labels are edited by hand. Deliberately not
    #: Container.changed, which also fires when the plan combo is used --
    #: choosing a plan must not trigger the re-planning that rebuilds it.
    edited = Signal()

    def __init__(self, param: ParamSpec) -> None:
        self.param = param
        self._override: tuple[str, ...] | None = None
        self._seen: int | None = None
        self._updating = False

        self._axes = LineEdit(
            name=f"{param.name}_axes",
            label=f"{param.name} axes",
            tooltip=(
                "What this array's axes are, outermost first. Any name works: "
                "'z y x', 'lifetime y x', 'pln row col'. Edit this if the "
                "guess is wrong -- it is remembered on the layer."
            ),
        )
        self._plan = ComboBox(
            name=f"{param.name}_adapt",
            label=f"{param.name} adapt",
            tooltip=f"How to fit this array to what {param.name} accepts.",
        )
        self._status = Label(value="")

        super().__init__(
            widgets=[self._axes, self._plan, self._status], labels=True, visible=False
        )
        self._axes.changed.connect(self._edited)

    # -- state ------------------------------------------------------------

    @property
    def plan(self) -> AdaptationPlan | None:
        return self._plan.value if self._plan.choices else None

    @property
    def problem(self) -> str | None:
        """Why this input cannot be adapted, if it cannot."""
        return self._problem

    _problem: str | None = None

    def _edited(self) -> None:
        if self._updating:
            return
        # Typed by hand, so it outranks anything resolution comes up with --
        # until the input layer changes underneath it.
        self._override = _axes.parse(self._axes.value) or None
        self.edited.emit()

    # -- refreshing -------------------------------------------------------

    def refresh(self, fn: Any, data: Any, viewer: Any) -> None:
        """Re-resolve axes and re-plan, for whatever is selected now."""
        if data is None or not hasattr(data, "shape"):
            self.visible = False
            self._problem = None
            return

        if id(data) != self._seen:
            # A different layer: an override typed for the old one says
            # nothing about this one.
            self._seen = id(data)
            self._override = None

        layer = _axes.layer_for(viewer, data)
        if self._override is not None:
            axes, note = self._override, "as you typed"
        else:
            guess = _axes.resolve(data, layer, viewer)
            axes, note = guess.axes, f"from {guess.source}"
            if not guess.declared:
                note += " -- check this"

        self._show(axes)
        _axes.remember(layer, axes)
        self._replan(fn, data, axes, viewer, note)
        self.visible = True

    def _show(self, axes: tuple[str, ...]) -> None:
        self._updating = True
        try:
            self._axes.value = " ".join(axes)
        finally:
            self._updating = False

    def _replan(
        self,
        fn: Any,
        data: Any,
        axes: tuple[str, ...],
        viewer: Any,
        note: str,
    ) -> None:
        try:
            candidates = skop.plans(
                fn,
                self.param.name,
                data,
                axes,
                position=_axes.positions(axes, viewer),
            )
        except ValueError as exc:
            # An array that cannot satisfy the op at all: too few axis labels,
            # or missing one the op requires. The user's move is to fix the
            # labels, so say so here rather than failing at run time.
            self._problem = f"{self.param.name}: {exc}"
            self._plan.choices = ()
            self._status.value = str(exc)
            return

        self._problem = None
        self._status.value = note
        wanted = self._plan.value.summary if self._plan.choices else None
        self._updating = True
        try:
            self._plan.choices = [(plan.summary, plan) for plan in candidates]
            for plan in candidates:
                if plan.summary == wanted:
                    self._plan.value = plan
                    break
        finally:
            self._updating = False


class Adaptations(Container):
    """The adaptation rows for whichever op is currently selected."""

    def __init__(self) -> None:
        super().__init__(labels=False, visible=False)
        self._rows: list[_Row] = []

    def rebuild(self, spec: OpSpec) -> list[str]:
        """Start over for a newly chosen op.

        Returns the names of the parameters that got a row, so the panel can
        watch those widgets for changes.
        """
        self.clear()
        # Only a parameter whose op declared Axes can be adapted; everything
        # else is passed through exactly as it always was.
        self._rows = [_Row(p) for p in spec.inputs if p.axes is not None]
        self.extend(self._rows)
        self.visible = bool(self._rows)
        return [row.param.name for row in self._rows]

    def refresh(self, fn: Any, values: dict[str, Any], viewer: Any) -> None:
        for row in self._rows:
            row.refresh(fn, values.get(row.param.name), viewer)
        self.visible = any(row.visible for row in self._rows)

    @property
    def plans(self) -> dict[str, AdaptationPlan]:
        """The chosen plan per parameter, for ``Runner.run(plans=...)``."""
        return {row.param.name: row.plan for row in self._rows if row.plan is not None}

    @property
    def problems(self) -> list[str]:
        return [row.problem for row in self._rows if row.problem]

    @property
    def output_axes(self) -> tuple[str, ...]:
        """Axes to stamp onto the results, from whichever plan produced them.

        Derived rather than declared, and only trustworthy when exactly one
        input was adapted -- which is every op in the collection today, and
        the same limit skop's own iteration imposes.
        """
        chosen = list(self.plans.values())
        return chosen[0].output_axes if len(chosen) == 1 else ()

    def watch(self, callback: Any) -> None:
        for row in self._rows:
            row.edited.connect(callback)
