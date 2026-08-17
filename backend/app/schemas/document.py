from datetime import datetime

from pydantic import BaseModel, Field


class ParsedDocument(BaseModel):
    title: str
    path: str
    content: str
    content_hash: str
    file_modified_at: datetime
    frontmatter: dict = Field(default_factory=dict)