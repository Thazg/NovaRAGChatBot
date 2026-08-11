import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  ChevronRight,
  Database,
  Eye,
  EyeOff,
  FileText,
  Loader2,
  LogIn,
  Quote,
  Search,
  ShieldCheck,
  UserPlus,
} from 'lucide-react';

import { NovaMark } from '../brand/NovaMark';
import { useResolvedTheme } from '../../hooks/useResolvedTheme';
import { useChatStore } from '../../store/useChatStore';

const atlasStyles = `
  @keyframes nova-scan {
    0% { transform: translateY(-120%); opacity: 0; }
    18% { opacity: .65; }
    82% { opacity: .65; }
    100% { transform: translateY(520%); opacity: 0; }
  }
  @keyframes nova-drift {
    0%, 100% { transform: translate3d(0, 0, 0); }
    50% { transform: translate3d(0, -8px, 0); }
  }
  @keyframes nova-marquee {
    from { transform: translateX(0); }
    to { transform: translateX(-50%); }
  }
  .nova-atlas-grid {
    background-image:
      linear-gradient(rgba(129, 140, 248, .07) 1px, transparent 1px),
      linear-gradient(90deg, rgba(129, 140, 248, .07) 1px, transparent 1px);
    background-size: 48px 48px;
    mask-image: linear-gradient(to bottom, transparent 0%, black 16%, black 78%, transparent 100%);
  }
`;

function FlowNode({
  className,
  icon,
  eyebrow,
  label,
  delay,
}: {
  className: string;
  icon: React.ReactNode;
  eyebrow: string;
  label: string;
  delay: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: [0, -5, 0] }}
      transition={{
        opacity: { delay, duration: 0.5 },
        y: { delay: delay + 0.5, duration: 4.5, repeat: Infinity, ease: 'easeInOut' },
      }}
      className={`absolute z-20 min-w-[136px] rounded-xl border border-white/10 bg-[#0d1020]/90 p-3 shadow-2xl shadow-black/30 backdrop-blur-xl ${className}`}
    >
      <div className="mb-2 flex items-center justify-between">
        <span className="grid h-7 w-7 place-items-center rounded-md border border-indigo-400/20 bg-indigo-400/10 text-indigo-300">
          {icon}
        </span>
        <span className="font-mono text-[8px] tracking-[0.2em] text-emerald-300/70">LIVE</span>
      </div>
      <div className="font-mono text-[9px] uppercase tracking-[0.22em] text-slate-500">{eyebrow}</div>
      <div className="mt-1 text-xs font-semibold text-slate-100">{label}</div>
    </motion.div>
  );
}

