# -*- coding: utf-8 -*-
import abc
from typing import Dict, List, Mapping, Optional, Union, cast

import attr

from .tag import Category


class BaseCategoryPool(metaclass=abc.ABCMeta):
    @abc.abstractproperty
    @property
    def categories(self) -> Mapping[str, Category]:
        raise NotImplementedError("Subclasses must define this interface")

    def __contains__(self, other: Union[str, Category]) -> bool:
        """When possible, use a Category, it is much faster."""
        if isinstance(other, str):
            for category_name in self.categories.keys():
                if other in category_name:  # string 'in'
                    return True
            return False
        elif isinstance(other, Category):
            other = cast(Category, other)
            return other.fullpath in self.categories
        raise TypeError("CategoryPools contain only Category objects")

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
            parent_cat = None
            if len(category_names) > 1:
                parent_cat = self._get_category_inner(category_names[:-1])
            return Category(category_names[-1], parent_cat)

    def __len__(self) -> int:
        return len(self.categories)


class MutableCategoryPool(BaseCategoryPool):
    def __init__(self) -> None:
        self._categories: Dict[str, Category] = {}

    @property
    def categories(self) -> Mapping[str, Category]:
        return self._categories

    def get_category(self, category_path: str, create: bool = False) -> Category:
        if not create:
            return super().get_category(category_path)
        if category_path in self._categories:
            return self._categories[category_path]

        category_names = [name.strip() for name in category_path.split("/")]
        if not category_names or not all(category_names):
            raise ValueError("Invalid category_path")
        return self._create_categories(category_names)

    def _create_categories(self, category_names: List[str]) -> Category:
        """category_names is assumed to NOT exist in the pool yet"""
        parent_names = category_names[:-1]
        parent_path = "/".join(parent_names)
        parent: Optional[Category] = self._categories.get(parent_path, None)
        if parent_path and not parent:
            parent = self._create_categories(category_names[:-1])
        category = Category(category_names[-1], parent)
        self._categories["/".join(category_names)] = category
        return category


@attr.s(slots=True, frozen=True, auto_attribs=True, hash=True)
class CategoryPool(BaseCategoryPool):
    """Pool of cached categories, searchable by name
    """

    stored_categories: Mapping[str, Category]

    @property
    def categories(self) -> Mapping[str, Category]:
        return self.stored_categories
