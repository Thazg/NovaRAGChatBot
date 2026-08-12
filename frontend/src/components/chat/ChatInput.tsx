import React, { useRef, useEffect, useState } from 'react';
import { Send, Square, Paperclip, Mic, Loader2 } from 'lucide-react';
import { Button } from '../ui/button';
import { Textarea } from '../ui/textarea';
import { cn } from '../../lib/utils';
import { useChatStore } from '../../store/useChatStore';
import { motion, AnimatePresence } from 'framer-motion';
import { toast } from 'sonner';
import { api } from '../../services/api';

interface ChatInputProps {
  onSend: (message: string) => void;
  onStop: () => void;
}

interface SpeechRecognitionResultEventLike {
  results: ArrayLike<{ 0: { transcript: string } }>;
}

interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
  onresult: ((event: SpeechRecognitionResultEventLike) => void) | null;
  start: () => void;
  stop: () => void;
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;
type SpeechWindow = Window & {
  SpeechRecognition?: SpeechRecognitionConstructor;
  webkitSpeechRecognition?: SpeechRecognitionConstructor;
};

export const ChatInput = ({ onSend, onStop }: ChatInputProps) => {
  const [input, setInput] = React.useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const isStreaming = useChatStore((state) => state.isStreaming);
  const isLoading = useChatStore((state) => state.isLoading);
  const setSidebarActiveTab = useChatStore((state) => state.setSidebarActiveTab);
  const language = useChatStore((state) => state.language);
  const isBusy = isStreaming || isLoading;
  const [isRecording, setIsRecording] = useState(false);
  const recognitionRef = useRef<{
    start: () => void;
    stop: () => void;
  } | null>(null);

  const prevStreamingRef = useRef(isStreaming);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      const newH = Math.min(textareaRef.current.scrollHeight, 200);
      textareaRef.current.style.height = `${newH}px`;
    }
  }, [input]);

  // Auto-focus input when streaming completes
  useEffect(() => {
    if (prevStreamingRef.current && !isStreaming) {
      textareaRef.current?.focus();
    }
    prevStreamingRef.current = isStreaming;
  }, [isStreaming]);

  useEffect(() => () => recognitionRef.current?.stop(), []);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const result = await api.uploadDocument(file);
      const job = result.job_id ? await api.waitForIndexJob(result.job_id) : null;
      if (result.indexed || job?.result?.indexed) {
        toast.success(`Indexed "${result.filename}" (${job?.result?.chunks ?? result.chunks ?? 0} chunks)`);
        setSidebarActiveTab('documents');
      } else {
        toast.error(result.message || 'Failed to index file');
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Upload failed');
    }
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const toggleRecording = () => {
    const speechWindow = window as SpeechWindow;
    const SpeechRecognitionAPI = speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition;
    if (!SpeechRecognitionAPI) {
      toast.error('Speech recognition not supported in this browser');
      return;
    }

    if (isRecording) {
      recognitionRef.current?.stop();
      setIsRecording(false);
      return;
    }

    const recognition = new SpeechRecognitionAPI();
    recognition.lang = language === 'english'
      ? 'en-US'
      : language === 'vietnamese'
        ? 'vi-VN'
        : (navigator.language || 'en-US');
    recognition.continuous = false;
    recognition.interimResults = false;

    recognition.onstart = () => setIsRecording(true);
    recognition.onend = () => setIsRecording(false);
    recognition.onerror = () => {
      setIsRecording(false);
      toast.error('Microphone access denied or error occurred');
    };
    recognition.onresult = (event: SpeechRecognitionResultEventLike) => {
      const transcript = event.results[0][0].transcript;
      setInput((prev) => (prev ? prev + ' ' + transcript : transcript));
    };

    recognitionRef.current = recognition;
    recognition.start();
  };

  const handleSubmit = () => {
    if (!input.trim() || isBusy) return;
    onSend(input.trim());
    setInput('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const charCount = input.length;
  const showCharCount = charCount > 200;

  return (
    <div className="relative w-full max-w-3xl mx-auto flex flex-col gap-1.5 md:gap-2">
      <motion.div
        layout
        initial={{ y: 16, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{
          layout: { type: "spring", stiffness: 260, damping: 28, mass: 0.7 },
          y: { type: "spring", stiffness: 320, damping: 28 },
          opacity: { duration: 0.28 },
        }}
        className={cn(
          "relative flex flex-col w-full rounded-xl md:rounded-2xl border bg-card/80 backdrop-blur-2xl transition-all duration-300",
          isBusy
            ? "border-primary/30 shadow-lg shadow-primary/10"
            : "border-border/50 shadow-md hover:border-border/70 focus-within:border-primary/40 focus-within:shadow-lg focus-within:shadow-primary/10"
        )}
      >
        {/* Streaming glow effect */}
        {isBusy && (
          <motion.div
            className="absolute inset-0 rounded-2xl pointer-events-none"
            animate={{ opacity: [0.3, 0.7, 0.3] }}
            transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
            style={{
              boxShadow: '0 0 0 1px hsl(var(--primary) / 0.2), 0 0 24px hsl(var(--primary) / 0.08)',
            }}
          />
        )}

        {/* Input row */}
        <div className="flex items-end gap-1.5 md:gap-2 px-2 md:px-3 py-2 md:py-2.5">
          {/* Attach button */}
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileUpload}
            className="hidden"
            accept=".pdf,.md,.markdown,.rst,.txt,.py,.docx,.ipynb"
          />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-9 w-9 md:h-8 md:w-8 text-muted-foreground hover:text-foreground hover:bg-muted/60 rounded-xl transition-colors shrink-0 mb-0.5"
            disabled={isBusy}
            onClick={() => fileInputRef.current?.click()}
            aria-label="Attach file"
          >
            <Paperclip className="h-4 w-4" />
          </Button>

          {/* Textarea */}
          <Textarea
            ref={textareaRef}
            value={input}
            onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask Nova anything..."
            className="min-h-[40px] md:min-h-[36px] max-h-[200px] w-full resize-none border-0 bg-transparent py-2 md:py-1.5 px-0 focus-visible:ring-0 shadow-none text-[15px] md:text-[14.5px] placeholder:text-muted-foreground/60 font-normal leading-relaxed"
            disabled={isBusy}
            rows={1}
            maxLength={4000}
            aria-label="Message input"
          />

          {/* Right controls */}
          <div className="mb-0.5 flex shrink-0 items-center gap-1">
            {/* A fixed mic slot prevents the send button from jumping sideways. */}
            <div className="relative h-9 w-9 md:h-8 md:w-8">
              <AnimatePresence initial={false}>
                {!input.trim() && !isBusy && (
                  <motion.div
                    className="absolute inset-0"
                    initial={{ opacity: 0, scale: 0.78, x: 5, filter: 'blur(4px)' }}
                    animate={{ opacity: 1, scale: 1, x: 0, filter: 'blur(0px)' }}
                    exit={{ opacity: 0, scale: 0.82, x: 5, filter: 'blur(4px)' }}
                    transition={{ type: "spring", stiffness: 360, damping: 28, mass: 0.65 }}
                  >
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={toggleRecording}
                    className={cn(
                      "h-9 w-9 md:h-8 md:w-8 rounded-xl transition-colors flex",
                      isRecording
                        ? "text-red-500 bg-red-500/10 hover:bg-red-500/20"
                        : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
                    )}
                    aria-label="Voice input"
                  >
                    {isRecording ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mic className="h-4 w-4" />}
                  </Button>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* Send and stop morph in place without changing control width. */}
            <div className="relative h-9 w-9 md:h-8 md:w-8">
              <AnimatePresence initial={false} mode="sync">
                {isBusy ? (
                  <motion.div
                    key="stop"
                    className="absolute inset-0"
                    initial={{ scale: 0.72, opacity: 0, rotate: -35, filter: 'blur(3px)' }}
                    animate={{ scale: 1, opacity: 1, rotate: 0, filter: 'blur(0px)' }}
                    exit={{ scale: 0.72, opacity: 0, rotate: 35, filter: 'blur(3px)' }}
                    transition={{ type: "spring", stiffness: 340, damping: 25, mass: 0.7 }}
                  >
                  <Button
                    type="button"
                    onClick={onStop}
                    size="icon"
                    className="h-9 w-9 md:h-8 md:w-8 rounded-xl bg-destructive/10 hover:bg-destructive/20 text-destructive transition-all border border-destructive/20 hover:scale-105"
                    aria-label="Stop generation"
                  >
                    <Square className="h-4 w-4 md:h-3.5 md:w-3.5 fill-current" />
                  </Button>
                  </motion.div>
                ) : (
                  <motion.div
                    key="send"
                    className="absolute inset-0"
                    initial={{ scale: 0.72, opacity: 0, rotate: -35, filter: 'blur(3px)' }}
                    animate={{ scale: 1, opacity: 1, rotate: 0, filter: 'blur(0px)' }}
                    exit={{ scale: 0.72, opacity: 0, rotate: 35, filter: 'blur(3px)' }}
                    transition={{ type: "spring", stiffness: 340, damping: 25, mass: 0.7 }}
                  >
                  <Button
                    type="button"
                    onClick={handleSubmit}
                    disabled={!input.trim()}
                    size="icon"
                    className={cn(
                      "h-9 w-9 md:h-8 md:w-8 rounded-xl transition-all shadow-sm",
                      input.trim()
                        ? "bg-primary text-primary-foreground hover:bg-primary/90 hover:scale-105 hover:shadow-md hover:shadow-primary/25"
                        : "bg-muted/60 text-muted-foreground/50 cursor-not-allowed"
                    )}
                    aria-label="Send message"
                  >
                    <Send className="h-4 w-4 md:h-3.5 md:w-3.5" />
                  </Button>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </div>

        {/* Footer row */}
        <div className="flex items-center justify-between px-4 pb-2 pt-0">
          <span className="text-[11px] text-muted-foreground/40 font-medium">
            {isBusy ? (
              <motion.span
                animate={{ opacity: [0.5, 1, 0.5] }}
                transition={{ repeat: Infinity, duration: 1.5 }}
              >
                Nova is generating...
              </motion.span>
            ) : (
              "Nova can make mistakes. Verify important information."
            )}
          </span>
          {showCharCount && (
            <span className={cn(
              "text-[11px] font-mono tabular-nums",
              charCount > 1800 ? "text-red-400" : charCount > 1200 ? "text-amber-400" : "text-muted-foreground/40"
            )}>
              {charCount.toLocaleString()}
            </span>
          )}
        </div>
      </motion.div>
    </div>
  );
};