function NeuralAtlas() {
  return (
    <div className="relative mt-8 h-[300px] overflow-hidden rounded-[28px] border border-white/[0.08] bg-[#090b16]/70 shadow-2xl shadow-black/20">
      <div className="nova-atlas-grid absolute inset-0" />
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-indigo-400/70 to-transparent" />
      <div className="absolute left-5 top-4 font-mono text-[9px] tracking-[0.3em] text-slate-600">KNOWLEDGE MAP / 03</div>
      <div className="absolute right-5 top-4 flex items-center gap-2 font-mono text-[9px] tracking-[0.18em] text-emerald-300/70">
        <span className="h-1.5 w-1.5 rounded-sm bg-emerald-300 shadow-[0_0_12px_rgba(110,231,183,.9)]" />
        SYSTEM ONLINE
      </div>

      <svg className="absolute inset-0 h-full w-full" viewBox="0 0 620 300" fill="none" aria-hidden="true">
        <defs>
          <linearGradient id="nova-flow" x1="50" y1="150" x2="570" y2="150" gradientUnits="userSpaceOnUse">
            <stop stopColor="#22d3ee" stopOpacity="0" />
            <stop offset="0.28" stopColor="#818cf8" />
            <stop offset="0.7" stopColor="#c084fc" />
            <stop offset="1" stopColor="#f472b6" stopOpacity="0" />
          </linearGradient>
          <filter id="nova-glow">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>
        <path d="M45 207 C148 207 142 88 256 113 S390 239 576 128" stroke="#818cf8" strokeOpacity=".16" />
        <motion.path
          d="M45 207 C148 207 142 88 256 113 S390 239 576 128"
          stroke="url(#nova-flow)"
          strokeWidth="2"
          strokeDasharray="8 16"
          filter="url(#nova-glow)"
          animate={{ strokeDashoffset: [48, 0] }}
          transition={{ duration: 2.8, repeat: Infinity, ease: 'linear' }}
        />
        <path d="M72 80 C188 24 267 245 377 197 S480 68 570 81" stroke="#22d3ee" strokeOpacity=".1" />
        <motion.path
          d="M72 80 C188 24 267 245 377 197 S480 68 570 81"
          stroke="url(#nova-flow)"
          strokeDasharray="3 20"
          animate={{ strokeDashoffset: [46, 0] }}
          transition={{ duration: 4.2, repeat: Infinity, ease: 'linear' }}
        />
      </svg>

      <FlowNode className="left-[6%] top-[42%]" icon={<FileText className="h-3.5 w-3.5" />} eyebrow="01 / Ingest" label="Private documents" delay={0.2} />
      <FlowNode className="left-1/2 top-[24%] -translate-x-1/2" icon={<Search className="h-3.5 w-3.5" />} eyebrow="02 / Retrieve" label="Hybrid evidence" delay={0.35} />
      <FlowNode className="right-[5%] top-[49%]" icon={<Quote className="h-3.5 w-3.5" />} eyebrow="03 / Ground" label="Cited answers" delay={0.5} />

      <motion.div
        initial={{ opacity: 0, scale: 0.6, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: [0, -5, 0] }}
        transition={{ delay: 0.55, type: 'spring', stiffness: 130 }}
        className="absolute bottom-5 left-1/2 z-10 grid h-16 w-16 -translate-x-1/2 place-items-center rounded-2xl border border-indigo-300/20 bg-[#0d1020]/95 shadow-[0_0_45px_rgba(129,140,248,.24)] backdrop-blur-xl"
      >
        <NovaMark className="h-10 w-10" title="Nova AI" />
      </motion.div>

      <div className="pointer-events-none absolute inset-x-0 top-0 h-20 bg-gradient-to-b from-indigo-400/[0.06] to-transparent [animation:nova-scan_5s_ease-in-out_infinite]" />
    </div>
  );
}

