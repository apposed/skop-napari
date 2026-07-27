# 0007 — The axis mapping UI

Supersedes [0006](0006-axis-awareness.md)'s "the choice is a combo box"
section. Everything else in 0006 — the four resolution rungs, writing the
answer back onto the layer, and the rule that convention may only invent axis
names no op consumes — stands unchanged, and matters more than ever.

## What changed underneath

[skop 0006](https://github.com/apposed/scikit-ops/blob/main/docs/design/0006-axis-mapping.md)
removed two things this panel was built on:

- **`Extra`**, the op-author policy saying whether extra axes could be iterated
  over. It turned out not to be the author's call: if `Axes` names everything
  the op depends on, independence follows, and whether per-slice or global
  processing is *scientifically* right is a property of the experiment, which
  only the user knows.
- **`skop.plans()`**, the enumeration. Axis names became hints rather than
  requirements, and the mapping from input axes to op slots became the user's
  to set — so the candidate space is now permutations × dispositions, which is
  not a list you can put in a combo box.

skop now hands over one best-effort `AdaptationPlan` and accepts an edited one.
Rendering and editing that plan is this panel's job.

## The row

Still one row per adaptable image input, and still driven by the same
`edited`-signal-not-`Container.changed` split 0006 established — rendering a
plan must never trigger the re-planning that produced it. What the row carries
has changed:

- the editable **axes** field, exactly as before, prefilled from resolution and
  annotated with its provenance;
- a **mapping combo per slot the op consumes**, labelled with the slot
  (`y ←`, `c? ←`), listing this array's axes, plus `—` for an optional slot
  nobody is filling;
- a **disposition combo per axis left over** — "iterate all 41" against
  "current position", plus "hand to the op" when the op is variadic;
- the plan's **summary** and any **warnings**.

Which controls exist is a function of the plan, so the row is rebuilt wholesale
on every re-plan rather than patched: unmapping a slot moves an axis out of the
mapping group and into the leftover group, growing a disposition control that
did not exist a moment earlier.

### Choosing a taken axis swaps

A mapping is a permutation, so picking an axis another slot already holds has
to displace something, and silently clearing the other slot would be worse than
useless. `_reassign` swaps: putting `z` into the `y` slot sends whatever `y`
held back to where `z` came from. Setting each slot in turn is how the panel
expresses the `Z→y, Y→x, iterate x` case, one combo at a time.

## Warnings are notes, not gates

0006's panel disabled Run when skop refused an input, and skop refused
generously — a missing named axis was fatal. Now a name is a hint, so the same
situation produces `Check: image: y is being fed the z axis` in the notes and
leaves Run enabled.

This keeps 0006's "on the consequence, not the confidence" principle and moves
it one step out. The consequence a user needs to see is no longer *"this will
discard data"* — the default plan cannot discard data, so that case is gone by
construction. It is *"this op is being fed something it did not ask for"*,
which is exactly the case where the run will succeed and may not compute what
was meant. Blocking it would be the old mistake in a new place: the panel does
not know whether feeding `z` to a `y` slot is wrong. The user does.

What still disables Run is what skop still refuses: labels that do not describe
the array, or fewer axes than the op consumes. Those are arithmetic, not
judgement.

## Consequences

- `_axes.py` is untouched, and its "never invent `c`" rule is now enforced from
  skop's side too — an optional slot fills by name match and never by position
  — so a wrong guess is caught twice rather than once.
- `_panel.py` gained only a notes line; `Adaptations.plans`, `problems` and
  `output_axes` kept their shapes, so `_run.py` is unchanged.
- Results are stamped with the plan's `output_axes`, which now come back in the
  user's own vocabulary — a remapped run produces `("x", "z", "y")`, not the
  op's slot names.

## Still open

- The mapping combos list axes by name. With many axes this gets long; a
  drag-to-reorder or a small matrix widget might read better, but a combo per
  slot is honest about what the underlying value is.
- Nothing yet remembers a *mapping* across layer changes the way `_axes.remember`
  remembers axis labels. Choices are deliberately dropped when the layer or the
  axis labels change, since the indices would no longer mean the same thing;
  whether a remap is worth persisting per layer is unexplored.
