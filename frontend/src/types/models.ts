export type Role = 'admin' | 'engineer' | 'viewer';

export type Permission =
  | 'streams:read'
  | 'streams:write'
  | 'events:read'
  | 'runs:read'
  | 'runs:trigger'
  | 'rejected:read'
  | 'rejected:replay'
  | 'schema:read'
  | 'schema:write'
  | 'audit:read';

export interface User {
  id: string;
  email: string;
  display_name: string;
  role: Role;
  role_label?: string;
  is_active: boolean;
  permissions?: Permission[];
}

export type CdcOp = 'insert' | 'update' | 'delete';
export type StreamStatus = 'healthy' | 'lagging' | 'paused' | 'error';
export type RunStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'canceled';
export type CompatLevel = 'full' | 'backward' | 'forward' | 'breaking';
export type RejectReason = 'schema_mismatch' | 'pk_missing' | 'parse_error' | 'type_conflict';
export type RejectStatus = 'pending' | 'replayed' | 'dismissed';

export interface StreamSummary {
  event_total: number;
  by_op: { insert: number; update: number; delete: number };
  pending_rejected: number;
  last_run: {
    id: string;
    status: RunStatus;
    upserted_count: number;
    finished_at: string | null;
  } | null;
}

export interface Stream {
  id: string;
  name: string;
  source_db: string;
  source_table: string;
  pk_column: string;
  watermark_lsn: number;
  watermark_display: string;
  max_lsn: number;
  max_lsn_display: string;
  lag: number;
  status: StreamStatus;
  status_label: string;
  description: string;
  owner_team: string;
  last_event_at: string | null;
  created_at: string;
  summary: StreamSummary;
}

export interface BoardTotals {
  stream_count: number;
  event_count: number;
  pending_rejected: number;
  active_runs: number;
  succeeded_runs: number;
  generated_at: string;
}

export interface Board {
  streams: Stream[];
  totals: BoardTotals;
  rejected_by_reason: Record<string, number>;
  run_stats: { total_runs: number; succeeded_runs: number; avg_duration_ms: number };
}

export interface CdcEvent {
  id: string;
  stream_id: string;
  lsn: number;
  lsn_display: string;
  received_seq: number;
  op: CdcOp;
  op_label: string;
  pk_value: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  reject_reason: RejectReason | null;
  reject_reason_label: string | null;
  reject_detail: string | null;
  replayed_from_id: string | null;
  received_at: string | null;
}

export interface FieldDiff {
  field: string;
  before: unknown;
  after: unknown;
}

export interface EventDiff {
  event: CdcEvent;
  added: FieldDiff[];
  removed: FieldDiff[];
  changed: FieldDiff[];
  unchanged: FieldDiff[];
  summary: { added: number; removed: number; changed: number; unchanged: number };
}

export interface RunCounts {
  received: number;
  processed: number;
  inserted: number;
  updated: number;
  deleted: number;
  rebuilt: number;
  upserted: number;
  duplicate: number;
  rejected: number;
  conflicted: number;
}

export interface AmountAuditItem {
  pk: string;
  base: number | null;
  expected: number;
  actual: number | null;
  mismatch: boolean;
  delta_sum: number;
}

export interface MergeResult {
  window: { start: number; end: number; size: number };
  strategy: string;
  counts: RunCounts;
  watermark_after: number;
  gap: number | null;
  rows: Array<{
    pk: string;
    op: string;
    last_lsn: number;
    rebuilt: boolean;
    values: Record<string, unknown>;
  }>;
  conflicts: Array<{
    pk: string;
    field: string;
    lsn: number;
    before_value: unknown;
    current_value: unknown;
    after_value: unknown;
  }>;
  duplicates: Array<{ event_id: string; lsn: number; pk: string; kept_from: string | null }>;
  rejected: Array<{ event_id: string; lsn: number; pk: string | null; reason: string; detail: string }>;
  amount_audit: { checked: number; mismatched: number; items: AmountAuditItem[] };
  digest: string;
  idempotent?: boolean;
  executed_by?: string;
}

export interface MergeRun {
  id: string;
  stream_id: string;
  stream_name: string | null;
  window_start_lsn: number;
  window_end_lsn: number;
  window_display: string;
  status: RunStatus;
  status_label: string;
  received_count: number;
  processed_count: number;
  duplicate_count: number;
  rejected_count: number;
  inserted_count: number;
  updated_count: number;
  deleted_count: number;
  upserted_count: number;
  watermark_before: number;
  watermark_after: number;
  watermark_after_display: string;
  duration_ms: number;
  result_digest: string | null;
  error_message: string | null;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  idempotent?: boolean;
  result?: MergeResult | null;
}

export interface SchemaField {
  name: string;
  type: string;
  nullable: boolean;
  default: unknown;
  is_pk: boolean;
}

export interface SchemaVersion {
  id: string;
  stream_id: string;
  version_label: string;
  fields: SchemaField[];
  field_count: number;
  ddl_summary: string;
  created_by: string;
  created_at: string;
}

export interface SchemaChange {
  kind: string;
  kind_label: string;
  column: string;
  old: SchemaField | null;
  new: SchemaField | null;
  compat: CompatLevel;
  forward_sql?: string[];
  precheck_sql?: string[];
  rollback_sql?: string[];
  note?: string;
}

export interface SchemaDiff {
  left: { version: string; field_count: number; pk_columns: string[] };
  right: { version: string; field_count: number; pk_columns: string[] };
  changes: SchemaChange[];
  counts: Record<string, number>;
  compat_level: CompatLevel;
  breaking_count: number;
  affected_columns: string[];
  migration_sql: string;
  rollback_sql: string;
  deploy_steps: string[];
  digest: string;
  left_version: SchemaVersion;
  right_version: SchemaVersion;
  stream: { id: string; name: string; source_table: string };
  target_table: string;
}

export interface RejectedEvent {
  id: string;
  event_id: string | null;
  run_id: string | null;
  stream_id: string;
  stream_name: string | null;
  lsn: number;
  lsn_display: string;
  reason: RejectReason;
  reason_label: string;
  detail: string;
  payload: Record<string, unknown> | null;
  status: RejectStatus;
  status_label: string;
  replayed_event_id: string | null;
  created_at: string | null;
  resolved_at: string | null;
}

export interface ReplayResult {
  rejected: RejectedEvent;
  new_event_id: string;
  repair_note: string;
  schema_version: string | null;
}

export interface AuditLog {
  id: string;
  action: string;
  actor_id: string | null;
  actor_kind: string;
  entity_type: string;
  entity_id: string | null;
  payload: Record<string, unknown>;
  ip: string | null;
  trace_id: string | null;
  created_at: string | null;
}
