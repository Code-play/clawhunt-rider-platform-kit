import { HashRouter, Navigate, Route, Routes } from 'react-router-dom';
import { RiderProvider, useRider } from './state/RiderContext.jsx';
import { ToastProvider } from './components/Toast.jsx';
import AppLayout from './components/AppLayout.jsx';
import EntryPage from './pages/EntryPage.jsx';
import ConsentPage from './pages/ConsentPage.jsx';
import ChatPage from './pages/ChatPage.jsx';
import StationsPage from './pages/StationsPage.jsx';
import ResultPage from './pages/ResultPage.jsx';
import SelfServicePage from './pages/SelfServicePage.jsx';

function RequireConsent({ children }) {
  const { hasConsent } = useRider();
  if (!hasConsent) return <Navigate to="/consent" replace />;
  return children;
}

export default function App() {
  return (
    <HashRouter>
      <RiderProvider>
        <ToastProvider>
          <AppLayout>
            <Routes>
              <Route path="/" element={<EntryPage />} />
              <Route path="/consent" element={<ConsentPage />} />
              <Route
                path="/chat"
                element={
                  <RequireConsent>
                    <ChatPage />
                  </RequireConsent>
                }
              />
              <Route
                path="/stations"
                element={
                  <RequireConsent>
                    <StationsPage />
                  </RequireConsent>
                }
              />
              <Route
                path="/result/:bookingId"
                element={
                  <RequireConsent>
                    <ResultPage />
                  </RequireConsent>
                }
              />
              <Route
                path="/me"
                element={
                  <RequireConsent>
                    <SelfServicePage />
                  </RequireConsent>
                }
              />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </AppLayout>
        </ToastProvider>
      </RiderProvider>
    </HashRouter>
  );
}
