import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { slotLabel } from '../lib/format.js';
import { useRider } from '../state/RiderContext.jsx';

export function Loading({ text = '加载中…' }) {
  return (
    <div className="loading-block" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span>{text}</span>
    </div>
  );
}

export function ErrorBlock({ message, onRetry }) {
  return (
    <div className="error-block" role="alert">
      <p>{message || '加载失败，请稍后重试'}</p>
      {onRetry ? (
        <button type="button" className="btn ghost" onClick={onRetry}>
          重试
        </button>
      ) : null}
    </div>
  );
}

export function Pill({ children, tone = 'default' }) {
  return <span className={`pill pill-${tone}`}>{children}</span>;
}

/** 对话进度：x/7 + 已收集字段 chips。fields 兼容对象数组与字符串数组。 */
export function ProgressPanel({ progress }) {
  if (!progress) return null;
  const fields = (progress.fields || []).map((f) =>
    typeof f === 'string' ? { key: f, label: f, collected: true } : f,
  );
  const total = progress.total || fields.length || 7;
  const done = progress.done != null ? progress.done : fields.filter((f) => f.collected).length;
  const pct = Math.min(100, Math.round((done / total) * 100));
  return (
    <section className="progress-card" aria-label="信息收集进度">
      <div className="progress-head">
        <span>信息收集进度</span>
        <strong>
          {done}/{total}
        </strong>
      </div>
      <div
        className="progress-track"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={done}
      >
        <i style={{ width: `${pct}%` }} />
      </div>
      <div className="field-chips">
        {fields.map((f) => (
          <span key={f.key} className={f.collected ? 'chip done' : 'chip'}>
            {f.label}
            {f.collected ? ' ✓' : ''}
          </span>
        ))}
      </div>
    </section>
  );
}

/** 政策回答卡：必须展示出处（文档名 + 版本）+ 免责声明。 */
export function PolicyCard({ card, sourceLabel }) {
  if (!card) return null;
  return (
    <div className="policy-card">
      <div className="policy-title">
        <span className="policy-tag">政策回答</span>
        {card.title}
        <span className="policy-version">{card.version}</span>
      </div>
      <p className="policy-answer">{card.answer}</p>
      <div className="policy-source">
        出处：{card.title} {card.version}
        {card.effective_date ? `（生效日期 ${card.effective_date}）` : ''}
        {sourceLabel && !String(sourceLabel).includes(card.title) ? `｜${sourceLabel}` : ''}
      </div>
      <div className="policy-disclaimer">
        免责声明：{card.disclaimer || '以上为政策摘要，具体以正式文件与承保/用工条款为准。'}
      </div>
    </div>
  );
}

/** 站点推荐卡：距离、在招人数、可约时段 → 选时段 → 预约。 */
export function StationCard({ station, onBook, busy }) {
  const [selected, setSelected] = useState('');
  const availableSlots = (station.slots || []).filter((s) => s.available).slice(0, 3);
  const isFull = availableSlots.length === 0;

  return (
    <div className="station-card">
      <div className="station-head">
        <strong>{station.name}</strong>
        <span className="station-distance">{station.distance_km} km</span>
      </div>
      <p className="station-address">{station.address}</p>
      <div className="station-meta">
        <span>
          在招 <b>{station.open_quota}</b> 人
        </span>
        <span>已约 {station.booked_count != null ? station.booked_count : 0} 人</span>
      </div>
      {isFull ? (
        <p className="station-full">本站在招名额/可约时段已满，建议选择其他站点</p>
      ) : (
        <>
          <div className="slot-list" role="group" aria-label="可约时段">
            {availableSlots.map((slot) => (
              <button
                type="button"
                key={slot.slot_start}
                className={selected === slot.slot_start ? 'slot selected' : 'slot'}
                onClick={() => setSelected(slot.slot_start)}
              >
                <span className="slot-time">{slotLabel(slot.slot_start)}</span>
                <span className="slot-left">余 {slot.capacity - slot.booked} 个名额</span>
              </button>
            ))}
          </div>
          <button
            type="button"
            className="btn primary block"
            disabled={!selected || busy}
            onClick={() => onBook(station, selected)}
          >
            {busy ? '预约提交中…' : selected ? '预约这个时段' : '请先选择时段'}
          </button>
        </>
      )}
    </div>
  );
}

/** 每一屏都可见的 AI 身份标识（全局 Layout 中只渲染一次）。 */
export function AiFooter() {
  const navigate = useNavigate();
  const { hasConsent } = useRider();
  const ref = useRef(null);

  // 把页脚实测高度写进 CSS 变量：字体放大 150% 导致换行时，输入框仍能准确贴在页脚上方。
  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const apply = () => {
      const height = Math.round(el.getBoundingClientRect().height);
      document.documentElement.style.setProperty('--footer-h', `${height}px`);
    };
    apply();
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', apply);
      return () => window.removeEventListener('resize', apply);
    }
    const observer = new ResizeObserver(apply);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <footer className="ai-footer" ref={ref} role="note" aria-label="AI 身份标识">
      <span className="ai-dot" aria-hidden="true">
        AI
      </span>
      <span className="ai-text">本服务由 AI 提供 · 可随时转人工</span>
      <button
        type="button"
        className="ai-action"
        onClick={() => navigate(hasConsent ? '/chat?handoff=1' : '/consent')}
      >
        转人工
      </button>
    </footer>
  );
}

export function NetBanner({ offline, queued, replaying }) {
  if (!offline && !queued && !replaying) return null;
  let text;
  if (replaying) text = '网络已恢复，正在重发排队消息…';
  else if (offline) text = '网络已断开：消息会先排队，恢复后自动重发，会话与进度不会丢';
  else text = `有 ${queued} 条消息待发送，正在自动重试…`;
  return (
    <div className={offline ? 'net-banner offline' : 'net-banner online'} role="status" aria-live="polite">
      {text}
    </div>
  );
}

/** 受控确认弹窗（H5 端不引入组件库，保持轻量）。 */
export function Dialog({
  open,
  title,
  children,
  onCancel,
  onOk,
  okText = '确定',
  cancelText = '取消',
  danger = false,
  confirmLoading = false,
}) {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') onCancel && onCancel();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onCancel]);

  if (!open) return null;
  return (
    <div className="dialog-mask" role="presentation" onClick={onCancel}>
      <div
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="dialog-title">{title}</h3>
        <div className="dialog-body">{children}</div>
        <div className="dialog-actions">
          <button type="button" className="btn ghost" onClick={onCancel} disabled={confirmLoading}>
            {cancelText}
          </button>
          <button
            type="button"
            className={danger ? 'btn danger' : 'btn primary'}
            onClick={onOk}
            disabled={confirmLoading}
          >
            {confirmLoading ? '处理中…' : okText}
          </button>
        </div>
      </div>
    </div>
  );
}
