# LoreGuard

**Strażnik kanonu dla światów tworzonych w Obsidianie.**

LoreGuard skanuje Twój Obsidian vault, wyciąga ustrukturyzowane fakty
z notatek (frontmatter + treść), i wykrywa sprzeczności między nimi —
niezgodne daty śmierci, niemożliwy wiek, sprzeczne relacje rodzinne,
dwa źródła opisujące to samo wydarzenie różnymi liczbami.

LoreGuard nigdy nie edytuje Twoich notatek. Tylko zgłasza konflikty —
Ty decydujesz, czy to błąd, celowy element lore, czy nieporozumienie.

## Jak to działa

```
Obsidian vault
     │
     ▼
skan .md + parser frontmatter/wikilinków
     │
     ▼
encje + fakty (z YAML) ──────────┐
     │                            │
     ▼                            │
Event (daty, uczestnicy)          │
     │                            │
     ▼                            ▼
        Deterministyczny silnik reguł
                    │
                    ▼
              KONFLIKTY
```

Fakty z frontmatter wyciągane są automatycznie przy każdej
synchronizacji. Głębsza analiza — ekstrakcja faktów z prozy i porównanie
semantyczne między dokumentami — korzysta z LLM i jest opcjonalna,
uruchamiana świadomie (per dokument lub zbiorczo), bo kosztuje realne
zapytania API.

## Co wykrywa

- **Sprzeczne fakty** — dwie różne wartości tego samego pytania o tę samą
  osobę/miejsce (np. dwie różne daty śmierci), nawet gdy opisane innymi
  słowami ("zginął" vs "umarł")
- **Złe zakresy dat** — koniec wydarzenia przed jego początkiem
- **Sprzeczne relacje** — "jest córką X" w jednym źródle, "jest siostrą X"
  w drugim
- **Niemożliwy wiek** — ktoś miał podany wiek w roku, który matematycznie
  się nie zgadza z jego datą urodzenia
- **Sprzeczności semantyczne** — dwa dokumenty opisujące to samo
  zdarzenie zupełnie innymi słowami, z różnymi liczbami/detalami
  (wymaga LLM + embeddingów)

Silnik reguł jest świadomie ostrożny: domyślnie tylko wąska lista
predykatów (śmierć, narodziny, stolica) jest traktowana jako
"jednowartościowa". Reszta (tytuły, epitety, dziedziny bóstw) może mieć
wiele wartości naraz bez wywoływania fałszywych alarmów.

## Stack

- **Backend**: FastAPI + SQLAlchemy + PostgreSQL + Alembic
- **Frontend**: Vue 3 + Vite + TypeScript
- **LLM**: wymienny provider — Anthropic Claude lub Google Gemini
  (auto-wykrywany po kluczu API w `.env`)
- **Embeddingi**: Gemini Embedding API (opcjonalne, z offline fallbackiem)

Zero Dockera — działa natywnie na Windows/Linux/Mac.

## Szybki start

### Backend

```bash
cd backend
pip install -r requirements.txt

cp .env.example .env
# uzupełnij DATABASE_PASSWORD, OBSIDIAN_VAULT_PATH,
# opcjonalnie ANTHROPIC_API_KEY i/lub GEMINI_API_KEY

alembic upgrade head
uvicorn app.main:app --reload
```

Backend wystartuje na `localhost:8000`. Dokumentacja API pod `/docs`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Pierwsze uruchomienie

1. Otwórz frontend, wejdź w **Dashboard**, kliknij **"Synchronizuj vault"**
   — to zaindeksuje wszystkie notatki i wyciągnie fakty z frontmatter,
   za darmo, bez LLM
2. (Opcjonalnie) w zakładce **Dokumenty** kliknij **"Wyciągnij fakty
   (LLM)"** na wybranej notatce, żeby wyciągnąć fakty też z prozy —
   wymaga klucza API
3. Sprawdź zakładkę **Konflikty**

## Konfiguracja pod własny vault

LoreGuard nie zakłada z góry angielskiego słownictwa ani sztywnej
struktury notatek. Cały słownik — jakie tagi oznaczają jaki typ encji,
jakie nazwy pól frontmatter oznaczają datę/lokalizację/uczestników,
które predykaty są traktowane jako wzajemnie wykluczające się — jest
konfigurowalny przez opcjonalny plik `.loreguard/schema.yaml` w Twoim
vault, z sensownymi domyślnymi wartościami (PL+EN) na start.

