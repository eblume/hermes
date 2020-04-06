# -*- coding: utf-8 -*-
from datetime import datetime
from enum import Enum
from functools import reduce
from typing import Any, Optional, Union, cast

from ortools.sat.python import cp_model


def _special(message):
    """Denotes a special action that must be handled outside of the usual flow."""

    def _inner(*_):
        raise NotImplementedError(message)

    return _inner


class Action(Enum):
    LESS_THAN = lambda x, y: x < y
    GREATER_THAN = lambda x, y: x > y
    LESS_THAN_EQ = lambda x, y: x <= y
    GREATER_THAN_EQ = lambda x, y: x >= y
    AND = lambda x, y: x and y
    OR = lambda x, y: x or y
    NOT = _special("Negation expressions are a custom action")
    ADD = lambda x, y: x + y
    SUBTRACT = lambda x, y: x - y
    EQUALS = lambda x, y: x == y
    NOT_EQUALS = lambda x, y: x != y
    MULTIPLY = lambda x, y: x * y
    IDENTITY = _special("Identity expressions are a custom action")


class Expression:
    """Expressions form the nodes of the tree representing a constraint as an AST.
    Each expression has an action that resolves that expression, and this is accomplished
    by using `apply()`. The result is a cp_model Expression that can be added as
    a constraint.

    To put it another way, the Expression class lets you build up a linear
    constraint like "y = mx + b", by representing it (here in S-expressions) as:

    (= y (+ (* m x) b))

    Then, once you've built such an expression (and have the root expression
    that contains it all), you can call `apply` on it to turn that in to a single
    object that the cp_model engine can use.
    """

    def __init__(self, action: Action, *arguments: "Expression"):
        self._args = arguments
        self._action = action

    def __repr__(self) -> str:
        return f"EXPR: {self._action}({','.join(map(str,self._args))})"

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Expression):
            return False
        return all((self._args == other._args, self._action == other._action))

    def apply(self) -> cp_model.LinearExpr:
        if self._action == Action.IDENTITY:
            arg = self._args[0]
            if isinstance(arg, Variable):
                return arg._var
            else:
                return arg.apply()
        elif self._action == Action.NOT:
            arg = self._args[0].apply()
            return not arg
        elif isinstance(self._action, type(lambda a, b: 0)):
            args = [arg.apply() for arg in self._args]
            return reduce(self._action, args)
        else:
            raise ValueError("Uknown action", self._action)

    def after(self, other: Union["Expression", datetime]) -> "Expression":
        if isinstance(other, datetime):
            other = Constant(int(other.timestamp()))
        return Expression(Action.GREATER_THAN, self, other)

    def before(self, other: Union["Expression", datetime]) -> "Expression":
        if isinstance(other, datetime):
            other = Constant(int(other.timestamp()))
        return Expression(Action.LESS_THAN, self, other)

    def and_(self, other: Union["Expression", bool]) -> "Expression":
        if isinstance(other, bool):
            other = Constant(1 if other else 0)
        return Expression(Action.AND, self, other)


class Variable(Expression):
    """Variables descend from Expressions so that they can be used in the DSL
    as a substitute for an expression. Their action is fixed to 'IDENTITY', and
    their only argument is a self reference - so in general, do not treat them
    like expressions unless composing them in the DSL. They are different.

    Internally, they store a reference to a singleton variable object in the
    final model (once that model is bound).
    """

    # Someone double check me on this, but I believe there is an implicit
    # constraint on the use of Variables in composing Expressions: a given
    # Expression must terminate with 2 and only 2 variables. This ensures the
    # linearity of the constraint, which is a necessity of this solver engine
    # (a linear constraint solver). Maybe this could be enforced at runtime?

    def __init__(self, name: str):
        super().__init__(Action.IDENTITY, self)
        self._var: Optional[cp_model.IntVar] = None
        self.name = name

    def bind(self, var: cp_model.IntVar) -> None:
        self._var = var

    def apply(self) -> cp_model.IntVar:
        if self._var is None:
            raise ValueError("Variable must be bound before it can be applied.")
        return self._var

    def __repr__(self) -> str:
        return f"VAR: '{self.name}'"

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Variable):
            return False
        return self.name == other.name


class Constant(Variable):
    """Constants are Variables, because they represent Variables in the model.
    The 'constant' in their name refers to the fact that they have a fixed value.
    """

    def __init__(self, value: int):
        super().__init__("constant")
        self._value = value

    def __repr__(self) -> str:
        return f"CONST: ({self._value})"

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Constant):
            return False
        return self._value == other._value

    def apply(self) -> cp_model.IntVar:
        return cast(cp_model.IntVar, self._value)
