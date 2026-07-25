"""Turning an OpSpec into magicgui input widgets.

Nothing here imports napari. The one napari-shaped thing a caller must supply
is ``annotation_for``, which says what type each parameter should be rendered
as; ``_roles.annotation_for`` is the napari answer, and a different front end
would pass a different one. If skop ever grows a second magicgui host, this
module is what moves.

Widgets are built one parameter at a time rather than by handing magicgui a
whole synthesized function, because ops in the wild contain parameters
magicgui cannot render -- ``tuple[int, ...]`` among them -- and one of those
must not take the entire panel down with it.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from magicgui.types import Undefined
from magicgui.widgets import Widget, create_widget

from skop import OpSpec, ParamSpec


@dataclass
class Inputs:
    """The renderable inputs of an op, and what had to be left out."""

    widgets: list[Widget] = field(default_factory=list)
    #: Parameters magicgui could not render, which have a default to fall
    #: back on. The op still runs; these simply are not adjustable.
    defaulted: list[tuple[str, str]] = field(default_factory=list)
    #: Parameters magicgui could not render and which have no default. The
    #: op cannot be run from a GUI at all.
    blocking: list[tuple[str, str]] = field(default_factory=list)

    @property
    def runnable(self) -> bool:
        return not self.blocking

    def values(self) -> dict[str, Any]:
        """The arguments to call the op with, as currently filled in."""
        return {w.name: w.value for w in self.widgets}


def build_inputs(spec: OpSpec, annotation_for: Callable[[ParamSpec], Any]) -> Inputs:
    """Build one widget per input parameter of *spec*.

    ``Out`` parameters are skipped: they are buffers the caller allocates, and
    a user is never asked for one.
    """
    docs = param_docs(spec.doc)
    inputs = Inputs()

    for param in spec.inputs:
        options = dict(param.ui)
        widget_type = options.pop("widget_type", None)
        if "tooltip" not in options and param.name in docs:
            options["tooltip"] = docs[param.name]

        try:
            widget = create_widget(
                # NB: Undefined, not None. Passing None marks the widget
                # nullable, which puts an empty entry in every layer combo.
                value=Undefined if param.required else param.default,
                annotation=annotation_for(param),
                name=param.name,
                label=param.name.replace("_", " "),
                widget_type=widget_type,
                options=options,
            )
        except Exception as exc:  # noqa: BLE001 - any failure is the same failure.
            reason = f"{type(exc).__name__}: {exc}"
            if param.required:
                inputs.blocking.append((param.name, reason))
            else:
                inputs.defaulted.append((param.name, reason))
            continue

        inputs.widgets.append(widget)

    return inputs


_ARGS_HEADING = re.compile(r"^\s*(Args|Arguments|Parameters)\s*:\s*$")
_SECTION_HEADING = re.compile(r"^\s*[A-Z][A-Za-z ]*\s*:\s*$")
_ARG_LINE = re.compile(r"^\s*(\*{0,2}\w+)\s*(\([^)]*\))?\s*:\s*(.*)$")


def param_docs(doc: str | None) -> dict[str, str]:
    """Pull per-parameter descriptions out of a Google-style docstring.

    magicgui does this itself when it builds from a function, but we build
    from an OpSpec, so the tooltips have to be recovered here. A docstring
    that does not follow the convention simply yields no tooltips.
    """
    if not doc:
        return {}

    lines = doc.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if _ARGS_HEADING.match(line))
    except StopIteration:
        return {}

    found: dict[str, str] = {}
    current: str | None = None
    for line in lines[start + 1 :]:
        if not line.strip():
            continue
        if _SECTION_HEADING.match(line):
            break
        match = _ARG_LINE.match(line)
        if match:
            current = match.group(1)
            found[current] = match.group(3).strip()
        elif current:
            # A continuation of the previous parameter's description.
            found[current] = f"{found[current]} {line.strip()}".strip()

    return found
