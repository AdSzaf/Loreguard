# LoreGuard
[English version](#) | [Wersja polska](./README_pl.md)

**A canon guardian for world-building and lore in Obsidian vaults.**

LoreGuard scans your Obsidian vault, extracts structured facts from notes (frontmatter + content), and detects contradictions—such as conflicting death dates, impossible ages, contradictory family ties, or differing descriptions of the same event.

LoreGuard **never edits your notes automatically**. It only reports conflicts—you decide whether it's an error, intentional lore, or a misunderstanding.

---

## How It Works

Obsidian Vault 
  ↓
.md scan & Frontmatter/Wikilink Parser
  ↓
Entities + Facts (YAML) ────────┐
  ↓                             │
Event Data (dates, participants)│
  ↓                             ▼
        Deterministic Rules Engine
                    ↓
                CONFLICTS

Frontmatter facts are parsed automatically on sync. Deeper analysis—extracting facts from prose and semantic cross-document comparison—uses optional LLMs, triggered manually per document or in bulk, as it incurs real API costs.

---

## What It Detects

- **Contradictory Facts** — Different values for the same property regarding a person/place (e.g., two different death dates), even when phrased differently.
- **Invalid Date Ranges** — End dates preceding start dates.
- **Contradictory Relations** — "Is daughter of X" in one source vs. "is sister of X" in another.
- **Impossible Age** — Mathematical mismatch between stated age and birth date.
- **Semantic Contradictions** — Two documents describing the same event differently with conflicting numbers/details (requires LLMs + embeddings).

The rules engine is intentionally cautious: by default, only a narrow list of predicates (death, birth, capital city) are treated as single-valued. Everything else allows multiple values without false alarms.

---

## Tech Stack

- **Backend**: FastAPI, SQLAlchemy, PostgreSQL, Alembic
- **Frontend**: Vue 3, Vite, TypeScript
- **LLM**: Interchangeable provider — Anthropic Claude or Google Gemini (auto-detected via `.env` API key)
- **Embeddings**: Gemini Embedding API (optional, with offline fallback)

No Docker required — runs natively on Windows, Linux, and macOS.

---

## Quick Start

### Backend

```bash
cd backend
pip install -r requirements.txt

cp .env.example .env
# Fill in DATABASE_PASSWORD, OBSIDIAN_VAULT_PATH,
# and optionally ANTHROPIC_API_KEY / GEMINI_API_KEY

alembic upgrade head
uvicorn app.main:app --reload

cd frontend
npm install
npm run dev

First Run

    Open the frontend, go to Dashboard, and click "Sync Vault" — this indexes notes and extracts frontmatter facts for free without an LLM.

    (Optional) In the Documents tab, click "Extract Facts (LLM)" on a note to parse prose (requires an API key).

    Check the Conflicts tab.

Customizing for Your Vault

LoreGuard does not enforce English-only vocabularies or rigid note structures. The entire dictionary—which tags map to entity types, which frontmatter fields represent dates/locations, and which predicates conflict—is configurable via an optional .loreguard/schema.yaml file in your vault, complete with sensible defaults (PL+EN) out of the box.