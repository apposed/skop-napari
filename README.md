# skop-napari

Run [scikit-ops](https://github.com/apposed/scikit-ops) ops from napari.

Adds one dock widget, **Ops**, which lists every op skop can discover, builds
a form for the chosen one, and runs it in its own Appose environment — off
the GUI thread, with progress and cancellation, and with its outputs added to
the viewer as the layer types their roles call for.

```sh
uv sync --all-groups
uv run napari
```

Then *Plugins → scikit-ops → Ops*.

## What it does with an op

An op is an ordinary Python function carrying enough annotation to describe
itself. This package reads that description and nothing else — it knows about
no op in particular.

| From the op | Becomes |
| --- | --- |
| a parameter's type | a magicgui widget |
| `Annotated[..., {...}]` UI hints | that widget's type, range, step |
| the docstring's `Args:` section | the widget's tooltip |
| an `ImageData`/`LabelsData`/… role | a layer combo box, not a file picker |
| an `Out[...]` parameter | nothing — a user is never asked for a buffer |
| the op's `env` | the Appose environment it runs in |
| `skop.progress(...)` | the progress bar |
| `skop.cancel_requested()` | the Cancel button |
| an output's role | an Image / Labels / Points / … layer |
| an output with no role | a row in the results panel |

That last pair is the point of skop's roles. `otsu` returns `LabelsData`, so
its result arrives as a Labels layer rather than a grayscale image; `unseg`
returns two `LabelsData` and two `int`s, so it produces two Labels layers and
two rows of counts.

## Layout

```
src/skop_napari/_roles.py   Role -> napari type; the only napari-specific part
src/skop_napari/_widget.py  OpSpec -> magicgui widgets (imports no napari)
src/skop_napari/_run.py     running an op off the GUI thread
src/skop_napari/_panel.py   the Ops widget itself
```

`_widget.py` deliberately imports nothing from napari: the one napari-shaped
decision, what type each parameter should be rendered as, is passed in as
`annotation_for`. If a second magicgui host ever turns up, that module is what
moves out.

## Design notes

**One widget, not one per op.** npe2 wants a static manifest, while skop finds
its ops by importing them, so a contribution per op would mean generating the
manifest at build time and losing the ability to drop in a new op and see it
appear. The napari team is working on dynamic registration; `_panel.py` is
what gets split up when it lands.

**Widgets are built one parameter at a time**, rather than by handing magicgui
a synthesized function. Real ops contain parameters magicgui cannot render —
`unseg` has `tuple[int, ...]` — and one of those must not take the whole panel
down. An unrenderable parameter with a default is quietly left at its default
and reported in the notes; one without a default disables the Run button and
says why.

**Roles are guessed here, never in skop.** skop reports `role is None` for an
unannotated array rather than assuming it is an image. This package makes that
assumption, because it has a viewer to make it for.

## Development

```sh
uv sync --all-groups
uv run pytest
uv run ruff check --fix && uv run ruff format
```

The tests drive a real napari viewer and run real ops in the `minimal` and
`skimage` Appose environments, which are built on first use.

Note that they need a real Qt platform: `QT_QPA_PLATFORM=offscreen` has no GL
context, and napari's vispy canvas segfaults on startup without one.
