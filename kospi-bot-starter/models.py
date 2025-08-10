from pydantic import BaseModel, AnyHttpUrl, Field
from typing import List, Optional, Literal
from datetime import datetime

ItemType = Literal["DART", "NEWS"]

class UpdateItem(BaseModel):
    type: ItemType
    symbol: Optional[str] = None
    title: str
    url: AnyHttpUrl
    published_at: datetime
    tags: List[str] = Field(default_factory=list)
    score: float = 0.0

class UpdatesResponse(BaseModel):
    items: List[UpdateItem]
