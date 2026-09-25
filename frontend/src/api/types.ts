// --- admin / config -----------------------------------------------------
export interface AppConfig {
  tenant_id: string | null;
  client_id: string | null;
  has_client_secret: boolean;
  copilot_sku_ids: string[];
  report_access_group_id: string | null;
  org_view_group_id: string | null;
  schedule_interval_hours: number;
  configured: boolean;
  // Azure OpenAI (analysis engine)
  aoai_endpoint: string | null;
  aoai_deployment: string | null;
  has_aoai_key: boolean;
  analysis_mode: "combined" | "split";
  aoai_configured: boolean;
  updated_at?: string | null;
  updated_by?: string | null;
}

export interface TestConnectionResult {
  ok: boolean;
  token_acquired: boolean;
  subscribed_skus: boolean;
  directory_read: boolean;
  copilot_licensed_users: number | null;
  detail: string | null;
}

export interface TestAoaiResult {
  ok: boolean;
  detail: string | null;
}

export interface JobRun {
  id: number;
  job_name: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  stats: Record<string, unknown> | null;
}

export interface StatusResult {
  configured: boolean;
  last_run: JobRun | null;
  prompts: number;
  conversations: number;
  licensed_users: number;
  entra_users: number;
}

export interface IngestRunResult {
  status: string;
  detail: string;
}

// --- backfill (kept for BackfillPage) -----------------------------------
export interface BackfillProgress {
  status: string; // idle | running | completed | cancelled | failed
  users_total: number;
  users_done: number;
  prompts: number;
  lookback_days: number;
  started_at: string | null;
  updated_at: string | null;
  detail: string | null;
}

export interface BackfillRun {
  id: number;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  stats: Record<string, unknown> | null;
}

export interface BackfillCoverage {
  earliest_covered: string | null;
  earliest_prompt: string | null;
  lookback_days: number | null;
  total_prompts: number;
  has_run: boolean;
  last_run_at: string | null;
}

// --- filters ------------------------------------------------------------
export interface UserOption {
  id: string;
  name: string;
  department: string | null;
  prompts: number;
}

export interface ManagerOption {
  id: string;
  name: string;
}

export interface FilterOptions {
  apps: string[];
  categories: string[];
  sources: string[];
  flags: string[];
  users: UserOption[];
  departments: string[];
  countries: string[];
  managers: ManagerOption[];
}

export interface Person {
  user_id: string;
  name: string;
  department: string | null;
  country: string | null;
  manager: string | null;
  prompts: number;
}

// --- metrics ------------------------------------------------------------
export interface Gcse {
  goal: number | null;
  context: number | null;
  source: number | null;
  expectation: number | null;
}

export interface MetricsSummary {
  prompts: number;
  conversations: number;
  avg_prompt_quality: number | null;
  avg_conversation_quality: number | null;
  pct_high_quality: number;
  user_generated_pct: number;
  pct_well_grounded: number;
  pct_neutral_conversations: number;
  pct_positive_conversations: number;
  gcse: Gcse;
  weakest_gcse_lever: string | null;
  avg_name_confidence: number | null;
  avg_sensitive_confidence: number | null;
  flagged_name: number;
  flagged_sensitive: number;
  flagged_profanity: number;
}

export interface ScoreBucket {
  score: number; // 1..10
  count: number;
}

export interface NamedCount {
  name: string;
  count: number;
}

export interface SentimentData {
  prompt: NamedCount[];
  conversation: NamedCount[];
}

export interface AppQualityRow {
  app: string;
  prompts: number;
  avg_quality: number | null;
}

export interface IntentQualityRow {
  category: string;
  prompts: number;
  avg_quality: number | null;
}

export interface UserRollupRow {
  user_id: string;
  name: string;
  department: string | null;
  prompts: number;
  conversations: number;
  avg_quality: number | null;
  user_generated_pct: number;
}

export interface GcseByIntentRow {
  category: string;
  goal: number | null;
  context: number | null;
  source: number | null;
  expectation: number | null;
}

export interface GovernanceData {
  name_confidence: ScoreBucket[];
  sensitive_confidence: ScoreBucket[];
  curse_confidence: ScoreBucket[];
}

export interface PromptRow {
  prompt_id: string;
  prompt_text: string;
  app: string | null;
  date: string | null;
  created_at: string | null;
  user_id: string | null;
  user_name: string | null;
  department: string | null;
  category: string | null;
  sentiment: string | null;
  source: string; // "User" | "System"
  user_generated: boolean;
  quality_score: number | null;
  quality_rationale: string | null;
  gcse_goal: number | null;
  gcse_context: number | null;
  gcse_source: number | null;
  gcse_expectation: number | null;
  name_confidence: number | null;
  sensitive_confidence: number | null;
  curse_confidence: number | null;
}

export interface ConversationRow {
  conversation_id: string;
  user_id: string | null;
  user_name: string | null;
  department: string | null;
  prompt_count: number;
  avg_prompt_quality: number | null;
  avg_name_confidence: number | null;
  avg_sensitive_confidence: number | null;
  max_curse_confidence: number | null;
  conversation_quality_score: number | null;
  sentiment: string | null;
  category: string | null;
  user_generated_ratio: number | null;
  theme: string | null;
  insight: string | null;
  improvement: string | null;
  suggested_starter_prompt: string | null;
}

export interface ConversationPrompt {
  prompt_id: string;
  prompt_text: string;
  date: string | null;
  created_at: string | null;
  app: string | null;
  category: string | null;
  sentiment: string | null;
  source: string; // "User" | "System"
  user_generated: boolean;
  quality_score: number | null;
  quality_rationale: string | null;
  gcse_goal: number | null;
  gcse_context: number | null;
  gcse_source: number | null;
  gcse_expectation: number | null;
  name_confidence: number | null;
  sensitive_confidence: number | null;
  curse_confidence: number | null;
}

export interface ConversationInfo {
  conversation_id?: string;
  sentiment?: string | null;
  avg_quality_score?: number | null;
  avg_of_prompts: number | null;
  conversation_quality_score?: number | null;
  user_generated_ratio?: number | null;
  theme?: string | null;
  insight?: string | null;
  category?: string | null;
  improvement?: string | null;
  suggested_starter_prompt?: string | null;
  prompt_count?: number;
  user_name?: string | null;
}

export interface ConversationDetail {
  conversation: ConversationInfo | null;
  prompts: ConversationPrompt[];
}

export interface PersonalCoaching {
  user_id: string;
  name: string;
  prompts: number;
  conversations: number;
  avg_quality: number | null;
  user_generated_pct: number;
  gcse_mine: Gcse;
  gcse_team: Gcse;
  weakest_lever: string | null;
  strongest_lever: string | null;
}

export interface Freshness {
  total_prompts: number;
  analysed_prompts: number;
  conversations: number;
  users: number;
  earliest: string | null;
  latest: string | null;
}
