import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useRider } from '../state/RiderContext.jsx';
import { useToast } from '../components/Toast.jsx';
import { CONSENT_DOC, CANDIDATE_FIELDS, HOTLINE } from '../mock/data.js';
import { KEYS, load } from '../lib/storage.js';
import { API_MODE } from '../api/client.js';

const CHANNEL_LABEL = {
  wechat: '微信好友分享',
  moments: '朋友圈广告',
  douyin: '抖音短视频',
  offline_poster: '线下海报',
  referral: '老骑手推荐',
  direct: '直接访问',
};

export default function EntryPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const { channel, hasConsent, consent, resetLocal } = useRider();
  const [busy, setBusy] = useState(false);
  const lastBookingId = load(KEYS.booking, null);

  const start = () => {
    navigate(hasConsent ? '/chat' : '/consent');
  };

  const restart = () => {
    setBusy(true);
    resetLocal();
    toast('本地登记缓存已清空，可以重新开始');
    setBusy(false);
  };

  return (
    <div className="entry">
      <section className="hero">
        <span className="hero-badge">AI 招聘助手 · 7 项信息 · 约 2 分钟</span>
        <h2 className="hero-title">骑手求职登记</h2>
        <p className="hero-sub">
          和 AI 助手聊几句，完成信息登记、了解岗位政策、预约附近站点面试。
        </p>
        <div className="hero-channel">
          渠道来源：
          <b>{CHANNEL_LABEL[channel] || channel}</b>
          <code className="channel-code">?source_channel={channel}</code>
        </div>
        <button type="button" className="btn primary block" onClick={start} disabled={busy}>
          {hasConsent ? '继续我的登记' : '开始登记'}
        </button>
        {hasConsent ? (
          <div className="entry-actions">
            <button type="button" className="btn ghost" onClick={restart} disabled={busy}>
              重新开始（清空本地缓存）
            </button>
            {lastBookingId ? (
              <button type="button" className="btn ghost" onClick={() => navigate(`/result/${lastBookingId}`)}>
                查看我的预约
              </button>
            ) : null}
          </div>
        ) : null}
        {consent ? (
          <p className="entry-consent">
            已同意《{CONSENT_DOC.title} {consent.consent_version || CONSENT_DOC.version}》·
            同意时间 {String(consent.consent_at || '').slice(0, 16).replace('T', ' ')}
          </p>
        ) : null}
      </section>

      <section className="card">
        <h3 className="section-title">我们会做什么</h3>
        <ol className="flow-list">
          <li>
            <b>告知同意</b>：一屏说明收集什么、不收集什么、用途与保存期限
          </li>
          <li>
            <b>对话登记</b>：AI 逐项收集 7 个字段，可随时转人工
          </li>
          <li>
            <b>岗位政策</b>：回答保险、结算、入职流程，均标注政策出处
          </li>
          <li>
            <b>推荐站点</b>：按距离与在招人数推荐站点，选时段直接预约
          </li>
        </ol>
      </section>

      <section className="card">
        <h3 className="section-title">只收集这 7 项</h3>
        <div className="field-chips">
          {CANDIDATE_FIELDS.map((field) => (
            <span className="chip" key={field.key}>
              {field.label}
            </span>
          ))}
        </div>
        <p className="muted small">
          不采集身份证号、银行卡号、人脸等生物识别信息，也不采集精确位置轨迹。详见告知同意页。
        </p>
      </section>

      <section className="card">
        <h3 className="section-title">需要人工帮助？</h3>
        <p className="muted">招聘热线（工作日 9:00-18:00）</p>
        <a className="btn ghost block" href={`tel:${HOTLINE.replace(/-/g, '')}`}>
          拨打 {HOTLINE}
        </a>
      </section>

      {API_MODE === 'mock' ? (
        <p className="muted small center">
          当前为内置 mock 模式（未设置 VITE_API_BASE），可直接走完主流程。
        </p>
      ) : null}
    </div>
  );
}
