export interface ProviderConfig {
  id: string;
  kind: "openai-compatible" | "anthropic" | "ollama" | "local-hf";
  label: string;
  base_url?: string | null;
  model: string;
  api_key?: string | null;
  api_key_env?: string | null;
  active: boolean;
}

export interface DocumentMeta {
  id: string;
  filename: string;
  chunks: number;
  embedding: string;
}

export interface SessionMeta {
  id: string;
  scenario: string;
  status: string;
  created_at: number;
  duration_minutes: number;
  subtitles: boolean;
  difficulty: string;
  has_report?: boolean;
  behavior_summary?: BehaviorSummary;
}

export interface TranscriptEntry {
  role: "user" | "assistant";
  text: string;
  ts: number;
}

export interface BehaviorSummary {
  available?: boolean;
  frames?: number;
  face_visible_pct?: number;
  eye_contact_pct?: number;
  head_stability?: number;
  avg_smile?: number;
  blinks?: number;
  confidence_score?: number;
}

export interface ReportDimension {
  name: string;
  score: number;
  comment: string;
}

export interface Report {
  overall_score: number | null;
  summary: string;
  dimensions: ReportDimension[];
  strengths: string[];
  improvements: string[];
  notable_moments: { quote: string; comment: string }[];
  behavior: BehaviorSummary;
  scenario: string;
}

export interface HubModel {
  repo_id: string;
  downloads: number;
  likes: number;
  downloaded: boolean;
  params?: string | null;
  suitable?: boolean;
  reason?: string;
}

export interface RecommendedModel {
  repo_id: string;
  params: string;
  note: string;
  gated?: boolean;
  downloaded: boolean;
  loaded: boolean;
}

export interface LocalModel {
  repo_id: string;
  size_bytes: number;
  loaded: boolean;
}

export interface ChatMessage {
  role: "user" | "assistant";
  text: string;
  streaming?: boolean;
}
