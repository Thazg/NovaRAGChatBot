import { useCallback, useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Upload, Loader2, AlertCircle, RefreshCw, LogOut } from 'lucide-react';
import { api } from '../../services/api';
import heroImage from '../../assets/hero.png';
import { useChatStore } from '../../store/useChatStore';

export const UploadGate = ({ onContinue }: { onContinue: () => void }) => {
  const [, setDocuments] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const logout = useChatStore((s) => s.logout);

  const loadDocs = useCallback(async () => {
    setError('');
    setLoading(true);
    try {
      const docs = await api.getDocuments();
      setDocuments(docs);
      if (docs.length > 0) {
        onContinue();
      }
    } catch {
      setDocuments([]);
      setError('Nova could not load your workspace. Check the connection and try again.');
    } finally {
      setLoading(false);
    }
  }, [onContinue]);

  useEffect(() => { loadDocs(); }, [loadDocs]);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      await api.uploadDocument(file);
      await loadDocs();
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : 'Upload failed. Please try again.');
    }
    setUploading(false);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="nova-shell nova-upload-shell fixed inset-0 z-50 h-[100dvh] w-screen overflow-y-auto bg-background"
      >
        <div className="nova-grid" />
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <motion.div
            animate={{ x: [0, 42, -18, 0], y: [0, -26, 18, 0], scale: [1, 1.12, 0.96, 1] }}
            transition={{ duration: 18, repeat: Infinity, ease: "easeInOut" }}
            className="absolute top-[8%] left-[12%] h-72 w-72 rounded-full bg-violet-500/20 blur-3xl"
          />
          <motion.div
            animate={{ x: [0, -48, 16, 0], y: [0, 32, -20, 0], scale: [1, 0.94, 1.1, 1] }}
            transition={{ duration: 21, repeat: Infinity, ease: "easeInOut" }}
            className="absolute bottom-[6%] right-[8%] h-80 w-80 rounded-full bg-sky-400/20 blur-3xl"
          />
        </div>

        <div className="nova-viewport-center">
          <motion.div
            initial={{ opacity: 0, y: 24, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ delay: 0.15, type: "spring", stiffness: 300, damping: 28 }}
            className="nova-panel nova-upload-panel relative flex w-full max-w-xl flex-col items-center overflow-hidden rounded-[2rem] px-6 py-9 text-center md:px-11 md:py-11"
          >
          <div className="absolute inset-x-12 top-0 h-[2px] bg-gradient-to-r from-transparent via-primary to-transparent" />
          <div className="pointer-events-none absolute -right-20 -top-24 h-52 w-52 rounded-full bg-violet-400/15 blur-3xl" />
          <motion.div
            initial={{ opacity: 0, scale: 0.7 }}
            animate={{ opacity: 1, scale: 1, y: [0, -7, 0] }}
            transition={{
              opacity: { delay: 0.25, duration: 0.4 },
              scale: { delay: 0.25, type: "spring", stiffness: 260, damping: 20 },
              y: { delay: 0.8, duration: 5, repeat: Infinity, ease: "easeInOut" },
            }}
            className="w-[132px] h-[104px] flex items-center justify-center mb-6 relative"
          >
            <div className="absolute inset-5 rounded-full bg-primary/20 blur-2xl" />
            <img src={heroImage} alt="Nova knowledge layers" className="relative h-full w-full object-contain drop-shadow-[0_18px_26px_rgba(124,58,237,0.3)]" />
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.35, duration: 0.5 }}
            className="text-3xl md:text-4xl font-bold tracking-tight mb-3"
          >
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-foreground via-foreground/95 to-foreground/70">
              Welcome to{" "}
            </span>
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-primary via-violet-400 to-primary/80">
              Nova
            </span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.45 }}
            className="text-base font-medium text-muted-foreground mb-8 max-w-sm"
          >
            Your knowledge base is empty. Upload at least one document to get started.
          </motion.p>

          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileUpload}
            className="hidden"
            accept=".pdf,.md,.markdown,.rst,.txt,.py,.docx,.ipynb"
          />

          <motion.button
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.55 }}
            whileHover={{ scale: 1.02, y: -2 }}
            whileTap={{ scale: 0.985 }}
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="nova-upload-dropzone group flex items-center gap-4 w-full max-w-sm p-5 rounded-2xl border-2 border-dashed border-primary/45 bg-primary/10 hover:bg-primary/15 backdrop-blur-sm transition-all duration-300 text-left relative overflow-hidden"
          >
            <div className="relative z-10 p-3 rounded-xl bg-gradient-to-br from-primary to-violet-600 shadow-[0_10px_24px_-8px_rgba(112,78,250,0.75)] group-hover:scale-110 group-hover:-rotate-3 transition-transform duration-300 text-white">
              {uploading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Upload className="w-5 h-5" />}
            </div>
            <div className="relative z-10 space-y-1 flex-1 min-w-0">
              <p className="font-bold text-sm text-foreground">
                {uploading ? "Uploading..." : "Upload a document"}
              </p>
              <p className="text-[13px] font-medium text-muted-foreground leading-snug">
                PDF, DOCX, Markdown, TXT, or Python files
              </p>
            </div>
          </motion.button>

          {error && (
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mt-5 flex w-full max-w-sm items-start gap-2.5 rounded-xl border border-destructive/20 bg-destructive/5 p-3 text-left text-xs text-destructive">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span className="flex-1 leading-relaxed">{error}</span>
              <button onClick={loadDocs} className="rounded-lg p-1 hover:bg-destructive/10" aria-label="Retry"><RefreshCw className="h-3.5 w-3.5" /></button>
            </motion.div>
          )}

          {loading && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex items-center gap-2 text-sm text-muted-foreground/50 mt-6"
            >
              <Loader2 className="h-4 w-4 animate-spin" />
              Checking documents...
            </motion.div>
          )}

          <button onClick={logout} className="mt-5 inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-muted-foreground/80 transition-colors hover:bg-secondary hover:text-foreground">
            <LogOut className="h-3.5 w-3.5" /> Sign out
          </button>
          </motion.div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
};
