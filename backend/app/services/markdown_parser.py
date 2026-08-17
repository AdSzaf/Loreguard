import hashlib
from pathlib import Path

import frontmatter

from app.schemas.document import ParsedDocument


class MarkdownParser:
    def parse(self, file_path: Path, vault_path: Path) -> ParsedDocument:
        post = frontmatter.load(file_path)

        relative_path = file_path.relative_to(vault_path)

        title = self._extract_title(
            file_path=file_path,
            frontmatter_data=post.metadata,
        )

        content = post.content

        return ParsedDocument(
            title=title,
            path=str(relative_path),
            content=content,
            content_hash=self._calculate_hash(content),
            frontmatter=post.metadata,
        )

    @staticmethod
    def _extract_title(
        file_path: Path,
        frontmatter_data: dict,
    ) -> str:
        if "title" in frontmatter_data:
            return str(frontmatter_data["title"])

        return file_path.stem

    @staticmethod
    def _calculate_hash(content: str) -> str:
        return hashlib.sha256(
            content.encode("utf-8")
        ).hexdigest()