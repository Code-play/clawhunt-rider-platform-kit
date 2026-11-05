import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';

const ToastContext = createContext(() => {});

export function ToastProvider({ children }) {
  const [message, setMessage] = useState('');
  const timerRef = useRef(null);

  const show = useCallback((text) => {
    setMessage(String(text || ''));
    if (timerRef.current) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => setMessage(''), 2800);
  }, []);

  useEffect(
    () => () => {
      if (timerRef.current) window.clearTimeout(timerRef.current);
    },
    [],
  );

  return (
    <ToastContext.Provider value={show}>
      {children}
      {message ? (
        <div className="toast" role="status" aria-live="polite">
          {message}
        </div>
      ) : null}
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
