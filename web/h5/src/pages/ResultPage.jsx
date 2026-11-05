import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import * as api from '../api/client.js';
import { useToast } from '../components/Toast.jsx';
import { Dialog, ErrorBlock, Loading } from '../components/ui.jsx';
import { ARRIVAL_NOTICE, HOTLINE } from '../mock/data.js';
import { KEYS, save } from '../lib/storage.js';
import { formatDateTime, slotLabel } from '../lib/format.js';

export default function ResultPage() {
  const { bookingId } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const [booking, setBooking] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [cancelOpen, setCancelOpen] = useState(false);
  const [cancelling, setCancelling] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await api.getBooking(bookingId);
      setBooking(data);
      save(KEYS.booking, data.id);
    } catch (err) {
      setError(err.message || '预约信息加载失败');
    } finally {
      setLoading(false);
    }
  }, [bookingId]);

  useEffect(() => {
    load();
  }, [load]);

  const station = booking && booking.station;
  const cancelled = booking && booking.status !== 'booked';

  const navUrl =
    station && station.lat && station.lng
      ? `https://uri.amap.com/marker?position=${station.lng},${station.lat}&name=${encodeURIComponent(
          station.name,
        )}&src=rider-agent&coordinate=gaode&callnative=0`
      : '';

  const cancel = async () => {
    setCancelling(true);
    try {
      await api.cancelBooking(bookingId);
      setCancelOpen(false);
      toast('预约已取消，可随时重新预约');
      await load();
    } catch (err) {
      toast(err.message || '取消失败，请稍后重试');
    } finally {
      setCancelling(false);
    }
  };

  if (loading) return <Loading text="正在读取预约信息…" />;
  if (error) return <ErrorBlock message={error} onRetry={load} />;
  if (!booking) return <ErrorBlock message="预约不存在" onRetry={load} />;

  return (
    <div className="result-page">
      <section className={cancelled ? 'result-hero cancelled' : 'result-hero'}>
        <span className="result-icon" aria-hidden="true">
          {cancelled ? '×' : '✓'}
        </span>
        <h2>{cancelled ? '预约已取消' : '预约成功'}</h2>
        <p className="muted">
          {cancelled
            ? '该时段已释放，你可以重新选择站点与时段。'
            : '请按预约时间到站，站长会电话确认；迟到超过 20 分钟需重新预约。'}
        </p>
      </section>

      <section className="card">
        <div className="kv-row">
          <span className="kv-key">预约单号</span>
          <span className="kv-value">{booking.id}</span>
        </div>
        <div className="kv-row">
          <span className="kv-key">站点</span>
          <span className="kv-value">{station ? station.name : booking.station_id}</span>
        </div>
        <div className="kv-row">
          <span className="kv-key">地址</span>
          <span className="kv-value">{station ? station.address : '-'}</span>
        </div>
        <div className="kv-row">
          <span className="kv-key">时段</span>
          <span className="kv-value">{slotLabel(booking.slot_start)}</span>
        </div>
        <div className="kv-row">
          <span className="kv-key">状态</span>
          <span className="kv-value">
            {booking.status === 'booked' ? '已预约（待到站）' : '已取消'}
          </span>
        </div>
        <div className="kv-row">
          <span className="kv-key">创建时间</span>
          <span className="kv-value">{formatDateTime(booking.created_at)}</span>
        </div>
      </section>

      {!cancelled ? (
        <>
          <section className="card">
            <h3 className="section-title">到站指引</h3>
            <div className="result-actions">
              {navUrl ? (
                <a className="btn primary block" href={navUrl} target="_blank" rel="noreferrer">
                  打开地图导航
                </a>
              ) : null}
              {station && station.manager_virtual_no ? (
                <a
                  className="btn ghost block"
                  href={`tel:${station.manager_virtual_no}`}
                >
                  拨打站长虚拟号 {station.manager_display_no || station.manager_virtual_no}
                </a>
              ) : null}
            </div>
            <p className="muted small">
              站长号码为平台分配的虚拟号，通话将转接至站点，双方均看不到真实号码。
            </p>
          </section>

          <section className="card">
            <h3 className="section-title">到站须知</h3>
            <ul className="notice-list">
              {ARRIVAL_NOTICE.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>
        </>
      ) : null}

      <section className="card">
        <h3 className="section-title">需要调整？</h3>
        {!cancelled ? (
          <button
            type="button"
            className="btn ghost block"
            onClick={() => navigate(`/stations?reschedule=${bookingId}`)}
          >
            改约其他时段
          </button>
        ) : (
          <button type="button" className="btn primary block" onClick={() => navigate('/stations')}>
            重新选择站点与时段
          </button>
        )}
        {!cancelled ? (
          <button type="button" className="btn ghost block" onClick={() => setCancelOpen(true)}>
            取消预约
          </button>
        ) : null}
        <button type="button" className="btn ghost block" onClick={() => navigate('/chat')}>
          返回 AI 对话
        </button>
      </section>

      <p className="muted small center">
        预约结果由 AI 助手生成，最终以站长电话通知为准。人工热线{' '}
        <a href={`tel:${HOTLINE.replace(/-/g, '')}`}>{HOTLINE}</a>
      </p>

      <Dialog
        open={cancelOpen}
        title="确认取消预约？"
        onCancel={() => setCancelOpen(false)}
        onOk={cancel}
        okText="确认取消"
        cancelText="先不取消"
        danger
        confirmLoading={cancelling}
      >
        <p>取消后该时段会释放给其他求职者，你需要重新选择时段预约。</p>
      </Dialog>
    </div>
  );
}
