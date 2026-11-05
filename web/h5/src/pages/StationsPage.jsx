import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import * as api from '../api/client.js';
import { useRider } from '../state/RiderContext.jsx';
import { useToast } from '../components/Toast.jsx';
import { ErrorBlock, Loading, StationCard } from '../components/ui.jsx';
import { KEYS, save } from '../lib/storage.js';

export default function StationsPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const [searchParams] = useSearchParams();
  const { candidateId } = useRider();
  const rescheduleId = searchParams.get('reschedule');

  const [stations, setStations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busyId, setBusyId] = useState('');
  const [rescheduleTarget, setRescheduleTarget] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await api.listStations();
      setStations(data.stations || []);
    } catch (err) {
      setError(err.message || '站点加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!rescheduleId) return;
    api
      .getBooking(rescheduleId)
      .then((b) => setRescheduleTarget(b))
      .catch((err) => toast(err.message || '读取原预约失败'));
  }, [rescheduleId, toast]);

  const visibleStations = useMemo(() => {
    if (rescheduleTarget) {
      return stations.filter((s) => s.id === rescheduleTarget.station_id);
    }
    return stations;
  }, [stations, rescheduleTarget]);

  const book = async (station, slotStart) => {
    if (!candidateId) return;
    setBusyId(station.id);
    try {
      const booking = rescheduleId
        ? await api.rescheduleBooking(rescheduleId, slotStart)
        : await api.createBooking({
            candidate_id: candidateId,
            station_id: station.id,
            slot_start: slotStart,
          });
      save(KEYS.booking, booking.id);
      toast(rescheduleId ? '改约成功' : '预约成功');
      navigate(`/result/${booking.id}`);
    } catch (err) {
      toast(err.message || '预约失败，请稍后重试');
    } finally {
      setBusyId('');
    }
  };

  if (loading) return <Loading text="正在获取附近站点…" />;
  if (error) return <ErrorBlock message={error} onRetry={load} />;

  return (
    <div className="stations-page">
      <p className="muted small">
        {rescheduleTarget
          ? `改约：仅支持原站点「${rescheduleTarget.station.name}」，选择新的时段即可。`
          : '按距离由近到远列出在招站点；在招人数为站点当前招聘名额，时段为可预约面试时间。'}
      </p>
      {visibleStations.length === 0 ? (
        <ErrorBlock message="当前没有可预约站点，请稍后重试或转人工。" onRetry={load} />
      ) : null}
      {visibleStations.map((station) => (
        <StationCard
          key={station.id}
          station={station}
          onBook={book}
          busy={busyId === station.id}
        />
      ))}
      <button type="button" className="btn ghost block" onClick={() => navigate('/chat')}>
        返回 AI 对话
      </button>
    </div>
  );
}
