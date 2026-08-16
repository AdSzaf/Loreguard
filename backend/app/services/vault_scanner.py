from pathlib import Path

from app.core.config import settings


class VaultScanner:
    def __init__(self, vault_path: str | None = None):
        self.vault_path = Path(
            vault_path or settings.obsidian_vault_path
        )

    def validate_vault(self) -> bool:
        return self.vault_path.exists() and self.vault_path.is_dir()

    def scan_markdown_files(self) -> list[Path]:
        if not self.validate_vault():
            raise FileNotFoundError(
                f"Obsidian vault not found: {self.vault_path}"
            )

        return list(self.vault_path.rglob("*.md"))