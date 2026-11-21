from pydantic import BaseModel,Field
class DrillInput(BaseModel):
    name:str=Field(min_length=2,max_length=160)
    idempotency_key:str=Field(min_length=4,max_length=120)
