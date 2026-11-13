"""Browser actions a tool call may ask for, validated before any page is opened.

An unknown action type, a missing selector or a non-numeric scroll offset is
rejected up front, so a measurement never silently skips the interaction it
was asked to measure.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError


class _Action(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ClickAction(_Action):
    """Click the first element matching ``selector``."""

    type: Literal["click"]
    selector: str = Field(min_length=1)


class TypeAction(_Action):
    """Fill the element matching ``selector`` with ``text``."""

    type: Literal["type"]
    selector: str = Field(min_length=1)
    text: str = ""


class ScrollAction(_Action):
    """Scroll the window down by ``y`` pixels (negative scrolls up)."""

    type: Literal["scroll"]
    y: float = Field(default=500.0, allow_inf_nan=False)


class HoverAction(_Action):
    """Move the pointer over the element matching ``selector``."""

    type: Literal["hover"]
    selector: str = Field(min_length=1)


class WaitAction(_Action):
    """Wait ``duration`` seconds (capped by ``MAX_RECORDING_DURATION``)."""

    type: Literal["wait"]
    duration: float = Field(default=1.0, ge=0, allow_inf_nan=False)


Action = Annotated[
    ClickAction | TypeAction | ScrollAction | HoverAction | WaitAction,
    Field(discriminator="type"),
]

_ACTIONS: TypeAdapter[list[Action]] = TypeAdapter(list[Action])


class InvalidActionsError(ValueError):
    """Raised when the requested actions do not validate."""


def parse_actions(actions: Sequence[Action | Mapping[str, Any]] | None) -> list[Action]:
    """Validate a list of actions (models or plain dicts) into action models."""
    if not actions:
        return []
    raw = [a.model_dump() if isinstance(a, BaseModel) else dict(a) for a in actions]
    try:
        return _ACTIONS.validate_python(raw)
    except ValidationError as err:
        problems = "; ".join(
            f"actions[{'.'.join(str(p) for p in e['loc'])}]: {e['msg']}" for e in err.errors()
        )
        raise InvalidActionsError(f"Invalid actions: {problems}") from err
