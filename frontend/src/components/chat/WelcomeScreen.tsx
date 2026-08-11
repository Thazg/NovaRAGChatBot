import { useEffect, useRef, useState } from 'react';
import { ArrowUp, Code, CornerDownLeft, FileText, Search, Zap, Database, Upload, Globe, Loader2, Sparkles } from 'lucide-react';
import { motion } from 'framer-motion';
import { api } from '../../services/api';
import { toast } from 'sonner';
import heroImage from '../../assets/hero.png';

const SUGGESTIONS = [
  {
    title: "Explore your documents",
    description: "What are the key findings in my research papers?",
    icon: <Search className="w-5 h-5" />,
    color: "from-blue-500/20 to-indigo-500/10",
    iconColor: "text-blue-400",
    border: "border-blue-500/20 hover:border-blue-500/50",
    glow: "hover:shadow-blue-500/10"
  },
  {
    title: "Summarize content",
    description: "Summarize the main points from this document.",
    icon: <FileText className="w-5 h-5" />,
    color: "from-violet-500/20 to-purple-500/10",
    iconColor: "text-violet-400",
    border: "border-violet-500/20 hover:border-violet-500/50",
    glow: "hover:shadow-violet-500/10"
  },
  {
    title: "Generate code",
    description: "Write a function to process text data.",
    icon: <Code className="w-5 h-5" />,
    color: "from-emerald-500/20 to-teal-500/10",
    iconColor: "text-emerald-400",
    border: "border-emerald-500/20 hover:border-emerald-500/50",
    glow: "hover:shadow-emerald-500/10"
  },
  {
    title: "Query knowledge base",
    description: "What topics are covered in my knowledge base?",
    icon: <Database className="w-5 h-5" />,
    color: "from-orange-500/20 to-amber-500/10",
    iconColor: "text-orange-400",
    border: "border-orange-500/20 hover:border-orange-500/50",
    glow: "hover:shadow-orange-500/10"
  }
];

const containerVariants = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.07, delayChildren: 0.4 }
  }
};

const itemVariants = {
  hidden: { opacity: 0, y: 24, scale: 0.95 },
  show: { opacity: 1, y: 0, scale: 1, transition: { type: "spring" as const, stiffness: 280, damping: 22 } }
};

