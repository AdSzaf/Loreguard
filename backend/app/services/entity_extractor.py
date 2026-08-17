import re
from dataclasses import dataclass


@dataclass
class EntityCandidate:
    name: str
    display_name: str | None = None
    source: str = "wikilink"


class EntityExtractor:
    WIKILINK_PATTERN = re.compile(
        r"\[\[([^\]|#]+)(?:\|([^\]]+))?\]\]"
    )

    def extract_from_content(
        self,
        content: str,
    ) -> list[EntityCandidate]:
        candidates: list[EntityCandidate] = []
        seen: set[str] = set()

        for match in self.WIKILINK_PATTERN.finditer(content):
            target = match.group(1).strip()
            display_name = match.group(2)

            if display_name:
                display_name = display_name.strip()

            normalized_name = target.casefold()

            if normalized_name in seen:
                continue

            seen.add(normalized_name)

            candidates.append(
                EntityCandidate(
                    name=target,
                    display_name=display_name,
                )
            )

        return candidates