from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    """
    The base of the models the API sends and receives.

    A response always includes every field, also those with a default, so the schema of a model
    as a response requires them. As a request, the same model may leave those fields out.
    """

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class BaseModelORM(ApiModel):
    model_config = ConfigDict(from_attributes=True)
