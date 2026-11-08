"""The exact shape the LLM's output must have. Anything else is rejected."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from securebank.intents.catalog import INTENTS

IntentName = Literal[tuple(INTENTS)]  # only the 17 catalog names are accepted


class ParsedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")   # no extra keys like "role" or "sql"

    intent: IntentName
    params: dict[str, str | int | None] = Field(default_factory=dict)

    @model_validator(mode="after")
    def params_belong_to_intent(self):
        allowed = set(INTENTS[self.intent].params)
        unknown = set(self.params) - allowed
        if unknown:
            raise ValueError(f"params {sorted(unknown)} are not allowed for {self.intent}; "
                             f"allowed: {sorted(allowed) or 'none'}")
        # drop empty values so defaults apply
        self.params = {k: v for k, v in self.params.items() if v not in (None, "")}
        return self
