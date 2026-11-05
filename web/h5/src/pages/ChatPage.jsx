import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import * as api from '../api/client.js';
import { API_MODE, isOffline, setSimulatedOffline } from '../api/client.js';
import { useRider } from '../state/RiderContext.jsx';
import { useToast } from '../components/Toast.jsx';
import { useNetworkStatus } from '../lib/network.js';
import { KEYS, load, save, uid } from '../lib/storage.js';
import { ErrorBlock, Loading, PolicyCard, ProgressPanel, StationCard } from '../components/ui.jsx';
import { resetMockDb } from '../mock/index.js';
import { HOTLINE } from '../mock/data.js';

const FALLBACK_GREETING = {
  text:
    '你好，我是骑手招募助手，可以帮你了解岗位、推荐附近站点并预约面试。\n' +
    '本次登记共 7 项信息，大约 2 分钟；你随时可以要求转人工。\n' +
    '先问一下，怎么称呼你？',
  quick_replies: ['张伟（示例）', '李娜（示例）'],
  progress: {
    done: 0,
    total: 7,
    fields: ['姓名', '手机号', '出生年月', '跑单区域', '工作类型', '是否有电动车', '可到岗时间'].map(
      (label) => ({ key: label, label, collected: false }),
    ),
  },
  actions: [],
};

