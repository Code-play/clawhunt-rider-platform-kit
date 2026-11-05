import { createContext, useCallback, useContext, useMemo, useState } from 'react';
import * as api from '../api/client.js';
import { CONSENT_VERSION } from '../mock/data.js';
import { KEYS, load, save, clearAll } from '../lib/storage.js';

const RiderContext = createContext(null);

/**
 * 求职者端的全局状态：渠道来源、告知同意、候选人档案。
 * 会话本身（消息/进度）由聊天页单独持久化，避免与档案状态互相耦合。
 */
export function RiderProvider({ children }) {
  const [channel, setChannel] = useState(() => {
    const fromUrl = new URLSearchParams(window.location.search).get('source_channel');
    if (fromUrl) {
      save(KEYS.channel, fromUrl);
      return fromUrl;
    }
    return load(KEYS.channel, 'direct');
  });
  const [consent, setConsent] = useState(() => load(KEYS.consent));
  const [candidate, setCandidate] = useState(() => load(KEYS.candidate));

  /** 撤回授权 / 演示重置：清空本地所有 rider.h5.* 缓存（含 mock 库）。 */
  const resetLocal = useCallback(() => {
    clearAll();
    setConsent(null);
    setCandidate(null);
    setChannel('direct');
  }, []);

  /** 提交告知同意，并在后端建立候选人档案；返回 consent 记录。 */
  const acceptConsent = useCallback(async () => {
    const consentAt = new Date().toISOString();
    const res = await api.saveConsent({
      consent_version: CONSENT_VERSION,
      consent_at: consentAt,
      source_channel: channel,
    });
    const nextConsent = {
      candidate_id: res.candidate_id,
      consent_version: res.consent_version || CONSENT_VERSION,
      consent_at: res.consent_at || consentAt,
    };
    const nextCandidate = { id: res.candidate_id };
    save(KEYS.consent, nextConsent);
    save(KEYS.candidate, nextCandidate);
    setConsent(nextConsent);
    setCandidate(nextCandidate);
    return nextConsent;
  }, [channel]);

  const refreshCandidate = useCallback(async () => {
    if (!consent || !consent.candidate_id) return null;
    try {
      const data = await api.getCandidate(consent.candidate_id);
      save(KEYS.candidate, data);
      setCandidate(data);
      return data;
    } catch (err) {
      if (err && err.status === 404) {
        console.warn('[rider] 候选人档案已不存在（可能已撤回），清空本地状态');
        resetLocal();
        return null;
      }
      console.warn('[rider] 读取档案失败:', err.message);
      return null;
    }
  }, [consent, resetLocal]);

  const patchCandidate = useCallback(
    async (patch) => {
      if (!candidate || !candidate.id) throw new Error('候选人档案不存在');
      const data = await api.patchCandidate(candidate.id, patch);
      save(KEYS.candidate, data);
      setCandidate(data);
      return data;
    },
    [candidate],
  );

  const value = useMemo(
    () => ({
      channel,
      consent,
      candidate,
      hasConsent: Boolean(consent && consent.candidate_id),
      candidateId: (candidate && candidate.id) || (consent && consent.candidate_id) || null,
      acceptConsent,
      refreshCandidate,
      patchCandidate,
      resetLocal,
    }),
    [channel, consent, candidate, acceptConsent, refreshCandidate, patchCandidate, resetLocal],
  );

  return <RiderContext.Provider value={value}>{children}</RiderContext.Provider>;
}

export function useRider() {
  const ctx = useContext(RiderContext);
  if (!ctx) throw new Error('useRider 必须在 RiderProvider 内使用');
  return ctx;
}
