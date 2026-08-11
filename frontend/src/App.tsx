import { useCallback, useEffect, useState } from 'react';
import { useChatStore } from './store/useChatStore';
import { Layout } from './components/layout/Layout';
import { Toaster } from './components/ui/sonner';
import { StartupScreen } from './components/layout/StartupScreen';
import { UploadGate } from './components/layout/UploadGate';
import { LoginScreen } from './components/auth/LoginScreen';
import { motion } from 'framer-motion';
import { NovaMark } from './components/brand/NovaMark';

function App() {
  const token = useChatStore((s) => s.token);
  const userId = useChatStore((s) => s.userId);
  const bootstrapSession = useChatStore((s) => s.bootstrapSession);
  const [isReady, setIsReady] = useState(false);
  const [gatePassed, setGatePassed] = useState(false);
  const [sessionChecked, setSessionChecked] = useState(false);

  useEffect(() => {
    let active = true;
    bootstrapSession()
      // A missing or expired refresh cookie is the normal signed-out state.
      // Avoid a redundant logout request that can mask the original failure.
      .catch(() => undefined)
      .finally(() => active && setSessionChecked(true));
    return () => { active = false; };
  }, [bootstrapSession]);

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
