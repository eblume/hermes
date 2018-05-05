"""Hermes, the Time Accountant"""

__author__ = """Erich Blume"""
__email__ = "blume.erich@gmail.com"
__version__ = "0.1.1a"

import datetime as dt
import functools
import re
from operator import attrgetter
from typing import Iterable, List, Mapping, Optional, Set, Union, cast, overload

import attr


class Spannable:

    @property
    def span(self) -> "Span":
        raise NotImplementedError("Subclasses must define this interface")

    def __contains__(self, other: "Spannable") -> bool:
        """`other` overlaps at least in part with this object"""
        selfspan = self.span
        otherspan = other.span
        if otherspan.begins_at < selfspan.begins_at:
            return otherspan.finish_at >= selfspan.begins_at

        elif otherspan.finish_at > selfspan.finish_at:
            return otherspan.begins_at <= selfspan.finish_at

        else:
            return True


@attr.s(slots=True, frozen=True, auto_attribs=True, hash=True)
class Tag(Spannable):
    name: str
    category: Optional["Category"]
    valid_from: dt.datetime
    valid_to: dt.datetime

    @property
    def span(self):
        return Span(self.valid_from, self.valid_to)


@functools.total_ordering
@attr.s(slots=True, frozen=True, auto_attribs=True, hash=True)
class Span(Spannable):
    begins_at: dt.datetime
    finish_at: dt.datetime

    @property
    def span(self) -> "Span":
        return self  # It's safe to just return self, due to immutability

    @property
    def duration(self) -> dt.timedelta:
        return self.finish_at - self.begins_at

    def subspans(self, duration: dt.timedelta) -> Iterable["Span"]:
        selfspan = self.span
        start = selfspan.begins_at
        while start < selfspan.finish_at:
            finish = min(start + duration, selfspan.finish_at)
            yield Span(start, finish)

            start = finish


class BaseTimeAccount(Spannable):

    @property
    def category_pool(self):
        raise NotImplementedError("Subclasses must define this interface.")

    def iter_tags(self) -> Iterable["Tag"]:
        raise NotImplementedError("Subclasses must define this interface.")

    def filter(self, category: Union["Category", str]) -> "BaseTimeAccount":
        raise NotImplementedError("Subclasses must define this interface.")

    def reslice(
        self, begins_at: dt.datetime, finish_at: dt.datetime
    ) -> "BaseTimeAccount":
        raise NotImplementedError("Subclasses must define this interface.")

    def __len__(self):
        return len(list(self.iter_tags()))

    # The next two overloads let mypy be comfortable with the abuse we're
    # giving to python's slice syntax. It's clunky as hell, but that's the
    # price you pay when you muck around with things like indexing.

    @overload
    def __getitem__(self, key: int) -> "BaseTimeAccount":  # pragma: no cover
        pass

    @overload  # noqa: F811
    def __getitem__(self, key: slice) -> "BaseTimeAccount":  # pragma: no cover
        pass

    def __getitem__(  # noqa: F811
        self, key: Union[Optional[int], slice]
    ) -> "BaseTimeAccount":
        # Do a little type casting safety dance. Let's find a better way.
        type_error = key is None
        type_error |= not isinstance(key, slice)
        if type_error:
            raise TypeError("BaseTimeAccount objects must be sliced with datetime")

        key = cast(slice, key)

        # And a safety dance for our friends slice.start and slice.stop
        type_error |= key.start is not None and not isinstance(key.start, dt.datetime)
        type_error |= key.stop is not None and not isinstance(key.stop, dt.datetime)
        if type_error:
            raise TypeError("BaseTimeAccount objects must be sliced with datetime")

        start = cast(dt.datetime, key.start)
        stop = cast(dt.datetime, key.stop)

        return self.reslice(start, stop)

    def slice_with_span(self, span: Span) -> "BaseTimeAccount":
        return self.reslice(span.begins_at, span.finish_at)

    def subspans(self, duration: dt.timedelta) -> Iterable["BaseTimeAccount"]:
        for subspan in self.span.subspans(duration):
            yield self.slice_with_span(subspan)


@attr.s(slots=True, frozen=True, auto_attribs=True, hash=True)
class TimeAccount(BaseTimeAccount):
    tags: Set[Tag]

    @property
    def category_pool(self):
        return CategoryPool(
            categories={tag.category.fullpath: tag.category for tag in self.iter_tags()}
        )

    def iter_tags(self) -> Iterable["Tag"]:
        yield from self.tags

    def reslice(self, begins_at: dt.datetime, finish_at: dt.datetime) -> "TimeAccount":
        selfspan = self.span
        newspan = Span(
            begins_at if begins_at is not None else selfspan.begins_at,
            finish_at if finish_at is not None else selfspan.finish_at,
        )
        tags = {t for t in self.tags if t in newspan}
        return TimeAccount(tags=tags)

    @property
    def span(self) -> "Span":
        tags = sorted(self.tags, key=attrgetter("valid_from"))
        oldest = min(tags, key=attrgetter("valid_from"))
        most_recent = max(tags, key=attrgetter("valid_to"))
        return Span(oldest.valid_from, most_recent.valid_to)

    def filter(self, category: Union["Category", str]) -> "BaseTimeAccount":
        if category is None:
            return self  # safe to return self due to immutability

        if isinstance(category, str):
            category = self.category_pool.get_category(category)
        cast(Category, category)

        return TimeAccount(tags={tag for tag in self.iter_tags() if tag in category})

    @classmethod
    def combine(cls, *others: "BaseTimeAccount") -> "TimeAccount":
        tags = {t for other in others for t in other.iter_tags()}
        return TimeAccount(tags)


@attr.s(slots=True, frozen=True, auto_attribs=True, hash=True)
class Category:
    name: str = attr.ib()
    parent: Optional["Category"]

    @name.validator
    def _check_name(self, _, value: str):
        pattern = r"[a-zA-Z][a-zA-Z0-9:\- ]*$"
        if not re.match(pattern, value):
            raise ValueError(f'Category name must match "{pattern}"')

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

    def __contains__(self, tag: Tag) -> bool:
        tag_cat = tag.category
        while tag_cat is not None:
            if tag_cat == self:
                return True

            tag_cat = tag_cat.parent
        return False


@attr.s(slots=True, frozen=True, auto_attribs=True, hash=True)
class CategoryPool:
    """Pool of cached categories, searchable by name
    """
    categories: Mapping[str, Category]

    def __contains__(self, category: Category) -> bool:
        return category is not None and category.fullpath in self.categories

    def get_category(self, category_path: str) -> Category:
        """Return a Category using existing types stored in this pool.

        `category_path` must be a "/"-seperated string. Each substring will be
        a category name. As much as possible, this will use categories already
        stored in the category pool, and then new categories will be constructed.
        """
        category_names = [name.strip() for name in category_path.split("/")]
        if not category_names or not all(category_names):
            raise ValueError("Invalid category_path")

        return self._get_category_inner(category_names)

    def _get_category_inner(self, category_names: List[str]) -> Category:
        category_path = "/".join(category_names)
        if category_path in self.categories:
            return self.categories[category_path]

        else:
            if len(category_names) > 1:
                parent_cat = self._get_category_inner(category_names[:-1])
            else:
                parent_cat = None
            return Category(category_names[0], parent_cat)
