import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { NovaMark } from '../brand/NovaMark';
import { api } from '../../services/api';

interface StartupScreenProps {
  onReady: () => void;
}

const STEPS = [
  { label: 'Initializing Nova AI...', progress: 15 },
  { label: 'Connecting to backend...', progress: 35 },
  { label: 'Loading AI model...', progress: 65 },
  { label: 'Loading knowledge base...', progress: 85 },
  { label: 'Ready.', progress: 100 },
];

export const StartupScreen = ({ onReady }: StartupScreenProps) => {
  const [stepIndex, setStepIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    const checkHealth = async () => {
      if (!isMounted) return;
      try {
        setStepIndex(1);

        const data = await api.readinessCheck();

        if (!isMounted) return;
        const llmReady = data.ready === true;
        if (llmReady) {
          setError(null);
          setStepIndex(2);
          await new Promise(r => setTimeout(r, 700));
          if (!isMounted) return;

          setStepIndex(3);
          await new Promise(r => setTimeout(r, 600));
          if (!isMounted) return;

          setStepIndex(4);

          setTimeout(() => {
            if (isMounted) onReady();
          }, 500);
        } else {
          setError(data.message || (data.llm_provider === 'groq'
            ? 'Groq is not ready yet. Nova will reconnect automatically.'
            : 'Ollama is offline. Start it and Nova will reconnect automatically.'));
          setTimeout(checkHealth, 5000);
        }
      } catch (err: unknown) {
        if (!isMounted) return;
        const errorName = err instanceof DOMException || err instanceof Error ? err.name : '';
        if (errorName === 'TimeoutError' || errorName === 'AbortError') {
          setError('The workspace is waking up. Reconnecting…');
          setTimeout(checkHealth, 3000);
        } else {
          setError('The workspace is waking up. Reconnecting…');
          setTimeout(checkHealth, 3000);
        }
      }
    };

    // Short delay then kick off
    const t = setTimeout(checkHealth, 300);
    return () => {
      isMounted = false;
      clearTimeout(t);
    };
  }, [onReady]);

  const currentStep = STEPS[stepIndex];

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0, transition: { duration: 0.6, ease: 'easeInOut' } }}
        className="nova-shell fixed inset-0 z-50 h-[100dvh] w-screen overflow-hidden bg-background"
      >
        <div className="nova-grid" />
        {/* Ambient background */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_80%_50%_at_50%_-10%,rgba(99,102,241,0.12),transparent)] pointer-events-none" />
        <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-[600px] h-[300px] bg-violet-500/5 blur-3xl rounded-full pointer-events-none" />

        {/* Grid pattern */}
        <div
          className="absolute inset-0 opacity-[0.025] pointer-events-none"
          style={{
            backgroundImage: 'linear-gradient(hsl(var(--border)) 1px, transparent 1px), linear-gradient(90deg, hsl(var(--border)) 1px, transparent 1px)',
            backgroundSize: '40px 40px',
          }}
        />

        <div className="nova-viewport-center">
          <motion.div
            initial={{ scale: 0.88, opacity: 0, y: 20 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
            className="nova-startup-panel relative flex w-full max-w-md flex-col items-center gap-8 overflow-hidden rounded-[2rem] px-8 py-10 md:px-12 md:py-12"
          >
          <div className="absolute inset-x-12 top-0 h-[2px] bg-gradient-to-r from-transparent via-primary to-transparent" />
          <div className="pointer-events-none absolute -right-16 -top-20 h-44 w-44 rounded-full bg-primary/15 blur-3xl" />
          {/* Logo */}
          <div className="flex flex-col items-center gap-4">
            <motion.div
              animate={{ boxShadow: ['0 0 20px rgba(99,102,241,0.2)', '0 0 40px rgba(99,102,241,0.35)', '0 0 20px rgba(99,102,241,0.2)'] }}
              transition={{ duration: 2.5, repeat: Infinity, ease: 'easeInOut' }}
              className="nova-logo-orbit"
            >
              <NovaMark className="h-9 w-9" title="Nova AI" />
            </motion.div>

            <div className="text-center">
              <h1 className="text-2xl font-bold tracking-tight text-foreground">
                Nova AI Agent
              </h1>
              <p className="text-sm text-muted-foreground/60 mt-1 font-medium">
                Private RAG Workspace
              </p>
            </div>
          </div>

          {/* Progress section */}
          <div className="flex flex-col items-center gap-4 w-72">
            {/* Progress bar */}
            <div className="w-full h-1 bg-muted/50 rounded-full overflow-hidden">
              <motion.div
                className="h-full rounded-full bg-gradient-to-r from-primary to-violet-500"
                initial={{ width: 0 }}
                animate={{ width: `${currentStep.progress}%` }}
                transition={{ duration: 0.6, ease: 'easeOut' }}
              />
            </div>

            {/* Status text */}
            <div className="h-5 flex items-center justify-center">
              <AnimatePresence mode="wait">
                <motion.p
                  key={stepIndex}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -6 }}
                  transition={{ duration: 0.25 }}
                  className="text-[13px] text-muted-foreground/70 font-medium text-center"
                >
                  {error || currentStep.label}
                </motion.p>
              </AnimatePresence>
            </div>

            {/* Retry hint if error */}
            {error && (
              <motion.p
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="text-[12px] text-muted-foreground/50 text-center"
              >
                Retrying automatically...
              </motion.p>
            )}
          </div>

          {/* Step dots */}
          <div className="flex items-center gap-2">
            {STEPS.map((_, i) => (
              <motion.div
                key={i}
                className="rounded-full transition-all duration-300"
                animate={{
                  width: i === stepIndex ? 20 : 6,
                  backgroundColor: i < stepIndex
                    ? 'hsl(var(--primary))'
                    : i === stepIndex
                      ? 'hsl(var(--primary))'
                      : 'hsl(var(--border))',
                  height: 6,
                  opacity: i > stepIndex ? 0.35 : 1,
                }}
                transition={{ duration: 0.3 }}
              />
            ))}
          </div>
          </motion.div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
};
