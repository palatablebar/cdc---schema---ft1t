import { useCallback, useEffect, useState } from 'react';
import { schemaApi, type VersionsResponse } from '../api/schema';
import { DiffTable, type DiffRow } from '../components/common/DiffTable';
import { EmptyState } from '../components/common/EmptyState';
import { MetricStrip } from '../components/common/MetricStrip';
import { PanelHead } from '../components/common/PanelHead';
import { StatusPill } from '../components/common/StatusPill';
import { CHANGE_KIND_TONE, COMPAT_LEVEL } from '../constants/cdc';
import { useStreamStore } from '../stores/streamStore';
import type { SchemaDiff as SchemaDiffType } from '../types/models';
import { errorMessage } from '../utils/errorMessage';
import { fieldTypeText } from '../utils/schemaText';

const SqlBlock = ({ sql, label }: { sql: string; label: string }) => {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(sql);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  };
  return (
    <div className="panel">
      <div className="panel-head-sm">
        {label}
        <button className="btn small copy-btn" onClick={() => void copy()}>
          {copied ? '已复制' : '复制'}
        </button>
      </div>
      <pre className="sql-block">{sql}</pre>
    </div>
  );
};

/** schema 演进：字段级 diff + 兼容等级 + 迁移/回滚 SQL（全部后端算）。 */
export const SchemaDiffPage = () => {
  const board = useStreamStore((state) => state.board);
  const selectedStreamId = useStreamStore((state) => state.selectedStreamId);
  const selectStream = useStreamStore((state) => state.selectStream);

  const [versions, setVersions] = useState<VersionsResponse | null>(null);
  const [leftId, setLeftId] = useState('');
  const [rightId, setRightId] = useState('');
  const [diff, setDiff] = useState<SchemaDiffType | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const stream = board?.streams.find((item) => item.id === selectedStreamId) ?? board?.streams[0] ?? null;

  useEffect(() => {
    if (!stream) return;
    schemaApi
      .versions(stream.id)
      .then((response) => {
        setVersions(response);
        const pair = response.pairs[0];
        if (pair) {
          setLeftId(pair.left_version_id);
          setRightId(pair.right_version_id);
        } else if (response.items.length) {
          setLeftId(response.items[0].id);
          setRightId(response.items[response.items.length - 1].id);
        }
      })
      .catch((err) => setError(errorMessage(err)));
  }, [stream?.id]);

  const compare = useCallback(async () => {
    if (!leftId || !rightId) return;
    setLoading(true);
    setError(null);
    try {
      setDiff(await schemaApi.diff(leftId, rightId));
    } catch (err) {
      setDiff(null);
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [leftId, rightId]);

  useEffect(() => {
    if (leftId && rightId) void compare();
  }, [leftId, rightId, compare]);

  const changeRows: DiffRow[] = diff
    ? diff.changes.map((change) => ({
        field: change.column,
        before: change.old ? fieldTypeText(change.old) : '（不存在）',
        after: change.new ? fieldTypeText(change.new) : '（删除）',
        kind: change.kind_label,
      }))
    : [];

  const level = diff ? COMPAT_LEVEL[diff.compat_level] : null;

  return (
    <div>
      <PanelHead
        title="schema 演进"
        sub={
          stream
            ? `${stream.name} · 目标表 ${diff?.target_table ?? `dw.${stream.name}_dw`} · 版本 ${versions?.total ?? 0} 个`
            : '选择变更流'
        }
        actions={
          <select className="select" value={stream?.id ?? ''} onChange={(event) => selectStream(event.target.value)}>
            {(board?.streams ?? []).map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        }
      />

      <div className="panel" style={{ marginBottom: 16 }}>
        <div className="panel-body">
          <div className="form-row">
            <label className="field">
              <span className="field-label">旧版本</span>
              <select className="select" value={leftId} onChange={(event) => setLeftId(event.target.value)} style={{ minWidth: 200 }}>
                {(versions?.items ?? []).map((version) => (
                  <option key={version.id} value={version.id}>
                    {version.version_label}（{version.field_count} 列）
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span className="field-label">新版本</span>
              <select className="select" value={rightId} onChange={(event) => setRightId(event.target.value)} style={{ minWidth: 200 }}>
                {(versions?.items ?? []).map((version) => (
                  <option key={version.id} value={version.id}>
                    {version.version_label}（{version.field_count} 列）
                  </option>
                ))}
              </select>
            </label>
            <button className="btn primary" onClick={() => void compare()} disabled={loading || !leftId || !rightId}>
              {loading ? '判定中…' : '重新判定'}
            </button>
            {versions?.pairs.length ? (
              <span className="tiny faint" style={{ marginLeft: 'auto' }}>
                默认比较对：{versions.pairs[0].label}
              </span>
            ) : null}
          </div>
        </div>
      </div>

      {error ? <div className="notice danger" style={{ marginBottom: 12 }}>{error}</div> : null}

      {!diff ? (
        <EmptyState
          title="还没有可比对的版本"
          hint="一条流至少需要两个 SchemaVersion（例如 v1 → v2）。seed 数据里 orders 流已经有 v1/v2。"
        />
      ) : (
        <>
          <div data-testid="compat-level">
          <MetricStrip
            items={[
              {
                label: '兼容等级',
                value: level?.label ?? diff.compat_level,
                tone: diff.compat_level === 'breaking' ? 'danger' : diff.compat_level === 'full' ? 'ok' : 'amber',
                note: level?.hint,
              },
              { label: '变更条目', value: String(diff.changes.length), note: `${diff.breaking_count} 条破坏性` },
              { label: '受影响列', value: String(diff.affected_columns.length), note: diff.affected_columns.join(', ') || '—' },
              { label: '版本', value: `${diff.left.version} → ${diff.right.version}`, note: `字段 ${diff.left.field_count} → ${diff.right.field_count}` },
            ]}
          />
          </div>

          <div className="section">
            <div className="section-label">
              <span>字段级变更</span>
            </div>
            {diff.changes.length === 0 ? (
              <EmptyState title="两个版本字段完全一致" hint="没有需要生成的迁移 SQL。" />
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th>列</th>
                    <th>变更类别</th>
                    <th>旧定义</th>
                    <th>新定义</th>
                    <th>兼容方向</th>
                    <th>说明</th>
                  </tr>
                </thead>
                <tbody>
                  {diff.changes.map((change, index) => (
                    <tr key={`${change.kind}-${change.column}-${index}`} className="stagger" style={{ animationDelay: `${index * 22}ms` }}>
                      <td className="mono">{change.column}</td>
                      <td>
                        <StatusPill
                          label={change.kind_label}
                          tone={CHANGE_KIND_TONE[change.kind] ?? 'danger'}
                          title={change.kind}
                        />
                      </td>
                      <td className="tiny mono faint">{change.old ? fieldTypeText(change.old) : '（不存在）'}</td>
                      <td className="tiny mono">{change.new ? fieldTypeText(change.new) : '（删除）'}</td>
                      <td>
                        <StatusPill
                          label={COMPAT_LEVEL[change.compat].label}
                          tone={COMPAT_LEVEL[change.compat].tone}
                        />
                      </td>
                      <td className="tiny muted">{change.note}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="section">
            <div className="section-label">
              <span>迁移与回滚脚本</span>
            </div>
            <div className="split-even">
              <SqlBlock sql={diff.migration_sql} label="前滚迁移 SQL" />
              <SqlBlock sql={diff.rollback_sql} label="回滚 SQL" />
            </div>
          </div>

          <div className="section">
            <div className="section-label">
              <span>字段对照（diff 渲染）</span>
            </div>
            <DiffTable rows={changeRows} beforeLabel={`${diff.left.version} 定义`} afterLabel={`${diff.right.version} 定义`} />
          </div>

          <div className="section">
            <div className="section-label">
              <span>发布建议</span>
            </div>
            <ol className="tiny muted" style={{ margin: 0, paddingLeft: 18, lineHeight: '22px' }}>
              {diff.deploy_steps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
          </div>

          {diff.changes.some((change) => (change.precheck_sql ?? []).length > 0) ? (
            <div className="section">
              <div className="section-label">
                <span>预检 SQL（结果为 0 才能继续）</span>
              </div>
              <pre className="sql-block">
                {diff.changes
                  .flatMap((change) => change.precheck_sql ?? [])
                  .join('\n')}
              </pre>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
};
