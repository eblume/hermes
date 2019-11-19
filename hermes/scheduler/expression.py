# -*- coding: utf-8 -*-
from enum import Enum
from typing import Optional, cast, Union, TYPE_CHECKING

from ortools.sat.python import cp_model


if TYPE_CHECKING:
    from .schedule import Model, EventBase, Event


class Action(Enum):
    LESS_THAN = lambda a, b: a < b
    GREATER_THAN = lambda a, b: a > b
    LESS_THAN_EQ = lambda a, b: a <= b
    GREATER_THAN_EQ = lambda a, b: a >= b
    AND = lambda a, b: a and b
    OR = lambda a, b: a or b
    NOT = lambda a: a.Not()
    ADD = lambda a, b: a + b
    SUBTRACT = lambda a, b: a - b
    XOR = 10
    EQUALS = 11
    NOT_EQUALS = 12
    MULTIPLY = 13
    ABSOLUTE = 14
    IDENTITY = 15
    OVERLAP = 16

    def apply(
        self,
        model: "Model",
        event: "Event",
        sentinel: "Variable",
        *action_args: "Expression",
    ) -> cp_model.LinearExpr:
        return self.value(*[arg.apply(model, event, sentinel) for arg in action_args])


class Expression:
    def __init__(self, action: Action, *arguments: Union["Expression", "EventBase"]):
        self._args = arguments
        self._action = action

    def apply(
        self, model: "Model", event: "EventBase", sentinel: "Variable"
    ) -> cp_model.LinearExpr:
        pass
        # TODO - finish this
        # return self._action.apply(model, event, sentinel, *self._args)

    # WAIT, WHAT? Why all the crazy type safety code and then just type:
    # ignore? I'll tell you why, dear reader! Or better yet, GVR himself
    # will tell you!: https://github.com/python/mypy/issues/6710
    #
    # And let this be the lesson: before you design a type-safe DSL, check
    # that your language allows Liskov Substitution Principle violation on
    # your DSL's operators. d'oh.
    #
    # (Ironically, this issue strikes at the core of the TimeSpan re-slicing
    # syntax too :( ... turns out, LSP is pretty important, I guess? Did
    # someone a haskell?)

    def __lt__(self, other: "Expression") -> "Expression":  # type: ignore
        if not isinstance(other, Expression):
            return NotImplemented
        return Expression(Action.LESS_THAN, self, other)

    def __gt__(self, other: "Expression") -> "Expression":  # type: ignore
        if not isinstance(other, Expression):
            return NotImplemented
        return Expression(Action.GREATER_THAN, self, other)

    def __lte__(self, other: "Expression") -> "Expression":  # type: ignore
        if not isinstance(other, Expression):
            return NotImplemented
        return Expression(Action.LESS_THAN_EQ, self, other)

    def __gte__(self, other: "Expression") -> "Expression":  # type: ignore
        if not isinstance(other, Expression):
            return NotImplemented
        return Expression(Action.GREATER_THAN_EQ, self, other)

    def __neg__(self, other: "Expression") -> "Expression":  # type: ignore
        return Expression(Action.NOT, self, other)

    def __add__(self, other: "Expression") -> "Expression":  # type: ignore
        if not isinstance(other, Expression):
            return NotImplemented
        return Expression(Action.ADD, self, other)

    def __sub__(self, other: "Expression") -> "Expression":  # type: ignore
        if not isinstance(other, Expression):
            return NotImplemented
        return Expression(Action.SUBTRACT, self, other)

    def __and__(self, other: "Expression") -> "Expression":  # type: ignore
        if not isinstance(other, Expression):
            return NotImplemented
        return Expression(Action.AND, self, other)

    def __or__(self, other: "Expression") -> "Expression":  # type: ignore
        if not isinstance(other, Expression):
            return NotImplemented
        return Expression(Action.OR, self, other)

    def __xor__(self, other: "Expression") -> "Expression":  # type: ignore
        if not isinstance(other, Expression):
            return NotImplemented
        return Expression(Action.XOR, self, other)

    def __eq__(self, other: "Expression") -> "Expression":  # type: ignore
        if not isinstance(other, Expression):
            return NotImplemented
        return Expression(Action.EQUALS, self, other)

    def __ne__(self, other: "Expression") -> "Expression":  # type: ignore
        if not isinstance(other, Expression):
            return NotImplemented
        return Expression(Action.NOT_EQUALS, self, other)

    def __mul__(self, other: "Expression") -> "Expression":  # type: ignore
        if not isinstance(other, Expression):
            return NotImplemented
        return Expression(Action.MULTIPLY, self, other)

    def __abs__(self, other: "Expression") -> "Expression":  # type: ignore
        if not isinstance(other, Expression):
            return NotImplemented
        return Expression(Action.ABSOLUTE, self, other)


class Variable(Expression):
    def __init__(self, name: str):
        super().__init__(Action.IDENTITY, self)
        self._var: Optional[cp_model.IntVar] = None
        self.name = name

    def bind(self, var: cp_model.IntVar) -> None:
        self._var = var

    def apply(self, *_) -> cp_model.LinearExpr:
        # Technically, this returns a cp_model.IntVar, not a cp_model.LinearExpr. However,
        # the or-tools API ensures that in all practical cases that we care about,
        # the two are interchangeable. Note that there is a special case where LinearExpressions must
        # not be non-linear w.r.t. any two variables. It's possible we could enforce that here,
        # but for now we'll just be ok with an error in that case.
        if self._var is None:
            raise ValueError("Attempt to resolve an unbound variable")
        return cast(cp_model.LinearExpr, self._var)

    def __str__(self) -> str:
        return f"Variable<{self.name}>"


class Constant(Variable):
    def __init__(self, name: str, value: int):
        super().__init__(name)
        self._value = value

    def apply(self, *_) -> cp_model.LinearExpr:
        # See Variable.apply, same note applies here.
        return cast(cp_model.LinearExpr, self._value)
