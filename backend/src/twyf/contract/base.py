from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from pydantic.json_schema import SkipJsonSchema


class Wire(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid", frozen=True)


type Opt[T] = T | SkipJsonSchema[None]  # an optional field that is omitted, never null
