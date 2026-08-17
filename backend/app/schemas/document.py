from pydantic import BaseModel, Field


class ParsedDocument(BaseModel):
    title: str
    path: str
    content: str
    content_hash: str
    frontmatter: dict = Field(default_factory=dict)