# Spec — splitting the panel up

**Status:** blocked on napari. Nothing to build here yet.

## Why this file exists

[Design 0002](../design/0002-one-panel-for-all-ops.md) chose a single Ops
widget carrying an op picker, because npe2 wants a static `napari.yaml` and
skop discovers its ops by importing them. That decision is a workaround, and it
should be revisited — not reasoned about from scratch — when napari's planned
support for dynamic command registration lands.

## What changes when it does

Each op becomes its own command and its own widget:

- In the *Plugins* menu, in command search, individually bindable.
- Layer-type filtering per command, so an op needing labels can gray itself out
  when the viewer has none.
- Several op forms open at once, which the single-selection panel cannot do.

## What already anticipates it

The split is not a rewrite. The per-op work is already separated from the
picker:

| File | Fate |
| --- | --- |
| `_widget.py` | unchanged — already builds a form from one `OpSpec` |
| `_roles.py` | unchanged |
| `_run.py` | unchanged |
| `_panel.py` | splits: picker logic dies, the rest becomes a per-op widget |

Concretely, `OpsPanel` today does two jobs — choose an op, and present one op.
`_select()` is the boundary between them. The per-op widget is everything from
`_select()` down, constructed with a fixed `OpSpec` instead of reading one from
a combo box.

## Open questions to answer then, not now

- **Where do commands come from?** `discover()` runs at import time and takes
  as long as importing every op module. Registering dozens of commands at
  napari startup may need to be lazy or cached.
- **One `Runner` or many?** Today the panel owns one, which keeps workers warm
  across ops. Per-op widgets would each want that sharing, so the `Runner`
  moves up to a module-level or plugin-level singleton — with a lifecycle
  question (when does it close?) that the current per-panel ownership answers
  for free.
- **Does the picker survive?** Possibly worth keeping alongside, as a browse
  view for a collection too large for a menu. napari-imagej keeps its search
  widget for exactly that reason.

## Do not pre-build this

The temptation is to restructure now "so it's ready". Resist it: the shape of
the eventual API is unknown, and the current single-panel design is not
suffering from being one file. The one thing worth maintaining is the
`_select()` boundary staying clean.

Graduate this file into `design/` when the split happens.
