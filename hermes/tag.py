# -*- coding: utf-8 -*-
import abc
from dataclasses import dataclass, field
import datetime as dt
import re
from typing import Any, MutableMapping, Optional, Type, TypeVar
from uuid import uuid4 as uuid

from .span import Span, Spannable


@dataclass(frozen=True)
class Category:
    name: str
    parent: Optional["Category"] = None

    def __post_init__(self):
        pattern = r"[a-zA-Z][a-zA-Z0-9:\- ]*$"
        if not re.match(pattern, self.name):
            raise ValueError(f'Category name {self.name} must match "{pattern}"')

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


_BaseTagT = TypeVar("_BaseTagT", bound="BaseTag")


class BaseTag(Spannable, metaclass=abc.ABCMeta):
    def __init__(
        self,
        name: str,
        category: Optional[Category],
        valid_from: Optional[dt.datetime],
        valid_to: Optional[dt.datetime],
    ):
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def name(self) -> str:
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def category(self) -> Optional["Category"]:
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def valid_from(self) -> Optional[dt.datetime]:
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def valid_to(self) -> Optional[dt.datetime]:
        raise NotImplementedError()

    @property
    def span(self) -> "Span":
        return Span(
            self.valid_from or dt.datetime.max, self.valid_to or dt.datetime.max
        )

    def recategorize(self: _BaseTagT, category: Category) -> _BaseTagT:
        return type(self)(self.name, category, self.valid_from, self.valid_to)

    @classmethod
    def from_span(
        cls: Type[_BaseTagT],
        span: Span,
        name: str,
        category: Optional[Category] = None,
        **kwargs,
    ) -> _BaseTagT:
        if kwargs:
            raise ValueError("Unknown kwargs", kwargs)

        return cls(
            name=name,
            category=category,
            valid_from=span.begins_at,
            valid_to=span.finish_at,
        )


@dataclass(frozen=True, order=True)
class Tag(BaseTag):
    name: str
    category: Optional[Category] = None
    valid_from: Optional[dt.datetime] = None
    valid_to: Optional[dt.datetime] = None


_MTagT = TypeVar("_MTagT", bound="MetaTag")


@dataclass(frozen=True)
class MetaTag(BaseTag):
    """Tag with additional Metadata. Note that `data` IS mutable."""

    name: str
    category: Optional[Category] = None
    valid_from: Optional[dt.datetime] = None
    valid_to: Optional[dt.datetime] = None
    data: MutableMapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_tag(
        cls: Type[_MTagT],
        tag: BaseTag,
        data: MutableMapping[str, Any],
        merge_data: bool = True,
    ) -> _MTagT:
        if merge_data and isinstance(tag, MetaTag):
            data = {**tag.data, **data}

        return cls(
            name=tag.name,
            category=tag.category,
            valid_from=tag.valid_from,
            valid_to=tag.valid_to,
            data=data,
        )


class IDTag(MetaTag):
    """A tag with a random unique ID (UUID)"""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.data.setdefault("id", str(uuid()))

    @property
    def id(self) -> str:
        return self.data["id"]
