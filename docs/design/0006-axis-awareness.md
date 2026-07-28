# 0006 — Axis awareness

> **Superseded in part by [0007](0007-axis-mapping-ui.md) and
> [0008](0008-naming-less-and-looking-more.md).** The "choice is a combo box"
> section below described picking from `skop.plans()`, which no longer exists:
> skop now returns one editable plan, and the panel shows a mapping per slot
> plus a disposition per leftover axis (0007). And rung four is gone: nothing
> invents axis names any more, and the viewer's layout it read has become a
> mapping rather than a naming (0008) — which is that rule's argument taken to
> its conclusion, since the safest name to invent turned out to be none. The
> first three rungs and the write-back stand.

## The problem

`stardist2d` is 2-D. A napari user with a `(z, y, x)` stack selected the layer,
pressed Run, and got a traceback out of TensorFlow. What they wanted was
obvious to everyone except the software: run it on the slice they are looking
at, or run it on all of them.

skop now has the machinery for that — an op declares `Axes`, and
`skop.plans()` turns "this op wants `y x`" plus "this array is `z y x`" into
the ways of bridging the two ([skop design
0005](https://github.com/apposed/scikit-ops/blob/main/docs/design/0005-dimensional-adaptation.md)).
But skop deliberately refuses to work out what an array's axes *are*, because
guessing needs a viewer to guess for. This panel has one. So the guessing, and
the offering of the choice, is this repo's job.

## Resolution: four rungs, best evidence first

`_axes.resolve()` returns an `AxisGuess` carrying the answer, where it came
from, and whether anyone actually declared it:

1. **`layer.metadata["skop_axes"]`** — someone answered this before, possibly
   by typing over a previous answer.
2. **The array's own dims** — an `xarray.DataArray`, or OME-NGFF `multiscales`
   axes sitting in the layer metadata.
3. **napari's layer state** — `axis_labels`, and `rgb`, which is the one piece
   of layer state that is decisive rather than suggestive.
4. **Convention** — shape, plus the viewer's layout.

An answer that does not match the array's dimensionality is discarded rather
than trusted, so stale labels left on a layer by an earlier, differently-shaped
result cannot be applied to this one.

**Every resolution is written back** onto the layer, and every output layer is
stamped with `axis_labels` and `skop_axes` from the plan that produced it. This
is the part that compounds: guessing happens once per layer instead of once per
run, a correction stays corrected, and a chain of ops gets *more* certain as it
goes rather than re-deriving the same guess from scratch. It also relabels the
napari slider from `-3` to `z`, which is free and worth having on its own.

## Convention must never invent an axis an op might consume

The sharpest thing found while building this, and the reason rung four is not
just "shape".

The obvious convention for spare axes is OME's TCZYX taken from the right, so a
4-D array becomes `(c, z, y, x)`. That is quietly disastrous here. Every image
op in the collection declares `Axes.pack("yxc?")` — an optional channel axis —
so a guessed `c` is not iterated over, it is **consumed**: the array is handed
to the op with its timepoints in the channel slot, where `to_gray` averages
across them and returns a confident, meaningless result.

Guessing `t` wrongly has no such failure mode. No op declares `t`, so a `t` axis
can only be iterated or rejected. The worst case is that the panel iterates over
something the user would have called `z` — and computes exactly the same thing.

So the rule: **convention only invents names no op consumes.** Spare axes get
`t` and `z`, and beyond that positional names like `dim0`. `c` is inferred from
exactly one place — a trailing extent of 3 or 4 — because that reads a real
property of the data rather than filling a slot by position. And even that
defers to the viewer: if the viewer is displaying that trailing axis, it is
spatial, and calling it RGB would transpose the image out from under the user.

## The choice is a combo box, not a prompt

skop 0005 argued for confirming with the user "on the consequence, not the
confidence" — a weak guess being fine when the op will iterate over the unknown
axis anyway, and needing confirmation when the plan would discard data.

Implementing it, the confirmation dialog turned out to be unnecessary. The
plans are already ordered lossless-first, so populating a combo box in that
order and defaulting to the first entry *is* the rule: the default never
discards data, and the plan that does is one visible click away, permanently on
screen, rather than behind a modal that appears at the worst possible moment.

A row per adaptable input, carrying:

- an editable **axes** field, prefilled with the resolution and annotated with
  where it came from — `from layer metadata` versus `from shape and viewer
  layout -- check this`. This doubles as the axis editor, so the "fail fast and
  make the user label the axes" path is just the ordinary path with a bad
  guess in it.
- an **adapt** combo — "run 3 times, once per z position" against "run once at
  z=3, discarding the rest of 3 z". The slice option uses
  `viewer.dims.current_step`, so "the current Z slice" means the one being
  looked at.

An input the op cannot use at all — too few labels, or missing a required axis
— disables Run and puts skop's own explanation in the panel notes, before
anything is dispatched.

## Finding the layer behind the data

`napari.types.ImageData` hands an op the layer's `.data` and drops the layer,
which is exactly the object holding the axis metadata. Rather than change every
image input to a layer annotation — which would alter what every op receives,
adaptable or not — `_axes.layer_for()` finds it again by identity: the combo's
choice stored that same array object.

When it fails, resolution falls through to convention and the panel says so in
the source annotation, so the degradation is visible rather than silent. Worth
revisiting if magicgui ever stops handing over the array itself; the tests would
not catch that, since they would still pass with a shape-based guess.

## Consequences

- `_axes.py` holds resolution and imports no Qt or magicgui, so the rungs are
  testable without a viewer. `_plans.py` holds the widgets.
- Re-planning is driven off the input widget's `changed` signal, and the axes
  field's own edits, but deliberately *not* off `Container.changed` — that also
  fires when the plan combo is used, and choosing a plan must not trigger the
  re-planning that rebuilds the combo.
- Only ops declaring `Axes` grow a row. Everything else behaves exactly as it
  did.