function InputField({
  label,
  type,
  value,
  onChange,
  placeholder,
  showToggle,
  onToggleShow,
  autoFocus,
  autoComplete,
}: {
  label: string;
  type: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  showToggle?: boolean;
  onToggleShow?: () => void;
  autoFocus?: boolean;
  autoComplete?: string;
}) {
  const [focused, setFocused] = useState(false);

  return (
    <div>
      <label className="mb-2 block font-mono text-[10px] font-medium uppercase tracking-[0.2em] text-slate-400">
        {label}
      </label>
      <div className="group relative">
        <input
          type={type}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          placeholder={placeholder}
          autoFocus={autoFocus}
          autoComplete={autoComplete || (showToggle ? 'current-password' : 'username')}
          className="h-12 w-full rounded-xl border border-white/10 bg-black/25 px-4 text-sm text-white outline-none transition duration-300 placeholder:text-slate-600 hover:border-white/20 focus:border-indigo-400/60 focus:bg-indigo-400/[0.04] focus:shadow-[0_0_0_4px_rgba(129,140,248,.08)]"
        />
        {showToggle && (
          <button
            type="button"
            onClick={onToggleShow}
            aria-label={type === 'password' ? 'Show password' : 'Hide password'}
            className="absolute right-3 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-slate-500 transition hover:bg-white/5 hover:text-slate-200"
          >
            {type === 'password' ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
          </button>
        )}
        <motion.span
          className="absolute bottom-0 left-4 right-4 h-px origin-left bg-gradient-to-r from-cyan-300 via-indigo-400 to-fuchsia-400"
          animate={{ scaleX: focused ? 1 : 0, opacity: focused ? 1 : 0 }}
          transition={{ duration: 0.3 }}
        />
      </div>
    </div>
  );
}

export function LoginScreen() {
  const theme = useChatStore((state) => state.theme);
  const computedTheme = useResolvedTheme(theme);
  const login = useChatStore((state) => state.login);
  const register = useChatStore((state) => state.register);

  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  useEffect(() => {
    const root = document.documentElement;
    root.classList.remove('light', 'dark');
    root.classList.add(computedTheme);
  }, [computedTheme]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    if (!username.trim() || !password.trim()) {
      setError('Please fill in all fields.');
      return;
    }
    if (mode === 'register' && !/^[a-zA-Z0-9_.-]{2,40}$/.test(username.trim())) {
      setError('Use 2–40 letters, numbers, dots, dashes, or underscores.');
      return;
    }
    if (mode === 'register' && password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }

    setLoading(true);
    try {
      if (mode === 'login') await login(username, password);
      else await register(username, password);
    } catch (submissionError: unknown) {
      setError(submissionError instanceof Error ? submissionError.message : 'Something went wrong.');
    } finally {
      setLoading(false);
    }
  };

  const switchMode = (nextMode: 'login' | 'register') => {
    setMode(nextMode);
    setError('');
  };

  return (
    <div className="fixed inset-0 overflow-y-auto overflow-x-hidden bg-[#050610] text-white selection:bg-indigo-400/30">
      <style>{atlasStyles}</style>
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(ellipse_at_18%_14%,rgba(51,65,198,.18),transparent_34%),radial-gradient(ellipse_at_78%_85%,rgba(147,51,234,.12),transparent_38%)]" />
      <div className="nova-atlas-grid pointer-events-none fixed inset-0 opacity-50" />
      <div className="pointer-events-none fixed inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-indigo-300/70 to-transparent" />
      <div className="pointer-events-none fixed left-[8%] top-0 h-full w-px bg-gradient-to-b from-transparent via-white/[0.06] to-transparent" />

      <main className="relative z-10 mx-auto flex min-h-full w-full max-w-[1240px] items-center px-5 py-8 sm:px-8 lg:px-12">
        <div className="grid w-full items-center gap-10 lg:grid-cols-[minmax(0,1.15fr)_minmax(380px,.75fr)] lg:gap-16">
          <section className="hidden min-w-0 lg:block" aria-label="Nova knowledge pipeline">
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
              <div className="mb-5 flex items-center gap-3 font-mono text-[10px] uppercase tracking-[0.3em] text-indigo-300/80">
                <span className="h-px w-8 bg-indigo-400" />
                Nova / Private knowledge OS
              </div>
              <h1 className="max-w-[660px] text-5xl font-semibold leading-[1.02] tracking-[-0.045em] text-white xl:text-6xl">
                Your knowledge,
                <span className="block bg-gradient-to-r from-cyan-200 via-indigo-300 to-fuchsia-300 bg-clip-text text-transparent">
                  mapped into answers.
                </span>
              </h1>
              <p className="mt-5 max-w-xl text-base leading-7 text-slate-400">
                A private workspace that turns scattered documents into traceable, citation-backed intelligence.
              </p>
            </motion.div>

            <NeuralAtlas />

            <div className="mt-5 flex items-center gap-7 border-t border-white/[0.07] pt-5">
              {[
                ['HYBRID', 'BM25 + Vector'],
                ['STREAM', 'Live generation'],
                ['GROUND', 'Source citations'],
              ].map(([label, value]) => (
                <div key={label}>
                  <div className="font-mono text-[9px] tracking-[0.22em] text-slate-600">{label}</div>
                  <div className="mt-1 text-xs font-medium text-slate-300">{value}</div>
                </div>
              ))}
            </div>
          </section>

          <motion.section
            initial={{ opacity: 0, x: 22 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.65, ease: [0.22, 1, 0.36, 1] }}
            className="mx-auto w-full max-w-[440px]"
          >
            <div className="mb-6 flex items-center gap-3 lg:hidden">
              <div className="grid h-11 w-11 place-items-center rounded-xl border border-indigo-400/20 bg-[#0d1020] shadow-[0_0_24px_rgba(129,140,248,.16)]">
                <NovaMark className="h-7 w-7" title="Nova AI" />
              </div>
              <div>
                <div className="text-lg font-semibold tracking-tight">Nova AI</div>
                <div className="font-mono text-[9px] tracking-[0.2em] text-indigo-300/70">PRIVATE KNOWLEDGE OS</div>
              </div>
            </div>

            <div className="relative overflow-hidden rounded-[26px] border border-white/[0.1] bg-[#0b0d19]/90 p-6 shadow-[0_30px_100px_rgba(0,0,0,.45)] backdrop-blur-2xl sm:p-8">
              <div className="absolute inset-x-8 top-0 h-px bg-gradient-to-r from-transparent via-indigo-300/80 to-transparent" />
              <div className="pointer-events-none absolute right-0 top-0 h-40 w-40 bg-[linear-gradient(135deg,transparent_46%,rgba(129,140,248,.08)_47%,transparent_48%)]" />

              <div className="relative mb-7">
                <div className="mb-6 flex items-center justify-between">
                  <div className="flex items-center gap-2 font-mono text-[9px] tracking-[0.22em] text-slate-500">
                    <Database className="h-3.5 w-3.5 text-indigo-300" />
                    SECURE ACCESS
                  </div>
                  <div className="flex items-center gap-1.5 rounded-md border border-emerald-300/10 bg-emerald-300/[0.05] px-2 py-1 font-mono text-[8px] tracking-[0.16em] text-emerald-300/70">
                    <ShieldCheck className="h-3 w-3" /> ENCRYPTED
                  </div>
                </div>
                <h2 className="text-3xl font-semibold tracking-[-0.035em] text-white">
                  {mode === 'login' ? 'Enter your workspace' : 'Create your workspace'}
                </h2>
                <p className="mt-2 text-sm leading-6 text-slate-500">
                  {mode === 'login'
                    ? 'Continue where your knowledge left off.'
                    : 'Build a private knowledge layer in seconds.'}
                </p>
              </div>

              <motion.form
                key={mode}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3 }}
                onSubmit={handleSubmit}
                className="relative space-y-4"
              >
                <InputField
                  label="Username"
                  type="text"
                  value={username}
                  onChange={setUsername}
                  placeholder="Enter username"
                  autoFocus
                />
                <InputField
                  label="Password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={setPassword}
                  placeholder="Enter password"
                  showToggle
                  onToggleShow={() => setShowPassword((visible) => !visible)}
                  autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
                />

                <AnimatePresence initial={false}>
                  {error && (
                    <motion.div
                      initial={{ opacity: 0, height: 0, y: -6 }}
                      animate={{ opacity: 1, height: 'auto', y: 0 }}
                      exit={{ opacity: 0, height: 0, y: -6 }}
                      className="overflow-hidden rounded-xl border border-red-400/15 bg-red-400/[0.07] px-4 py-3 text-sm text-red-200"
                    >
                      {error}
                    </motion.div>
                  )}
                </AnimatePresence>

                <motion.button
                  type="submit"
                  disabled={loading}
                  whileHover={{ y: -1 }}
                  whileTap={{ scale: 0.985 }}
                  className="group relative flex h-12 w-full items-center justify-center gap-2 overflow-hidden rounded-xl bg-[#f4f4ff] text-sm font-semibold text-[#0b0d19] shadow-[0_12px_35px_rgba(129,140,248,.16)] transition disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <span className="absolute inset-y-0 -left-1/3 w-1/3 skew-x-[-18deg] bg-gradient-to-r from-transparent via-indigo-200/80 to-transparent transition-transform duration-700 group-hover:translate-x-[430%]" />
                  {loading ? (
                    <Loader2 className="relative h-4 w-4 animate-spin" />
                  ) : mode === 'login' ? (
                    <LogIn className="relative h-4 w-4" />
                  ) : (
                    <UserPlus className="relative h-4 w-4" />
                  )}
                  <span className="relative">{loading ? 'Please wait...' : mode === 'login' ? 'Sign In' : 'Create Account'}</span>
                  {!loading && <ChevronRight className="relative h-4 w-4 transition-transform group-hover:translate-x-0.5" />}
                </motion.button>
              </motion.form>

              <div className="relative mt-6 border-t border-white/[0.07] pt-5 text-center text-sm text-slate-500">
                {mode === 'login' ? "New to Nova? " : 'Already have an account? '}
                <button
                  type="button"
                  onClick={() => switchMode(mode === 'login' ? 'register' : 'login')}
                  className="font-medium text-indigo-300 transition hover:text-white"
                >
                  {mode === 'login' ? 'Create an account' : 'Sign In'}
                </button>
              </div>
            </div>

            <div className="mt-5 flex items-center justify-between px-1 font-mono text-[8px] uppercase tracking-[0.19em] text-slate-700">
              <span>Nova protocol 2.1</span>
              <span>Private by design</span>
            </div>
          </motion.section>
        </div>
      </main>
    </div>
  );
}
