/** 前端枚举第二份：与 backend/src/constants/enums.py 一一对应（README 有对照表）。 */
import type { CdcOp, CompatLevel, RejectReason, RejectStatus, Role, RunStatus, StreamStatus } from '../types/models';

export const STREAM_STATUS: Record<StreamStatus, { label: string; tone: 'ok' | 'warn' | 'muted' | 'danger' }> = {
  healthy: { label: '正常', tone: 'ok' },
  lagging: { label: '延迟', tone: 'warn' },
  paused: { label: '已暂停', tone: 'muted' },
  error: { label: '异常', tone: 'danger' },
};

export const RUN_STATUS: Record<RunStatus, { label: string; tone: 'ok' | 'amber' | 'danger' | 'muted'; running?: boolean }> = {
  queued: { label: '排队中', tone: 'amber', running: true },
  running: { label: '归并中', tone: 'amber', running: true },
  succeeded: { label: '成功', tone: 'ok' },
  failed: { label: '失败', tone: 'danger' },
  canceled: { label: '已取消', tone: 'muted' },
};

export const CDC_OP: Record<CdcOp, { label: string; tone: 'ok' | 'amber' | 'danger' }> = {
  insert: { label: '新增', tone: 'ok' },
  update: { label: '更新', tone: 'amber' },
  delete: { label: '删除', tone: 'danger' },
};

export const REJECT_REASON: Record<RejectReason, { label: string; tone: 'danger' | 'warn' | 'amber' }> = {
  schema_mismatch: { label: 'schema 不匹配', tone: 'warn' },
  pk_missing: { label: '主键缺失', tone: 'danger' },
  parse_error: { label: '载荷解析失败', tone: 'amber' },
  type_conflict: { label: '类型冲突', tone: 'danger' },
};

export const REJECT_STATUS: Record<RejectStatus, { label: string; tone: 'ok' | 'amber' | 'muted' }> = {
  pending: { label: '待处理', tone: 'amber' },
  replayed: { label: '已重放', tone: 'ok' },
  dismissed: { label: '已忽略', tone: 'muted' },
};

export const COMPAT_LEVEL: Record<CompatLevel, { label: string; tone: 'ok' | 'amber' | 'forward' | 'danger'; hint: string }> = {
  full: { label: '完全兼容', tone: 'ok', hint: '两个版本字段一致，无迁移动作' },
  backward: { label: '向后兼容', tone: 'ok', hint: '新 schema 能读旧数据，可直接发布' },
  forward: { label: '向前兼容', tone: 'forward', hint: '旧 schema 能读新数据，需下游先升级' },
  breaking: { label: '破坏性变更', tone: 'danger', hint: '两个方向都不成立，必须双写/回填/切读' },
};

export const CHANGE_KIND_TONE: Record<string, 'ok' | 'danger' | 'forward'> = {
  add_nullable: 'ok',
  add_required: 'danger',
  add_required_with_default: 'ok',
  drop_column: 'danger',
  type_widen: 'ok',
  type_narrow: 'danger',
  type_incompatible: 'danger',
  nullability_to_required: 'danger',
  nullability_to_nullable: 'ok',
  pk_change: 'danger',
};

export const ROLE_LABEL: Record<Role, string> = {
  admin: '平台管理员',
  engineer: '数据工程师',
  viewer: '分析师',
};
