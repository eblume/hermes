# -*- coding: utf-8 -*-
from collections.abc import MutableMapping
import datetime as dt
import re
from typing import Any, Iterable, Mapping, Optional

import attr

from .span import Span, Spannable


@attr.s(slots=True, frozen=True, auto_attribs=True, hash=True)
class Category:
    name: str = attr.ib()
    parent: Optional["Category"]

    @name.validator
    def _check_name(self, _, value: str):
        pattern = r"[a-zA-Z][a-zA-Z0-9:\- ]*$"
        if not re.match(pattern, value):
            raise ValueError(f'Category name {value} must match "{pattern}"')

    def __truediv__(self, other: str):
        """Create a new category as a subcategory of this one.
        """
        return Category(other, parent=self)

    @property
    def fullpath(self):
        if self.parent is None:
            return self.name

        else:
            return f"{self.parent.fullpath}/{self.name}"

    def __contains__(self, tag: "Tag") -> bool:
        tag_cat = tag.category
        while tag_cat is not None:
            if tag_cat == self:
                return True

            tag_cat = tag_cat.parent
        return False


@attr.s(slots=True, frozen=True, auto_attribs=True, hash=True)
class Tag(Spannable):
    name: str
    category: Optional[Category] = attr.ib(default=Category("No Category", None))
    valid_from: Optional[dt.datetime] = attr.ib(default=None)
    valid_to: Optional[dt.datetime] = attr.ib(default=None)

    @property
    def span(self):
        return Span(
            self.valid_from or dt.datetime.max, self.valid_to or dt.datetime.max
        )

    def recategorize(self, category: Category) -> "Tag":
        return Tag(self.name, category, self.valid_from, self.valid_to)

    @classmethod
    def from_span(cls, span: Span, name: str, category: Optional[Category] = None, **kwargs) -> "Tag":
        if kwargs:  # for subclassing
            raise ValueError("Unknown kwargs", kwargs)

        return cls(name=name, category=category, valid_from=span.begins_at, valid_to=span.finish_at)


MetaMapT = Optional[Mapping[str, Any]]


class MetaTag(Tag, MutableMapping):
    """Tag with additional Metadata. Serialization of data (JSON, YAML, etc.)
    is not considered in this class.

    Note that the metadata stored in such a tag is mutable, and is NOT part
    of the hashable 'core data' included in every Tag. So while you can have
    two MetaTags with different data but the same core data, they will still
    evaluate as being equivalent. Example:

    >>> time1 = datetime.now()
    >>> time2 = time1 + timedelta(seconds=5)
    >>> t1 = MetaTag("Foo", None, time1, data={'foo': 'bar'})
    >>> t2 = MetaTag("Foo", None, time2, data={'biff': 'boff'})
    >>> t1 == t2
    True
    >>> hash(t1) == hash(t2)
    True
    """

    def __init__(self, data: MetaMapT=None, **kwargs) -> None:
        super().__init__(**kwargs)
        object.__setattr__(self, "_data", data or {})  # MetaTags are no longer frozen

    @classmethod
    def from_span(cls, span: Span, data: MetaMapT=None, **kwargs) -> "MetaTag":
        tag = super().from_span(span, **kwargs)
        return cls.from_tag(tag, data)

    @classmethod
    def from_tag(cls, tag: Tag, data: MetaMapT=None) -> "MetaTag":
        return cls(name=tag.name, category=tag.category, valid_from=tag.valid_from, valid_to=tag.valid_to, data=data)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

    def __delitem__(self, key: str) -> None:
        del self._data[key]

    def __iter__(self) -> Iterable[str]:
        yield from self._data

    def __len__(self) -> int:
        return len(self._data)
