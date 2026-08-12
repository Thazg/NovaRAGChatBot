import { useCallback, useEffect, useState } from 'react';
import { useChatStore } from './store/useChatStore';
import { Layout } from './components/layout/Layout';
import { Toaster } from './components/ui/sonner';
import { StartupScreen } from './components/layout/StartupScreen';
import { UploadGate } from './components/layout/UploadGate';
import { LoginScreen } from './components/auth/LoginScreen';
import { motion } from 'framer-motion';
import { NovaMark } from './components/brand/NovaMark';
import { RefreshCw, LogIn } from 'lucide-react';

function App() {
  const token = useChatStore((s) => s.token);
  const userId = useChatStore((s) => s.userId);
  const bootstrapSession = useChatStore((s) => s.bootstrapSession);
  const [isReady, setIsReady] = useState(false);
  const [gatePassed, setGatePassed] = useState(false);
  const [sessionChecked, setSessionChecked] = useState(false);
  const [sessionRecoveryNeeded, setSessionRecoveryNeeded] = useState(false);

  const checkSession = useCallback(async () => {
    setSessionChecked(false);
    setSessionRecoveryNeeded(false);
    try {
      await bootstrapSession();
    } catch (error) {
      // A 401 means signed out. Network/schema failures may still have a valid
      // HttpOnly refresh cookie, so do not turn them into a false logout.
      if (!(error instanceof Error && error.message === 'Session expired')) {
        setSessionRecoveryNeeded(true);
      }
    } finally {
      setSessionChecked(true);
    }
  }, [bootstrapSession]);

  useEffect(() => { void checkSession(); }, [checkSession]);

  useEffect(() => {
    setIsReady(false);
    setGatePassed(false);
  }, [userId]);

  const handleReady = useCallback(() => setIsReady(true), []);

  if (!sessionChecked) {
    return (
      <div className="nova-shell relative flex min-h-dvh items-center justify-center overflow-hidden">
        <div className="nova-grid" />
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="relative z-10 flex flex-col items-center gap-4"
        >
          <div className="nova-logo-orbit">
            <NovaMark className="h-7 w-7" title="Nova AI" />
          </div>
          <p className="text-sm font-medium text-muted-foreground">Securing your workspace…</p>
        </motion.div>
      </div>
    );
  }

  if (sessionRecoveryNeeded) {
    return (
      <main className="nova-shell relative flex min-h-dvh items-center justify-center overflow-hidden p-6">
        <div className="nova-grid" />
        <motion.section
          initial={{ opacity: 0, y: 16, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          className="nova-panel relative z-10 w-full max-w-md rounded-[2rem] p-8 text-center"
          role="alert"
        >
          <div className="nova-logo-orbit mx-auto mb-5">
            <NovaMark className="h-7 w-7" title="Nova AI" />
          </div>
          <h1 className="text-xl font-semibold text-foreground">Your session is still recoverable</h1>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">
            Nova could not reach the workspace. Your secure cookie was not removed; retry when the service is available.
          </p>
          <div className="mt-6 grid gap-3 sm:grid-cols-2">
            <button
              type="button"
              onClick={() => void checkSession()}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground"
            >
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              Retry session
            </button>
            <button
              type="button"
              onClick={() => setSessionRecoveryNeeded(false)}
              className="inline-flex items-center justify-center gap-2 rounded-xl border border-border bg-card px-4 py-3 text-sm font-semibold text-foreground"
            >
              <LogIn className="h-4 w-4" aria-hidden="true" />
              Go to sign in
            </button>
          </div>
        </motion.section>
        <Toaster position="top-center" />
      </main>
    );
  }

  if (!token) {
    return (
      <>
        <LoginScreen />
        <Toaster position="top-center" />
      </>
    );
  }

  return (
    <>
      {!isReady && <StartupScreen onReady={handleReady} />}
      {isReady && !gatePassed && <UploadGate onContinue={() => setGatePassed(true)} />}
      {gatePassed && <Layout />}
      <Toaster position="top-center" />
    </>
  );
}

export default App;
