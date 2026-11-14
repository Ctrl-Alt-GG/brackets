from pydantic import BaseModel, ConfigDict


class BaseModelORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)
