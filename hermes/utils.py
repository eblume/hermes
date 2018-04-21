import attr
from functools import partial


immutable = partial(attr.s, slots=True, frozen=True, auto_attribs=True, hash=True)
