# -*- coding: utf-8 -*-
import datetime as dt
import re
from typing import Any, MutableMapping, Optional
from uuid import uuid4 as uuid

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
    def from_span(
        cls, span: Span, name: str, category: Optional[Category] = None, **kwargs
    ) -> "Tag":  # This is where the BaseTag thing is needed.
        if kwargs:  # for subclassing
            raise ValueError("Unknown kwargs", kwargs)

        return cls(
            name=name,
            category=category,
            valid_from=span.begins_at,
            valid_to=span.finish_at,
        )


@attr.s(slots=True, auto_attribs=True)
class MetaTag:
    """Tag with additional Metadata. Note that this class is NOT immutable."""

    tag: Tag
    data: MutableMapping[str, Any] = attr.ib(factory=dict)

    @classmethod
    def create(
        cls,
        name: str,
        category: Optional[Category],
        valid_from: Optional[dt.datetime],
        valid_to: Optional[dt.datetime],
        data: Optional[MutableMapping[str, Any]] = None,
    ) -> "MetaTag":
        tag = Tag(name, category, valid_from, valid_to)
        return cls(tag, data or dict())


class IDTag(MetaTag):
    """A tag with a random unique ID (UUID)"""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.data.setdefault("id", str(uuid()))

    @property
    def id(self) -> str:
        return self.data["id"]
