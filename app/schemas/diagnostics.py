import uuid
from decimal import Decimal

from pydantic import BaseModel, Field


class TestCreate(BaseModel):
    name: str = Field(min_length=1)
    price: Decimal = Field(gt=0)


class TestUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    price: Decimal | None = Field(default=None, gt=0)


class TestOut(BaseModel):
    id: uuid.UUID
    centre_id: uuid.UUID
    name: str
    price: Decimal

    model_config = {"from_attributes": True}


class CentreCreate(BaseModel):
    name: str = Field(min_length=1)
    location: str = Field(min_length=1)


class CentreUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    location: str | None = Field(default=None, min_length=1)


class CentreOut(BaseModel):
    id: uuid.UUID
    name: str
    location: str
    tests: list[TestOut] = []

    model_config = {"from_attributes": True}
