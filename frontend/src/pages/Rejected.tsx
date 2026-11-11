import { useCallback, useEffect, useState } from 'react';
import { rejectedApi } from '../api/rejected';
import { EmptyState } from '../components/common/EmptyState';
import { PanelHead } from '../components/common/PanelHead';
import { StatusPill } from '../components/common/StatusPill';
import { REJECT_REASON, REJECT_STATUS } from '../constants/cdc';
import { useAuthStore } from '../stores/authStore';
import { useStreamStore } from '../stores/streamStore';
import type { RejectedEvent } from '../types/models';
import { errorMessage } from '../utils/errorMessage';
import { displayValue, formatLsn, formatShortTime } from '../utils/format';

const STATUS_TABS: Array<{ value: string; label: string }> = [
  { value: 'pending', label: '待处理' },
  { value: 'replayed', label: '已重放' },
  { value: 'dismissed', label: '已忽略' },
  { value: '', label: '全部' },
];

/** 拒绝事件与重放：重放会按原因做真实载荷修复（补默认值/清理数字/类型转换）。 */
export const RejectedPage = () => {
  const board = useStreamStore((state) => state.board);
  const canReplay = useAuthStore((state) => state.can('rejected:replay'));
  const [status, setStatus] = useState('pending');
  const [streamId, setStreamId] = useState('');
  const [items, setItems] = useState<RejectedEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await rejectedApi.list({ status, stream_id: streamId, limit: 100 });
      setItems(response.items);
      setTotal(response.total);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [status, streamId]);

  useEffect(() => {
    void load();
  }, [load]);

  const replay = async (item: RejectedEvent) => {
    setBusyId(item.id);
    setError(null);
    setNote(null);
    try {
      const result = await rejectedApi.replay(item.id);
      setNote(
        `重放成功：新事件 ${result.new_event_id.slice(0, 8)}，基于 schema ${result.schema_version ?? '—'}；修复说明：${result.repair_note}`,
      );
      await load();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusyId(null);
    }
  };

  const dismiss = async (item: RejectedEvent) => {
    setBusyId(item.id);
    try {
      await rejectedApi.dismiss(item.id);
      await load();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div>
      <PanelHead
        title="拒绝与重放"
        sub="拒绝原因决定修复策略：类型冲突/解析失败清理数字，schema 不匹配补默认值，主键缺失不可自动重放"
        actions={
          <select className="select" value={streamId} onChange={(event) => setStreamId(event.target.value)}>
            <option value="">全部流</option>
            {(board?.streams ?? []).map((stream) => (
              <option key={stream.id} value={stream.id}>
                {stream.name}
              </option>
            ))}
          </select>
        }
      />

      <div className="chip-row" style={{ marginBottom: 12 }}>
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.value}
            className={`chip${status === tab.value ? ' on' : ''}`}
            onClick={() => setStatus(tab.value)}
          >
            {tab.label}
          </button>
        ))}
        <span className="tiny faint" style={{ marginLeft: 'auto' }}>
          共 <span className="mono">{total}</span> 条 · 当前角色 {canReplay ? '可重放' : '只读'}
        </span>
      </div>

      {note ? <div className="notice ok" style={{ marginBottom: 12 }}>{note}</div> : null}
      {error ? <div className="notice danger" style={{ marginBottom: 12 }}>{error}</div> : null}

      {items.length === 0 && !loading ? (
        <EmptyState
          title={status === 'pending' ? '没有待处理的拒绝事件' : '当前筛选下没有记录'}
          hint="拒绝事件来自归并运行：payload 解析失败、类型冲突、schema 不匹配或主键缺失都会被截留在这里，不会污染目标表。"
        />
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th className="num">LSN</th>
              <th>流</th>
              <th>原因</th>
              <th>状态</th>
              <th>说明</th>
              <th>载荷快照</th>
              <th>时间</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {items.map((item, index) => (
              <tr key={item.id} className="stagger" style={{ animationDelay: `${index * 20}ms` }}>
                <td className="num">{formatLsn(item.lsn)}</td>
                <td className="mono tiny">{item.stream_name ?? item.stream_id.slice(0, 8)}</td>
                <td>
                  <StatusPill
                    label={REJECT_REASON[item.reason]?.label ?? item.reason}
                    tone={REJECT_REASON[item.reason]?.tone ?? 'danger'}
                  />
                </td>
                <td>
                  <StatusPill
                    label={REJECT_STATUS[item.status]?.label ?? item.status}
                    tone={REJECT_STATUS[item.status]?.tone ?? 'muted'}
                  />
                </td>
                <td className="tiny" style={{ maxWidth: 320 }}>{item.detail}</td>
                <td className="mono tiny faint" style={{ maxWidth: 300, wordBreak: 'break-all' }}>
                  {displayValue(item.payload?.after ?? item.payload, 90)}
                </td>
                <td className="tiny faint">{formatShortTime(item.created_at)}</td>
                <td style={{ whiteSpace: 'nowrap' }}>
                  {item.status === 'pending' && canReplay ? (
                    <>
                      <button
                        className="btn small"
                        disabled={busyId === item.id}
                        onClick={() => void replay(item)}
                      >
                        {busyId === item.id ? '重放中' : '重放'}
                      </button>{' '}
                      <button
                        className="btn small danger"
                        disabled={busyId === item.id}
                        onClick={() => void dismiss(item)}
                      >
                        忽略
                      </button>
                    </>
                  ) : item.status === 'pending' ? (
                    <span className="tiny faint">需 engineer/admin</span>
                  ) : (
                    <span className="tiny faint mono">{item.replayed_event_id?.slice(0, 8) ?? '—'}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
};
