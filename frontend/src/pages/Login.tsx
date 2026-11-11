import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';
import { errorMessage } from '../utils/errorMessage';

/** 登录页：左侧值班台说明（真实客户背景）+ 右侧表单。 */
export const LoginPage = () => {
  const login = useAuthStore((state) => state.login);
  const [email, setEmail] = useState('admin@cdc.local');
  const [password, setPassword] = useState('Demo@2026');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email.trim(), password);
      navigate('/streams', { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login">
      <section className="login-brandside">
        <div>
          <span className="login-eyebrow">北岸生活 · 数据平台组 · 值班席位</span>
          <h1 className="login-title">
            增量合并
            <br />
            与 schema 演进
          </h1>
          <p className="login-lede">
            上游 MySQL binlog 经 CDC 投递到 Kafka，再进数仓。这里负责事件落账、乱序去重归并、
            schema 兼容判定与迁移 SQL 生成。夜间窗口不再等人工对账，白天也能查到增量。
          </p>
        </div>
        <div className="login-facts">
          <span>
            <b>日订单</b> 400,000 · 峰值 62 条/秒
          </span>
          <span>
            <b>当前流</b> orders（交易主表）· customers（会员维表）
          </span>
          <span>
            <b>昨日常见故障</b> 重复投递 3 次 · 乱序 2 次 · schema 漂移 1 次
          </span>
          <span>
            <b>账号</b> admin / engineer / viewer，口令 Demo@2026
          </span>
        </div>
      </section>

      <section className="login-formside">
        <form className="login-form" onSubmit={submit}>
          <div>
            <span className="login-eyebrow">值班登录</span>
            <h2>进入管制台</h2>
          </div>

          <label className="field">
            <span className="field-label">邮箱</span>
            <input
              className="input"
              type="email"
              value={email}
              autoComplete="username"
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>

          <label className="field">
            <span className="field-label">口令</span>
            <input
              className="input"
              type="password"
              value={password}
              autoComplete="current-password"
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>

          {error ? <div className="notice danger">{error}</div> : null}

          <button className="btn primary" type="submit" disabled={busy}>
            {busy ? '校验中…' : '登录'}
          </button>

          <p className="login-hint">
            演示账号：
            <br />
            admin@cdc.local（管理员，可建流/改水位线）
            <br />
            eng@cdc.local（工程师，可发起归并/重放）
            <br />
            viewer@cdc.local（分析师，只读，发起运行返回 403）
          </p>
        </form>
      </section>
    </div>
  );
};
