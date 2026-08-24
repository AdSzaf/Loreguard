from dataclasses import dataclass

from app.core.wikilinks import iter_wikilinks


@dataclass
class EntityCandidate:
    name: str
    display_name: str | None = None
    source: str = "wikilink"


class EntityExtractor:
    def extract_from_content(
        self,
        content: str,
    ) -> list[EntityCandidate]:
        candidates: list[EntityCandidate] = []
        seen: set[str] = set()

        for target, display_name in iter_wikilinks(content):
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