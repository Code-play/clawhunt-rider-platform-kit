import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import * as api from '../api/client.js';
import { useRider } from '../state/RiderContext.jsx';
import { useToast } from '../components/Toast.jsx';
import { Dialog, Loading } from '../components/ui.jsx';
import { CONSENT_DOC, HOTLINE } from '../mock/data.js';
import { formatDateTime, hasEbikeText, jobTypeText } from '../lib/format.js';

const EMPTY_FORM = {
  name: '',
  phone: '',
  birth_ym: '',
  area_text: '',
  job_type: '',
  has_ebike: '',
  start_text: '',
};

export default function SelfServicePage() {
  const navigate = useNavigate();
  const toast = useToast();
  const {
    candidateId,
    consent,
    candidate: cachedCandidate,
    refreshCandidate,
    patchCandidate,
    resetLocal,
  } = useRider();

  const [info, setInfo] = useState(cachedCandidate || null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [loading, setLoading] = useState(!cachedCandidate);
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [revokeOpen, setRevokeOpen] = useState(false);
  const [revoking, setRevoking] = useState(false);

  const hydrate = useCallback((data) => {
    setInfo(data);
    setForm({
      name: '',
      phone: '',
      birth_ym: data.birth_ym || '',
      area_text: data.area_text || '',
      job_type: data.job_type || '',
      has_ebike: data.has_ebike == null ? '' : String(data.has_ebike),
      start_text: data.start_text || '',
    });
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      const data = await refreshCandidate();
      if (!alive) return;
      if (data) hydrate(data);
      setLoading(false);
    })();
    return () => {
      alive = false;
    };
  }, [refreshCandidate, hydrate]);

  const update = (key) => (e) => setForm((prev) => ({ ...prev, [key]: e.target.value }));

  const save = async () => {
    const patch = {};
    if (form.name.trim()) patch.name = form.name.trim();
    if (form.phone.trim()) {
      if (!/^1\d{10}$/.test(form.phone.trim())) {
        toast('手机号需为 11 位数字');
        return;
      }
      patch.phone = form.phone.trim();
    }
    ['birth_ym', 'area_text', 'start_text'].forEach((key) => {
      const next = form[key].trim();
      if (next && next !== (info[key] || '')) patch[key] = next;
    });
    if (form.job_type && form.job_type !== info.job_type) patch.job_type = form.job_type;
    if (form.has_ebike !== '' && String(info.has_ebike) !== form.has_ebike) {
      patch.has_ebike = form.has_ebike === 'true';
    }

    if (Object.keys(patch).length === 0) {
      toast('没有检测到修改内容');
      return;
    }

    setSaving(true);
    try {
      const updated = await patchCandidate(patch);
      hydrate(updated);
      toast('已保存更正，并记录修改留痕');
    } catch (err) {
      toast(err.message || '保存失败，请稍后重试');
    } finally {
      setSaving(false);
    }
  };

  const downloadCopy = async () => {
    if (!candidateId) return;
    setExporting(true);
    try {
      const data = await api.exportMyInfo(candidateId);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `rider-info-${candidateId}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast('信息副本已开始下载（JSON）');
    } catch (err) {
      toast(err.message || '下载失败，请稍后重试');
    } finally {
      setExporting(false);
    }
  };

  const revoke = async () => {
    if (!candidateId) return;
    setRevoking(true);
    try {
      await api.revokeMyInfo(candidateId);
      resetLocal();
      toast('已撤回授权：后端记录与本地缓存均已删除');
      navigate('/', { replace: true });
    } catch (err) {
      toast(err.message || '撤回失败，请稍后重试');
    } finally {
      setRevoking(false);
      setRevokeOpen(false);
    }
  };

  if (loading) return <Loading text="正在读取你的信息…" />;

  return (
    <div className="self-service">
      <section className="card">
        <h2 className="section-title">我的信息</h2>
        <div className="kv-row">
          <span className="kv-key">姓名</span>
          <span className="kv-value">{info && info.name_masked ? info.name_masked : '未填写'}</span>
        </div>
        <div className="kv-row">
          <span className="kv-key">手机号</span>
          <span className="kv-value">{info && info.phone_masked ? info.phone_masked : '未填写'}</span>
        </div>
        <div className="kv-row">
          <span className="kv-key">出生年月</span>
          <span className="kv-value">{(info && info.birth_ym) || '未填写'}</span>
        </div>
        <div className="kv-row">
          <span className="kv-key">跑单区域</span>
          <span className="kv-value">{(info && info.area_text) || '未填写'}</span>
        </div>
        <div className="kv-row">
          <span className="kv-key">工作类型</span>
          <span className="kv-value">{jobTypeText(info && info.job_type)}</span>
        </div>
        <div className="kv-row">
          <span className="kv-key">电动车</span>
          <span className="kv-value">{hasEbikeText(info && info.has_ebike)}</span>
        </div>
        <div className="kv-row">
          <span className="kv-key">可到岗时间</span>
          <span className="kv-value">{(info && info.start_text) || '未填写'}</span>
        </div>
        <p className="muted small">
          姓名的完整值在系统中以令牌存储，此处仅展示掩码；招募专员查看完整手机号需填写理由并留痕。
        </p>
      </section>

      <section className="card">
        <h3 className="section-title">同意记录</h3>
        <div className="kv-row">
          <span className="kv-key">告知书版本</span>
          <span className="kv-value">
            {CONSENT_DOC.title} {CONSENT_DOC.version}
          </span>
        </div>
        <div className="kv-row">
          <span className="kv-key">同意时间</span>
          <span className="kv-value">
            {formatDateTime((consent && consent.consent_at) || (info && info.consent_at))}
          </span>
        </div>
        <div className="kv-row">
          <span className="kv-key">渠道</span>
          <span className="kv-value">{(info && info.source_channel) || 'direct'}</span>
        </div>
      </section>

      <section className="card">
        <h3 className="section-title">1. 查看 / 更正我的信息</h3>
        <p className="muted small">
          以下内容可自助更正，保存后会写入修改留痕（改了什么、改前改后）。姓名与手机号留空表示不修改。
        </p>
        <div className="form-grid">
          <label className="field">
            <span className="field-label">更正姓名（可选）</span>
            <input
              className="input"
              value={form.name}
              onChange={update('name')}
              placeholder="如需更正请输入完整姓名"
            />
          </label>
          <label className="field">
            <span className="field-label">更正手机号（可选）</span>
            <input
              className="input"
              inputMode="numeric"
              value={form.phone}
              onChange={update('phone')}
              placeholder="11 位手机号"
            />
          </label>
          <label className="field">
            <span className="field-label">出生年月</span>
            <input
              className="input"
              value={form.birth_ym}
              onChange={update('birth_ym')}
              placeholder="YYYY-MM"
            />
          </label>
          <label className="field">
            <span className="field-label">跑单区域</span>
            <input
              className="input"
              value={form.area_text}
              onChange={update('area_text')}
              placeholder="如 浦东新区"
            />
          </label>
          <label className="field">
            <span className="field-label">工作类型</span>
            <select className="input" value={form.job_type} onChange={update('job_type')}>
              <option value="">请选择</option>
              <option value="fulltime">全职</option>
              <option value="parttime">兼职</option>
              <option value="undecided">还没想好</option>
            </select>
          </label>
          <label className="field">
            <span className="field-label">是否有电动车</span>
            <select className="input" value={form.has_ebike} onChange={update('has_ebike')}>
              <option value="">请选择</option>
              <option value="true">有</option>
              <option value="false">没有</option>
            </select>
          </label>
          <label className="field">
            <span className="field-label">可到岗时间</span>
            <input
              className="input"
              value={form.start_text}
              onChange={update('start_text')}
              placeholder="如 明天 / 本周内"
            />
          </label>
        </div>
        <button type="button" className="btn primary block" onClick={save} disabled={saving}>
          {saving ? '保存中…' : '保存更正'}
        </button>
      </section>

      <section className="card">
        <h3 className="section-title">2. 下载我的信息副本</h3>
        <p className="muted small">
          导出 JSON 副本（含登记字段、同意版本与时间、当前状态）；副本中姓名与手机号仍为掩码。
        </p>
        <button type="button" className="btn ghost block" onClick={downloadCopy} disabled={exporting}>
          {exporting ? '生成中…' : '下载信息副本'}
        </button>
      </section>

      <section className="card">
        <h3 className="section-title">3. 撤回授权并删除</h3>
        <p className="muted small">
          撤回后：删除后端登记信息与预约、清空本机会话与进度缓存，且不可恢复。如已入职，请联系人事另行处理。
        </p>
        <button type="button" className="btn danger block" onClick={() => setRevokeOpen(true)}>
          撤回授权并删除我的信息
        </button>
      </section>

      <section className="card">
        <h3 className="section-title">4. 联系人工</h3>
        <a className="btn primary block" href={`tel:${HOTLINE.replace(/-/g, '')}`}>
          拨打招聘热线 {HOTLINE}
        </a>
        <button type="button" className="btn ghost block" onClick={() => navigate('/chat?handoff=1')}>
          转人工在线跟进
        </button>
      </section>

      <Dialog
        open={revokeOpen}
        title="确认撤回授权并删除？"
        onCancel={() => setRevokeOpen(false)}
        onOk={revoke}
        okText="确认撤回并删除"
        cancelText="我再想想"
        danger
        confirmLoading={revoking}
      >
        <p>
          将删除后端候选人档案、预约记录（预约时段会被释放），并清空本机会话与进度缓存。此操作不可恢复。
        </p>
      </Dialog>
    </div>
  );
}