export default function ChatPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const offline = useNetworkStatus();
  const { candidateId } = useRider();
  const [searchParams, setSearchParams] = useSearchParams();

  const [messages, setMessages] = useState(() => load(KEYS.messages, []));
  const [progress, setProgress] = useState(() => load(KEYS.progress, null));
  const [sessionId, setSessionId] = useState(() => (load(KEYS.session, null) || {}).id || null);
  const [outbox, setOutbox] = useState(() => load(KEYS.outbox, []));
  const [booting, setBooting] = useState(false);
  const [bootError, setBootError] = useState('');
  const [sending, setSending] = useState(false);
  const [replaying, setReplaying] = useState(false);
  const [bookingBusyId, setBookingBusyId] = useState('');
  const [draft, setDraft] = useState('');
  const [countdown, setCountdown] = useState(null);

  const bootRef = useRef(false);
  const flushingRef = useRef(false);
  const outboxRef = useRef(outbox);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    outboxRef.current = outbox;
  }, [outbox]);

  useEffect(() => {
    save(KEYS.messages, messages);
  }, [messages]);
  useEffect(() => {
    if (progress) save(KEYS.progress, progress);
  }, [progress]);
  useEffect(() => {
    save(KEYS.outbox, outbox);
  }, [outbox]);

  useEffect(() => {
    const el = bottomRef.current;
    if (!el) return;
    const t = window.setTimeout(() => {
      try {
        el.scrollIntoView({ behavior: 'smooth', block: 'end' });
      } catch {
        window.scrollTo(0, document.body.scrollHeight);
      }
    }, 60);
    return () => window.clearTimeout(t);
  }, [messages, sending]);

  const appendMessages = useCallback((items) => {
    setMessages((prev) => [...prev, ...items]);
  }, []);

  /** 追加 AI 消息（按 message_id 去重，保证断网重放不会出现重复回复）。 */
  const appendAi = useCallback(
    (res) => {
      if (!res) return;
      const id = res.message_id || uid('m');
      const aiMessage = {
        id,
        role: 'ai',
        text: res.reply,
        quick_replies: res.quick_replies || [],
        actions: res.actions || [],
        policy_card: res.policy_card || null,
        source_label: res.source_label || '',
        stations: res.stations || null,
      };
      setMessages((prev) => (prev.some((m) => m.id === id) ? prev : [...prev, aiMessage]));
      if (res.progress) setProgress(res.progress);
    },
    [],
  );

  const initSession = useCallback(async () => {
    if (!candidateId) return;
    setBooting(true);
    setBootError('');
    try {
      const res = await api.createSession(candidateId);
      setSessionId(res.session_id);
      save(KEYS.session, { id: res.session_id, created_at: Date.now() });
      // 兼容两种后端形态：契约扩展 greeting 字段，或直接把首条问候放在 reply 里。
      const greeting = res.greeting || (res.reply
        ? {
            text: res.reply,
            quick_replies: res.quick_replies || [],
            progress: res.progress || null,
            actions: res.actions || [],
          }
        : FALLBACK_GREETING);
      setMessages([
        {
          id: uid('m'),
          role: 'ai',
          text: greeting.text,
          quick_replies: greeting.quick_replies || [],
          actions: greeting.actions || [],
        },
      ]);
      setProgress(greeting.progress || null);
      save(KEYS.outbox, []);
      setOutbox([]);
    } catch (err) {
      setBootError(err.message || '创建会话失败');
    } finally {
      setBooting(false);
    }
  }, [candidateId]);

  // 首次挂载：已有本地会话与消息就直接恢复（刷新/断网都不丢）；否则新建会话。
  useEffect(() => {
    if (bootRef.current) return;
    bootRef.current = true;
    const savedSession = load(KEYS.session, null);
    const savedMessages = load(KEYS.messages, []);
    if (savedSession && savedSession.id && savedMessages.length > 0) {
      console.info('[chat] 已从本地恢复会话与进度', savedSession.id, savedMessages.length, '条消息');
      return;
    }
    initSession();
  }, [initSession]);

  const flushQueue = useCallback(async () => {
    if (flushingRef.current || !sessionId) return;
    const queue = [...outboxRef.current];
    if (!queue.length) return;
    flushingRef.current = true;
    setReplaying(true);
    try {
      let remaining = queue;
      for (const item of queue) {
        if (isOffline()) break;
        try {
          const res = await api.sendAgentMessage(sessionId, {
            text: item.text,
            clientMessageId: item.id,
          });
          appendAi(res);
          setMessages((prev) =>
            prev.map((m) => (m.id === item.id ? { ...m, pending: false, failed: false } : m)),
          );
          remaining = remaining.filter((x) => x.id !== item.id);
          setOutbox([...remaining]);
        } catch (err) {
          if (err.name === 'NetworkError' || err.code === 'NETWORK_ERROR') break;
          console.warn('[chat] 重放消息失败:', err);
          setMessages((prev) =>
            prev.map((m) => (m.id === item.id ? { ...m, pending: false, failed: true } : m)),
          );
          remaining = remaining.filter((x) => x.id !== item.id);
          setOutbox([...remaining]);
        }
      }
    } finally {
      flushingRef.current = false;
      setReplaying(false);
    }
  }, [appendAi, sessionId]);

  // 网络恢复后自动重发排队的在途消息。
  useEffect(() => {
    if (!offline && !replaying && outbox.length > 0 && sessionId) {
      flushQueue();
    }
  }, [offline, replaying, outbox.length, sessionId, flushQueue]);

  // 演示：模拟断网 10 秒后自动恢复（验证「断网 10 秒恢复，会话与进度不丢」）。
  useEffect(() => {
    if (countdown == null) return undefined;
    if (countdown <= 0) {
      setSimulatedOffline(false);
      setCountdown(null);
      toast('网络已恢复，正在自动重发排队消息');
      return undefined;
    }
    const timer = window.setTimeout(() => setCountdown((c) => (c == null ? null : c - 1)), 1000);
    return () => window.clearTimeout(timer);
  }, [countdown, toast]);

  const enqueue = useCallback((id, text) => {
    setOutbox((prev) => [...prev, { id, text, ts: Date.now() }]);
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, pending: true, failed: false } : m)),
    );
  }, []);

  const submitText = useCallback(
    async (raw) => {
      const text = String(raw || '').trim();
      if (!text || sending || !sessionId) return;
      setDraft('');
      const localId = uid('cm');
      appendMessages([{ id: localId, role: 'user', text, pending: true }]);

      if (isOffline()) {
        enqueue(localId, text);
        toast('当前无网络，消息已排队，恢复后自动发送');
        return;
      }

      setSending(true);
      try {
        const res = await api.sendAgentMessage(sessionId, {
          text,
          clientMessageId: localId,
        });
        setMessages((prev) =>
          prev.map((m) => (m.id === localId ? { ...m, pending: false, failed: false } : m)),
        );
        appendAi(res);
      } catch (err) {
        if (err.name === 'NetworkError' || err.code === 'NETWORK_ERROR') {
          enqueue(localId, text);
          toast('网络中断，消息已排队，恢复后自动重发');
        } else {
          setMessages((prev) =>
            prev.map((m) => (m.id === localId ? { ...m, pending: false, failed: true } : m)),
          );
          appendMessages([
            { id: uid('sys'), role: 'system', text: `消息未送达：${err.message || '服务暂不可用'}` },
          ]);
        }
      } finally {
        setSending(false);
      }
    },
    [appendAi, appendMessages, enqueue, sending, sessionId, toast],
  );

  const book = useCallback(
    async (station, slotStart) => {
      if (!candidateId) return;
      setBookingBusyId(station.id);
      try {
        const booking = await api.createBooking({
          candidate_id: candidateId,
          station_id: station.id,
          slot_start: slotStart,
        });
        save(KEYS.booking, booking.id);
        toast('预约成功');
        navigate(`/result/${booking.id}`);
      } catch (err) {
        toast(err.message || '预约失败，请稍后重试');
      } finally {
        setBookingBusyId('');
      }
    },
    [candidateId, navigate, toast],
  );

  // 从 AI 身份标识的「转人工」跳进来时，自动发送转人工诉求（只触发一次）。
  useEffect(() => {
    const want = searchParams.get('handoff');
    if (!want || !sessionId || booting) return;
    setSearchParams({}, { replace: true });
    submitText('转人工');
  }, [searchParams, sessionId, booting, setSearchParams, submitText]);

  const lastAi = useMemo(() => [...messages].reverse().find((m) => m.role === 'ai'), [messages]);
  const quickReplies = lastAi && lastAi.quick_replies ? lastAi.quick_replies : [];
  const lastActions = (lastAi && lastAi.actions) || [];
  const isMinorEnd = lastActions.includes('end_minor');
  const isHandoff = lastActions.includes('handoff');
  const pendingCount = outbox.length;

  const startOfflineDemo = () => {
    if (!API_MODE || API_MODE !== 'mock') {
      toast('仅 mock 模式提供断网演示');
      return;
    }
    setSimulatedOffline(true);
    setCountdown(10);
    toast('已模拟断网 10 秒，期间发送的消息会进入本地队列');
  };

  if (booting && messages.length === 0) {
    return <Loading text="正在创建 AI 会话…" />;
  }

  if (bootError && messages.length === 0) {
    return (
      <ErrorBlock
        message={`AI 会话创建失败：${bootError}。请检查网络后重试（本地进度不会丢失）。`}
        onRetry={initSession}
      />
    );
  }

  return (
    <div className="chat">
      <ProgressPanel progress={progress} />

      <div className="chat-tools">
        <button type="button" className="tool-btn" onClick={() => submitText('转人工')}>
          转人工
        </button>
        <button type="button" className="tool-btn" onClick={() => submitText('保险怎么算？')}>
          政策问答
        </button>
        <button type="button" className="tool-btn" onClick={() => navigate('/stations')}>
          全部站点
        </button>
      </div>

      <div className="chat-list" role="log" aria-live="polite">
        {messages.map((msg) => (
          <ChatMessage key={msg.id} message={msg} onBook={book} bookingBusyId={bookingBusyId} />
        ))}
        {sending ? (
          <div className="bubble ai typing" aria-label="AI 正在输入">
            <span className="dot" />
            <span className="dot" />
            <span className="dot" />
          </div>
        ) : null}
        <div ref={bottomRef} />
      </div>

      {isMinorEnd ? (
        <div className="chat-closed">
          本次登记已结束（未满 18 周岁无法登记骑手岗位）。如需人工确认，可拨打招聘热线{' '}
          <a href={`tel:${HOTLINE.replace(/-/g, '')}`}>{HOTLINE}</a>。
        </div>
      ) : null}

      {isHandoff && !isMinorEnd ? (
        <div className="chat-closed handoff">
          已转人工：招聘专员将电话联系你。也可直接拨打{' '}
          <a href={`tel:${HOTLINE.replace(/-/g, '')}`}>{HOTLINE}</a>。
        </div>
      ) : null}

      {quickReplies.length > 0 && !isMinorEnd ? (
        <div className="quick-replies" role="group" aria-label="快捷选项">
          {quickReplies.map((q) => (
            <button
              type="button"
              key={q}
              className="chip quick"
              onClick={() => submitText(q)}
              disabled={sending}
            >
              {q}
            </button>
          ))}
        </div>
      ) : null}

      {pendingCount > 0 ? (
        <p className="queue-hint">
          有 {pendingCount} 条消息在本地排队，网络恢复后自动重发（同一消息不会重复入库）。
        </p>
      ) : null}

      <details className="demo-tools">
        <summary>演示工具（断网重放 / 分支流程）</summary>
        <div className="demo-actions">
          <button type="button" className="chip quick" onClick={startOfflineDemo}>
            {countdown != null ? `断网中，${countdown}s 后恢复` : '模拟断网 10 秒'}
          </button>
          <button
            type="button"
            className="chip quick"
            onClick={() => {
              setSimulatedOffline(false);
              setCountdown(null);
              toast('网络已恢复');
            }}
          >
            立即恢复网络
          </button>
          <button
            type="button"
            className="chip quick"
            onClick={() => {
              resetMockDb();
              window.localStorage.clear();
              window.location.hash = '#/';
              window.location.reload();
            }}
          >
            重置演示数据
          </button>
          <button type="button" className="chip quick" onClick={() => submitText('我今年 16 岁')}>
            未成年分支
          </button>
        </div>
      </details>

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          submitText(draft);
        }}
      >
        <input
          ref={inputRef}
          className="composer-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={isMinorEnd ? '本次登记已结束' : '输入消息，或点上方快捷选项'}
          aria-label="输入消息"
          disabled={isMinorEnd}
        />
        <button
          type="submit"
          className="btn primary composer-send"
          disabled={!draft.trim() || sending || isMinorEnd}
        >
          {sending ? '发送中' : '发送'}
        </button>
      </form>
    </div>
  );
}

