from typing import Any

from pydantic import BaseModel, ConfigDict


class BaseModelORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    def model_dump(self, **kwargs: Any) -> Any:
        # Leaving out unset values keeps column defaults on insert and current values on update.
        # Raw SQL needs every parameter, so its callers ask for `exclude_none=False`.
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(**kwargs)
