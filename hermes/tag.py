# -*- coding: utf-8 -*-
import datetime as dt
import re
from typing import Optional

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