function ChatMessage({ message, onBook, bookingBusyId }) {
  if (message.role === 'system') {
    return <div className="system-msg">{message.text}</div>;
  }
  const isUser = message.role === 'user';
  return (
    <div className={isUser ? 'bubble-wrap user' : 'bubble-wrap ai'}>
      {!isUser ? (
        <span className="avatar ai" aria-label="AI">
          AI
        </span>
      ) : null}
      <div className="bubble-col">
        <div className={isUser ? 'bubble user' : 'bubble ai'}>
          <p className="bubble-text">{message.text}</p>
          {isUser && message.pending ? <span className="pending-tag">待发送</span> : null}
          {isUser && message.failed ? <span className="failed-tag">未送达</span> : null}
        </div>
        {message.policy_card ? (
          <PolicyCard card={message.policy_card} sourceLabel={message.source_label} />
        ) : null}
        {message.stations && message.stations.length > 0 ? (
          <div className="station-recos">
            {message.stations.map((station) => (
              <StationCard
                key={station.id}
                station={station}
                onBook={onBook}
                busy={bookingBusyId === station.id}
              />
            ))}
          </div>
        ) : null}
      </div>
      {isUser ? (
        <span className="avatar user" aria-label="我">
          我
        </span>
      ) : null}
    </div>
  );
}
