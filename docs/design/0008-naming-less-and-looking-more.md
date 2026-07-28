# 0008 — Naming less, and looking at the viewer more

Supersedes [0006](0006-axis-awareness.md)'s rung four. There is no rung four
any more: convention no longer invents names at all. What rung four was *also*
doing — reading which axes the viewer has on screen — was the good part, and it
has been promoted out of naming and into the mapping, where it is now always
consulted, in 3-D view as well as 2-D.

## The problem with inventing names

Rung four called a 3-D array `(z, y, x)` because 3-D arrays usually are. That
is a claim about somebody's data made on the strength of its dimensionality,
and 0006 already knew it was dangerous: most of that document is the rule
keeping the invention away from names an op might consume.

Two things made the rule stop being worth its cost.

The first is that the invented name now shows up in three places a user reads —
the axes field, the mapping combos, and the stamped output layer — with nothing
to distinguish it from a name someone actually declared. `-- check this` in the
status line is a thin defence against a field that says `z y x`. Worse, it was
written back onto the layer, so a guess became a declaration on the next run.

The second is that skop stopped needing it. Axis names are hints ([skop design
0006](https://github.com/apposed/scikit-ops/blob/main/docs/design/0006-axis-mapping.md)),
an unnamed axis matches no slot by name and never draws a warning for being fed
to one, and the default mapping is right-aligned — so an unnamed `(3, 8, 6)`
array feeds a `y x` op exactly as an invented `(z, y, x)` one did. The names
were doing no work in the plan. They were only doing work in the display, where
they were doing harm.

So: whatever the rungs cannot read stays unnamed, `None` all the way to skop,
and shown as napari's own `-3 -2 -1`. Nothing is written back onto the layer,
and nothing is stamped onto the output, unless every axis has a real name.

The one inference that survives is `c` from a trailing extent of 3 or 4. It
reads a real property of the data rather than filling a slot by position, and
it is load-bearing in a way the others never were: `c` is the axis ops declare
as optional, and skop fills an optional slot by name only, so an unnamed RGB
axis is iterated over three times instead of being handed to `to_gray` whole.
It still defers to the viewer, for the reason 0006 gives.

## Layout is not a name, it is a mapping

Rung four's other half was sound. Which axes the viewer is displaying is not a
guess — it is a fact about what the user is looking at, and running on what
they can see is the entire job. It was just being expressed in the wrong
currency: as `y` and `x` *names*, which then had to travel through skop's
name-matching to arrive back at the mapping it was always about.

`_axes.displayed()` now reports it as axis indices, and `_plans._guided()`
points the op's spatial slots (`z`, `y`, `x`) straight at them. Consequences of
saying it this way rather than as names:

- **3-D view counts too.** Rung four bailed out whenever `dims.displayed` did
  not hold exactly two axes, because it was after a plane. A mapping does not
  care how many are on screen; both lists are right-aligned, so a 2-D op in a
  3-D view takes the two innermost displayed axes.
- **Names are irrelevant to it.** An axis called `lifetime`, or called nothing
  at all, lands in the `y` slot if that is what is on screen.
- **It outranks the names.** Somebody who has rolled the dims round to look at
  the `zx` plane means to run on the `zx` plane. skop reports that as
  `y is being fed the z axis` — a note, not a gate ([0007](0007-axis-mapping-ui.md))
  — which is the right volume for it. In the ordinary view, where nobody has
  rolled anything, layout and names agree and none of this is visible.
- **A hand-set combo still wins.** The guidance is only applied while the row's
  mapping is `None`, so an explicit choice is never overwritten — and because
  it is re-derived on every re-plan rather than stored, it tracks the viewer
  live until the user takes over. The precedence is: typed axes > chosen
  mapping > viewer layout > names.

The one sharp edge is that forcing a slot can displace another. An optional
slot that loses its axis goes **empty** rather than being handed a spatial axis
it never asked for — 0006's "never invent `c`" rule, arriving from a new
direction.

## Positions by index

`skop.plan(position=)` was keyed by axis name, which stops working when the
common case is an array whose axes have no names: several would collapse onto
one key and "current position" would quietly read slice zero. skop now accepts
an axis index as a key as well, and `_axes.positions()` returns indices. That
is the only change this needed on the skop side.

`_axes.positions()` and `_axes.displayed()` also right-align the viewer's dims
onto the layer's, which rung four could only handle by giving up: napari's
dims belong to the viewer and are shared across its layers, so a 3-D layer in a
4-D viewer has the viewer's axis 1 as its own axis 0.

## Consequences

- `AxisGuess.axes` may contain `None`. `_axes.display()` renders it for a
  human; skop takes it as-is.
- `_axes.parse()` reads a placeholder back as `None`, so a user who edits
  `-3 -2 -1` into `-3 -2 c` has named one axis, not three.
- `_CONVENTIONAL`, `_names_for` and `_by_convention` are gone, and with them
  `dim0`, and the `t`/`z` naming that 0006 spends a section justifying. The
  justification was sound; the feature was not worth it.
- The write-back and stamping loops still compound, but only for real names —
  which is the case where they were compounding something true.

## Still open

- A partly-named array (`lifetime` declared, the rest placeholders) resolves
  fine, but the panel's provenance line describes the whole answer with one
  source. Per-axis provenance would be more honest and probably more UI than it
  is worth.
- `_guided` treats `z`, `y` and `x` as the spatial slot names. A wildcard slot
  (`*`) is deliberately left alone, since it expressed no preference — but an
  op declaring `Axes("*", "*")` for a plane arguably wants the displayed plane
  too.