export const WelcomeScreen = ({ onSelectSuggestion }: { onSelectSuggestion: (text: string) => void }) => {
  const [docCount, setDocCount] = useState<number | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.getDocuments().then(docs => setDocCount(docs.length)).catch(() => setDocCount(0));
  }, []);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const result = await api.uploadDocument(file);
      if (result.indexed) {
        toast.success(`Indexed "${result.filename}" (${result.chunks} chunks)`);
        const docs = await api.getDocuments();
        setDocCount(docs.length);
      } else {
        toast.error(result.message || 'Failed to index file');
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Upload failed');
    }
    setUploading(false);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const hasDocs = docCount !== null && docCount > 0;

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-4 md:p-8 w-full max-w-6xl mx-auto min-h-full relative select-none">
      
      {/* Background decorative blobs */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <motion.div animate={{ x: [0, 36, 0], y: [0, -20, 0] }} transition={{ duration: 14, repeat: Infinity }} className="absolute top-1/4 left-1/3 w-96 h-96 bg-primary/10 rounded-full blur-3xl -translate-x-1/2 -translate-y-1/2" />
        <motion.div animate={{ x: [0, -28, 0], y: [0, 28, 0] }} transition={{ duration: 17, repeat: Infinity }} className="absolute bottom-1/4 right-1/3 w-72 h-72 bg-cyan-500/10 rounded-full blur-3xl translate-x-1/2 translate-y-1/2" />
      </div>

      {/* Hero section */}
      <motion.div
        initial={{ opacity: 0, y: 32 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
        className="nova-panel flex flex-col items-center text-center space-y-5 md:space-y-6 mb-8 md:mb-10 relative z-10 rounded-[2rem] px-7 py-8 md:px-14 md:py-10 overflow-hidden w-full max-w-[860px]"
      >
        <div className="absolute inset-x-16 top-0 h-px bg-gradient-to-r from-transparent via-primary/70 to-transparent" />
        {/* Logo/icon */}
        <motion.div
          initial={{ opacity: 0, scale: 0.7 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.55, delay: 0.1, type: "spring", stiffness: 260, damping: 20 }}
          className="relative"
        >
          <motion.div
            animate={{ y: [0, -8, 0], rotate: [-1.5, 1.5, -1.5] }}
            transition={{ duration: 6, repeat: Infinity, ease: 'easeInOut' }}
            className="relative w-[116px] h-[96px] md:w-[138px] md:h-[112px] flex items-center justify-center"
          >
            <div className="absolute inset-4 rounded-full bg-primary/20 blur-2xl" />
            <img src={heroImage} alt="Layered knowledge workspace" className="relative w-full h-full object-contain drop-shadow-[0_18px_30px_rgba(124,58,237,0.28)]" />
          </motion.div>
          <div className="absolute left-1/2 top-1/2 h-32 w-32 -translate-x-1/2 -translate-y-1/2 rounded-full border border-primary/15" />
          <motion.div animate={{ rotate: 360 }} transition={{ duration: 10, repeat: Infinity, ease: 'linear' }} className="absolute left-1/2 top-1/2 h-36 w-36 -translate-x-1/2 -translate-y-1/2 rounded-full border border-dashed border-primary/20">
            <Sparkles className="absolute -top-1 left-1/2 h-3.5 w-3.5 text-primary" />
          </motion.div>
          {/* Status pulse */}
          <motion.div
            className="absolute -top-1 -right-1 w-5 h-5 bg-emerald-500 rounded-full border-[3px] border-background flex items-center justify-center"
            animate={{ scale: [1, 1.15, 1] }}
            transition={{ duration: 2.5, repeat: Infinity, ease: "easeInOut" }}
          />
          {/* Outer glow ring */}
          <motion.div
            className="absolute inset-0 rounded-2xl border border-primary/20"
            animate={{ opacity: [0.3, 0.8, 0.3] }}
            transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
          />
        </motion.div>

        {/* Title */}
        <div className="space-y-3">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.22 }}
            className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-primary/10 border border-primary/20 text-primary text-xs font-semibold tracking-[0.15em] uppercase"
          >
            <Zap className="w-3 h-3 fill-current" />
              Nova knowledge workspace
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3, duration: 0.5 }}
            className="text-[2.15rem] sm:text-[3rem] md:text-[3.75rem] font-bold tracking-[-0.045em] leading-[0.98]"
          >
            <span className="bg-clip-text text-transparent bg-gradient-to-br from-foreground via-foreground/95 to-foreground/70">
              Make your knowledge
            </span>
            <br />
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-primary via-violet-400 to-primary/80">
              come alive.
            </span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.45 }}
            className="text-base text-muted-foreground/90 max-w-md leading-relaxed mx-auto"
          >
            {hasDocs
              ? "Explore every document, connect the evidence, and turn dense information into clear answers."
              : "Add your first document and watch Nova turn it into a searchable, conversational workspace."}
          </motion.p>
        </div>
      </motion.div>

      {/* Empty state: upload prompt */}
      {!hasDocs && docCount === 0 && (
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.6 }}
          className="flex flex-col items-center gap-4 w-full max-w-md relative z-10"
        >
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileUpload}
            className="hidden"
            accept=".pdf,.md,.markdown,.rst,.txt,.py,.docx,.ipynb"
          />
          <motion.button
            whileHover={{ scale: 1.02, y: -2 }}
            whileTap={{ scale: 0.985 }}
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="group flex items-center gap-4 w-full p-5 rounded-2xl border border-dashed border-primary/40 bg-primary/5 hover:bg-primary/10 backdrop-blur-sm shadow-sm hover:shadow-lg transition-all duration-250 text-left relative overflow-hidden"
          >
            <div className="p-2.5 rounded-xl bg-background/60 border border-border/50 shadow-sm group-hover:scale-110 transition-transform duration-300 text-primary">
              {uploading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Upload className="w-5 h-5" />}
            </div>
            <div className="space-y-1 flex-1 min-w-0">
              <p className="font-semibold text-sm text-foreground/90">Upload a document</p>
              <p className="text-[13px] text-muted-foreground/75 leading-snug">
                Upload PDF, DOCX, Markdown, or TXT files to build your knowledge base
              </p>
            </div>
          </motion.button>

          <motion.button
            whileHover={{ scale: 1.02, y: -2 }}
            whileTap={{ scale: 0.985 }}
            onClick={() => onSelectSuggestion("search for artificial intelligence")}
            className="group flex items-center gap-4 w-full p-5 rounded-2xl border border-violet-500/20 bg-violet-500/5 hover:bg-violet-500/10 backdrop-blur-sm shadow-sm hover:shadow-lg transition-all duration-250 text-left relative overflow-hidden"
          >
            <div className="p-2.5 rounded-xl bg-background/60 border border-border/50 shadow-sm group-hover:scale-110 transition-transform duration-300 text-violet-400">
              <Globe className="w-5 h-5" />
            </div>
            <div className="space-y-1 flex-1 min-w-0">
              <p className="font-semibold text-sm text-foreground/90">Search the web</p>
              <p className="text-[13px] text-muted-foreground/75 leading-snug">
                Say "search for &lt;topic&gt;" and I'll find and download relevant PDFs automatically
              </p>
            </div>
          </motion.button>
        </motion.div>
      )}

      {/* Has docs: suggestion cards */}
      {hasDocs && (
        <motion.div
          variants={containerVariants}
          initial="hidden"
          animate="show"
          className="grid grid-cols-1 sm:grid-cols-2 gap-2 md:gap-3 w-full max-w-[780px] relative z-10 px-2 md:px-0"
        >
          {SUGGESTIONS.map((suggestion, idx) => (
            <motion.button
              key={idx}
              variants={itemVariants}
              whileHover={{ scale: 1.02, y: -3 }}
              whileTap={{ scale: 0.985 }}
              onClick={() => onSelectSuggestion(suggestion.description)}
              className={`nova-panel nova-card-hover group flex items-start gap-4 p-5 rounded-2xl text-left relative overflow-hidden ${suggestion.border}`}
            >
              <div className={`absolute inset-0 bg-gradient-to-br ${suggestion.color} opacity-0 group-hover:opacity-100 transition-opacity duration-300 rounded-2xl`} />
              <div className={`relative z-10 p-2.5 rounded-xl bg-background/60 border border-border/50 shadow-sm group-hover:scale-110 transition-transform duration-300 ${suggestion.iconColor}`}>
                {suggestion.icon}
              </div>
              <div className="relative z-10 space-y-1.5 flex-1 min-w-0">
                <p className="font-semibold text-sm text-foreground/90 group-hover:text-foreground transition-colors">
                  {suggestion.title}
                </p>
                <p className="text-[13px] text-muted-foreground/75 leading-snug">
                  {suggestion.description}
                </p>
              </div>
            </motion.button>
          ))}
        </motion.div>
      )}

      {/* Loading state */}
      {docCount === null && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex items-center gap-2 text-sm text-muted-foreground/60 relative z-10"
        >
          <Loader2 className="h-4 w-4 animate-spin" />
          Checking knowledge base...
        </motion.div>
      )}

      {/* Keyboard hint */}
      {hasDocs && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.0 }}
          className="nova-shortcut-bar relative z-10 mt-8 hidden items-center gap-3 rounded-2xl px-4 py-3 text-[12px] md:flex"
        >
          <div className="flex items-center gap-2">
            <kbd className="nova-keycap">
              <CornerDownLeft className="h-3.5 w-3.5 text-primary" />
              Enter
            </kbd>
            <span className="font-semibold text-foreground/70">Send</span>
          </div>
          <span className="h-5 w-px bg-border/80" />
          <div className="flex items-center gap-2">
            <kbd className="nova-keycap">
              <ArrowUp className="h-3.5 w-3.5 text-primary" />
              Shift
              <span className="text-muted-foreground">+</span>
              <CornerDownLeft className="h-3.5 w-3.5 text-primary" />
            </kbd>
            <span className="font-semibold text-foreground/70">New line</span>
          </div>
          <span className="h-5 w-px bg-border/80" />
          <div className="flex items-center gap-2">
            <kbd className="nova-keycap">Ctrl K</kbd>
            <span className="flex items-center gap-1 font-semibold text-foreground/70">
              <Search className="h-3.5 w-3.5 text-primary" />
              Search
            </span>
          </div>
        </motion.div>
      )}
    </div>
  );
};
