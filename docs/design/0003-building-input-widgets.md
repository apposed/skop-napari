# 0003 — Building input widgets one parameter at a time

## The obvious approach, and why it fails

magicgui's headline feature is `magicgui(some_function)`: hand it a callable,
get a form. The natural implementation here is to synthesize a function with
the op's signature and hand *that* over.

It fails on real ops. `unseg` has a `tuple[int, ...]` parameter, and magicgui
cannot render it — `ValueError: No widget found for type Ellipsis`. With the
whole-function approach that exception takes down the entire form, so one
awkward parameter makes an otherwise perfectly runnable op unreachable.

And it will keep happening. Ops are written by scientists against scientific
libraries; the signatures contain whatever the science needed. A GUI layer that
requires every parameter to be renderable is a GUI layer that shows a shrinking
subset of the collection.

## The decision

`build_inputs()` walks `spec.params` and calls `create_widget` once per
parameter, catching failure per parameter and sorting the casualties:

```python
@dataclass
class Inputs:
    widgets: list[Widget]
    defaulted: list[tuple[str, str]]   # unrenderable, but has a default
    blocking: list[tuple[str, str]]    # unrenderable and required

    @property
    def runnable(self) -> bool:
        return not self.blocking
```

- **Unrenderable with a default** → silently left at its default, and named in
  the panel's notes: *"Not editable here, using defaults: shape"*. The op runs.
- **Unrenderable and required** → Run is disabled, and the notes say which
  parameter and why. The op does not run, but the panel still works and the
  user knows exactly what is wrong.

The `except Exception` is deliberately broad, with the reasoning in the code:
any failure to build a widget is the same failure, and distinguishing
magicgui's error taxonomy buys nothing when the response is identical.

## Details worth not rediscovering

**`Undefined`, not `None`, for a required parameter's initial value.**
magicgui treats a `None` value as marking the widget *nullable*, which puts an
empty entry at the top of every layer combo box. `Undefined` from
`magicgui.types` is the "no value yet" sentinel. This produced a puzzling
stray blank row in every image selector until it was tracked down.

**Do not set a layer combo's value programmatically.** Assigning
`image.value = layer.data` raises `ValueError: truth value of an array with
more than one element is ambiguous`, because magicgui's `ComboBox` finds the
matching item with `itemData(i) == value` and numpy overloads `==`. A combo
built with choices present already selects the first one, which is what a user
would have to do anyway.

**Layer combos offer `.data`, not layers.** `napari.types.ImageData` gives the
op the underlying array, which is what the op's `np.ndarray` signature asked
for. A `Layer` would have to be unwrapped somewhere, and the op is the wrong
place because the op must not import napari.

**Tooltips come from the docstring.** `param_docs()` parses a Google-style
`Args:` section. This is a small parser rather than a docstring library on
purpose — the dependency would exist to read one section of one format.

## Where roles change the shape

A parameter with `Role.image` becomes `napari.types.ImageData`, which magicgui
renders as a combo box over the viewer's image layers rather than a file picker
or a text field. That single substitution is most of what makes the generated
forms usable, and it is the payoff for
[roles existing in skop at all](https://github.com/apposed/scikit-ops/blob/main/docs/design/0003-semantic-roles.md).

`Out` parameters never appear — a user is never asked to supply an output
buffer. That filtering is in skop's `ParamSpec.direction`, not here.
