export type EntityType =
  | "person"
  | "deity"
  | "country"
  | "region"
  | "place"
  | "race"
  | "organization"
  | "faction"
  | "item"
  | "event"
  | "concept"
  | "other";

export type ConflictStatus = "open" | "confirmed" | "dismissed" | "explained";
export type ConflictSeverity = "low" | "medium" | "high";
export type DatePrecision = "day" | "month" | "year" | "approximate" | "unknown";

export interface DashboardSummary {
  documents: number;
  entities: number;
  facts: number;
  events: number;
  conflicts_total: number;
  conflicts_open: number;
  canon_health_percent: number;
  open_conflicts_preview: {
    id: number;
    entity: string;
    severity: ConflictSeverity;
    explanation: string;
  }[];
}

export interface DocumentSummary {
  id: number;
  title: string;
  path: string;
  indexed_at: string | null;
  file_modified_at: string;
  entities_linked: number;
  has_embedding?: boolean;
}

export interface LlmStatus {
  active_provider: string | null;
  model?: string | null;
  anthropic_key_set: boolean;
  gemini_key_set: boolean;
}

export interface ExtractedFactView {
  predicate: string;
  value: string | null;
  confidence: number;
  source_text: string | null;
}

export interface LlmExtractionResult {
  document?: string;
  facts_extracted?: number;
  facts?: ExtractedFactView[];
  conflicts?: {
    candidates_found: number;
    created: number;
    skipped_existing: number;
  };
  error?: string;
}

export interface EntitySummary {
  id: number;
  name: string;
  entity_type: EntityType;
  aliases: string[];
  documents: number;
}

export interface FactView {
  id: number;
  predicate: string;
  value: string | null;
  source_document: string;
  subject?: string;
}

export interface EntityDetail extends Omit<EntitySummary, "documents"> {
  facts: FactView[];
  conflicts: {
    id: number;
    rule_name: string;
    status: ConflictStatus;
    explanation: string;
  }[];
}

export interface EventParticipantView {
  name: string;
  role: string | null;
}

export interface EventView {
  id: number;
  name: string;
  date_text: string | null;
  date_start_year: number | null;
  date_end_year: number | null;
  precision: DatePrecision;
  location: string | null;
  outcome: string | null;
  participants: EventParticipantView[];
  source_document: string;
}

export interface FactRef {
  predicate: string;
  value: string | null;
  source_document: string;
}

export interface ConflictView {
  id: number;
  entity: string;
  rule_name: string;
  severity: ConflictSeverity;
  confidence: number;
  status: ConflictStatus;
  explanation: string;
  fact_a: FactRef | null;
  fact_b: FactRef | null;
  related_event: string | null;
  resolution_note: string | null;
}

export interface SyncResult {
  files_found: number;
  documents_synced: number;
  documents: {
    id: number;
    title: string;
    path: string;
    entities_linked: number;
    facts_extracted: number;
    is_event: boolean;
  }[];
  conflicts: {
    candidates_found: number;
    created: number;
    skipped_existing: number;
  };
}
