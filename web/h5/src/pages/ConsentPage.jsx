import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useRider } from '../state/RiderContext.jsx';
import { useToast } from '../components/Toast.jsx';
import { CONSENT_DOC, CONSENT_VERSION, HOTLINE } from '../mock/data.js';
import { formatDateTime } from '../lib/format.js';

export default function ConsentPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const { hasConsent, consent, acceptConsent } = useRider();
  const [checked, setChecked] = useState(false);
  const [declined, setDeclined] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const agree = async () => {
    if (!checked || submitting) return;
    setSubmitting(true);
    try {
      await acceptConsent();
      toast('已记录同意（含版本与时间戳），开始登记');
      navigate('/chat', { replace: true });
    } catch (err) {
      toast(`提交失败：${err.message || '请稍后重试'}`);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="consent-page">
      <section className="card">
        <div className="consent-head">
          <h2 className="section-title">
            个人信息收集告知书
            <span className="version-tag">{CONSENT_DOC.version}</span>
          </h2>
          <p className="muted small">
            生效日期 {CONSENT_DOC.effective_date}　请完整阅读后决定是否同意
          </p>
        </div>

        <section className="consent-block">
          <h3>收集哪些信息</h3>
          <ul>
            {CONSENT_DOC.collect.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>

        <section className="consent-block">
          <h3>不收集哪些信息</h3>
          <ul className="avoid">
            {CONSENT_DOC.not_collect.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>

        <section className="consent-block">
          <h3>用途</h3>
          <ul>
            {CONSENT_DOC.purposes.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>

        <section className="consent-block">
          <h3>保存期限</h3>
          <p>{CONSENT_DOC.retention}</p>
        </section>

        <section className="consent-block">
          <h3>你的权利</h3>
          <ul>
            {CONSENT_DOC.rights.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>

        <p className="ai-disclaimer">{CONSENT_DOC.ai_note}</p>
      </section>

      {hasConsent ? (
        <section className="card">
          <p className="ok-line">
            你已于 {formatDateTime(consent.consent_at)} 同意《{CONSENT_DOC.title}{' '}
            {consent.consent_version || CONSENT_VERSION}》。
          </p>
          <button type="button" className="btn primary block" onClick={() => navigate('/chat')}>
            继续我的登记
          </button>
          <button type="button" className="btn ghost block" onClick={() => navigate('/me')}>
            前往「我的信息」撤回授权并删除
          </button>
        </section>
      ) : (
        <section className="card">
          <label className="consent-check">
            <input
              type="checkbox"
              checked={checked}
              onChange={(e) => setChecked(e.target.checked)}
              aria-describedby="consent-check-hint"
            />
            <span>
              我已阅读并同意《{CONSENT_DOC.title} {CONSENT_DOC.version}》，同意平台按上述范围收集与使用我的个人信息。
            </span>
          </label>
          <p id="consent-check-hint" className="muted small">
            不勾选同意将无法开始信息登记；你可以先电话咨询再决定。
          </p>

          <button
            type="button"
            className="btn primary block"
            disabled={!checked || submitting}
            onClick={agree}
          >
            {submitting ? '提交中…' : checked ? '同意并开始登记' : '请先勾选同意'}
          </button>

          <button
            type="button"
            className="btn ghost block"
            onClick={() => setDeclined((v) => !v)}
          >
            {declined ? '收起' : '我不同意'}
          </button>

          {declined ? (
            <div className="decline-panel" role="region" aria-label="不同意后的可选出口">
              <p>
                不同意不会影响你电话咨询。你可以拨打招聘热线，由人工解答后再决定是否登记；本次不会收集你的任何信息。
              </p>
              <a className="btn primary block" href={`tel:${HOTLINE.replace(/-/g, '')}`}>
                电话咨询 {HOTLINE}
              </a>
              <button type="button" className="btn ghost block" onClick={() => navigate('/')}>
                返回首页（不登记）
              </button>
            </div>
          ) : null}
        </section>
      )}
    </div>
  );
}
