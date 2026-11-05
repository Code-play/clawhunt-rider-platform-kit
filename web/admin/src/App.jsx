import { HashRouter, Navigate, Route, Routes } from 'react-router-dom';
import { App as AntdApp, ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { AuthProvider, useAuth } from './state/AuthContext.jsx';
import AppLayout from './components/AppLayout.jsx';
import LoginPage from './pages/LoginPage.jsx';
import DashboardPage from './pages/DashboardPage.jsx';
import CandidatesPage from './pages/CandidatesPage.jsx';
import CandidateDetailPage from './pages/CandidateDetailPage.jsx';
import SchedulePage from './pages/SchedulePage.jsx';
import StationsPage from './pages/StationsPage.jsx';

function Shell() {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) return <LoginPage />;
  return (
    <AppLayout>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/candidates" element={<CandidatesPage />} />
        <Route path="/candidates/:candidateId" element={<CandidateDetailPage />} />
        <Route path="/schedule" element={<SchedulePage />} />
        <Route path="/stations" element={<StationsPage />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </AppLayout>
  );
}

export default function App() {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#1677ff',
          borderRadius: 6,
          fontSize: 14,
        },
      }}
    >
      <AntdApp>
        <HashRouter>
          <AuthProvider>
            <Shell />
          </AuthProvider>
        </HashRouter>
      </AntdApp>
    </ConfigProvider>
  );
}
