import { memo, useState, type CSSProperties, type ComponentProps } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { PrismLight as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import javascript from 'react-syntax-highlighter/dist/esm/languages/prism/javascript';
import typescript from 'react-syntax-highlighter/dist/esm/languages/prism/typescript';
import python from 'react-syntax-highlighter/dist/esm/languages/prism/python';
import bash from 'react-syntax-highlighter/dist/esm/languages/prism/bash';
import json from 'react-syntax-highlighter/dist/esm/languages/prism/json';
import css from 'react-syntax-highlighter/dist/esm/languages/prism/css';
import markup from 'react-syntax-highlighter/dist/esm/languages/prism/markup';
import { User, Copy, Check, ThumbsUp, ThumbsDown, RotateCcw, Sparkles, Share2 } from 'lucide-react';
import type { Message } from '../../types';
import { cn } from '../../lib/utils';
import { Button } from '../ui/button';
import { motion } from 'framer-motion';
import { useChatStore } from '../../store/useChatStore';
import { toast } from 'sonner';

SyntaxHighlighter.registerLanguage('javascript', javascript);
SyntaxHighlighter.registerLanguage('js', javascript);
SyntaxHighlighter.registerLanguage('typescript', typescript);
SyntaxHighlighter.registerLanguage('ts', typescript);
SyntaxHighlighter.registerLanguage('tsx', typescript);
SyntaxHighlighter.registerLanguage('python', python);
SyntaxHighlighter.registerLanguage('py', python);
SyntaxHighlighter.registerLanguage('bash', bash);
SyntaxHighlighter.registerLanguage('shell', bash);
SyntaxHighlighter.registerLanguage('json', json);
SyntaxHighlighter.registerLanguage('css', css);
SyntaxHighlighter.registerLanguage('html', markup);

interface ChatBubbleProps {
  message: Message;
  isStreaming?: boolean;
  onRegenerate?: () => void;
}

export const ChatBubble = memo(({ message, isStreaming, onRegenerate }: ChatBubbleProps) => {
  const [copied, setCopied] = useState(false);
  const { avatar, setMessageFeedback, currentConversationId } = useChatStore();
  const isUser = message.role === 'user';

  const handleCopy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      toast.success('Copied to clipboard');
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error('Clipboard access is unavailable');
    }
  };

  const handleFeedback = (feedback: 'like' | 'dislike') => {
    if (!currentConversationId) return;
    const newFeedback = message.feedback === feedback ? null : feedback;
    setMessageFeedback(currentConversationId, message.id, newFeedback);
  };

  const handleShare = async () => {
    try {
      if (navigator.share) {
        await navigator.share({ title: 'Nova AI response', text: message.content });
      } else {
        await handleCopy(message.content);
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return;
      toast.error('Could not share this message');
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
      className={cn("group my-4 flex w-full gap-3", isUser ? "justify-end" : "justify-start")}
    >
      <div className={cn("flex w-full max-w-[880px] gap-3", isUser ? "flex-row-reverse" : "flex-row")}>
        
        {/* Avatar */}
        <div className={cn(
          "z-10 mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center overflow-hidden rounded-[10px] border",
          isUser
            ? "border-border/50 bg-muted text-muted-foreground"
            : "border-primary/25 bg-primary/10 text-primary"
        )}>
          {isUser ? (
            avatar ? (
              <img src={avatar} alt="User" className="h-full w-full object-cover" />
            ) : (
              <User className="h-3.5 w-3.5" />
            )
          ) : (
            <Sparkles className="h-4 w-4" />
          )}
        </div>

        {/* Message bubble container */}
        <div className={cn(
          "group relative flex min-w-0 flex-col",
          isUser ? "w-auto max-w-[76%] items-end" : "w-full max-w-[800px] items-start"
        )}>
          
          {/* Bubble */}
          <div className={cn(
            "prose prose-sm dark:prose-invert w-full max-w-none break-words rounded-[14px] px-4 py-3 shadow-sm transition-colors",
            isUser
              ? "rounded-tr-[5px] border border-primary/20 bg-primary/10 text-foreground"
              : "rounded-tl-[5px] border border-border/50 bg-card/90 text-foreground"
          )}>
            {isUser || !isStreaming ? (
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  code({ inline, className, children, style: _inlineStyle, ...props }: ComponentProps<'code'> & { inline?: boolean }) {
                    const match = /language-(\w+)/.exec(className || '');
                    const language = match ? match[1] : '';
                    const codeString = String(children).replace(/\n$/, '');

                    if (!inline && match) {
                      return (
                        <div className="relative group/code my-4 rounded-xl overflow-hidden border border-border/40 shadow-lg bg-zinc-950">
                          <div className="flex items-center justify-between px-4 py-2 bg-zinc-900/90 border-b border-zinc-800/60">
                            <div className="flex items-center gap-2">
                              <div className="flex gap-1.5">
                                <div className="w-3 h-3 rounded-full bg-red-500/70" />
                                <div className="w-3 h-3 rounded-full bg-yellow-500/70" />
                                <div className="w-3 h-3 rounded-full bg-green-500/70" />
                              </div>
                              <span className="text-[11px] text-zinc-400 font-mono ml-1 tracking-wider uppercase opacity-70">
                                {language || 'code'}
                              </span>
                            </div>
                            <button
                              onClick={() => handleCopy(codeString)}
                              className="flex items-center gap-1.5 text-[11px] text-zinc-400 hover:text-zinc-200 transition-colors px-2 py-1 rounded-md hover:bg-zinc-800/80 font-medium"
                            >
                              {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                              {copied ? 'Copied!' : 'Copy'}
                            </button>
                          </div>
                          <SyntaxHighlighter
                            style={oneDark as { [key: string]: CSSProperties }}
                            language={language}
                            PreTag="div"
                            customStyle={{
                              margin: 0,
                              padding: '1.125rem 1.25rem',
                              background: 'transparent',
                              fontSize: '0.8375rem',
                              lineHeight: '1.65',
                            }}
                          >
                            {codeString}
                          </SyntaxHighlighter>
                        </div>
                      );
                    }
                    return (
                      <code
                        className="bg-primary/10 text-primary/90 px-1.5 py-0.5 rounded-md text-[0.82em] font-mono font-medium border border-primary/15"
                        {...props}
                      >
                        {children}
                      </code>
                    );
                  },
                  table: ({ children }) => (
                    <div className="overflow-x-auto my-4 rounded-xl border border-border/40 shadow-sm">
                      <table className="border-collapse w-full bg-muted/20">{children}</table>
                    </div>
                  ),
                  thead: ({ children }) => <thead className="bg-muted/50">{children}</thead>,
                  th: ({ children }) => (
                    <th className="border-b border-border/40 px-4 py-2.5 text-left text-[13px] font-semibold text-foreground/90">
                      {children}
                    </th>
                  ),
                  td: ({ children }) => (
                    <td className="border-b border-border/25 px-4 py-2.5 text-[13px] text-foreground/80">
                      {children}
                    </td>
                  ),
                  tr: ({ children }) => (
                    <tr className="hover:bg-muted/30 transition-colors">{children}</tr>
                  ),
                  p: ({ children }) => (
                    <p className="mb-3.5 last:mb-0 leading-[1.8] text-[14.5px] text-foreground/92">
                      {children}
                    </p>
                  ),
                  h1: ({ children }) => <h1 className="text-xl font-bold mt-5 mb-3 text-foreground">{children}</h1>,
                  h2: ({ children }) => <h2 className="text-lg font-semibold mt-4 mb-2.5 text-foreground">{children}</h2>,
                  h3: ({ children }) => <h3 className="text-base font-semibold mt-3.5 mb-2 text-foreground">{children}</h3>,
                  ul: ({ children }) => <ul className="my-3 space-y-1.5 pl-5 list-disc marker:text-primary/60">{children}</ul>,
                  ol: ({ children }) => <ol className="my-3 space-y-1.5 pl-5 list-decimal marker:text-primary/60">{children}</ol>,
                  li: ({ children }) => <li className="text-[14px] text-foreground/88 leading-relaxed">{children}</li>,
                  strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
                  a: ({ href, children }) => (
                    <a
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-primary hover:text-primary/80 underline underline-offset-3 decoration-primary/30 hover:decoration-primary/70 transition-all font-medium"
                    >
                      {children}
                    </a>
                  ),
                  blockquote: ({ children }) => (
                    <blockquote className="border-l-[3px] border-primary/40 pl-4 py-1 my-4 bg-primary/5 rounded-r-xl italic text-foreground/75 text-[14px]">
                      {children}
                    </blockquote>
                  ),
                  hr: () => <hr className="my-4 border-border/40" />,
                }}
              >
                {message.content || (isStreaming ? '\u200b' : '')}
              </ReactMarkdown>
            ) : (
              <p className="leading-[1.8] text-[14.5px] text-foreground/92 whitespace-pre-wrap">
                {message.content || '\u200b'}
              </p>
            )}

            {/* Streaming indicator */}
            {isStreaming && (
              <div className="flex items-center gap-2 mt-2.5 pt-2 border-t border-border/30">
                <motion.div className="flex items-center gap-1">
                  {[0, 1, 2].map((i) => (
                    <motion.div
                      key={i}
                      className="w-1.5 h-1.5 rounded-full bg-primary/60"
                      animate={{ opacity: [0.3, 1, 0.3], scale: [0.8, 1.1, 0.8] }}
                      transition={{
                        repeat: Infinity,
                        duration: 1.2,
                        delay: i * 0.2,
                        ease: "easeInOut"
                      }}
                    />
                  ))}
                </motion.div>
                <span className="text-[12px] text-muted-foreground/70 font-medium">Nova is thinking...</span>
              </div>
            )}
          </div>

          {/* Knowledge panel - removed */}

          {/* Action buttons (always visible on mobile, on hover on desktop) */}
          <div className={cn(
            "flex items-center gap-0.5 mt-1.5 opacity-100 md:opacity-0 md:group-hover:opacity-100 transition-all duration-200",
            isUser ? "flex-row-reverse" : "flex-row"
          )}>
            <span className="px-1.5 text-xs font-medium tabular-nums text-muted-foreground/70">
              {new Date(message.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
            {!isUser && !isStreaming && (
              <>
                <ActionButton
                  onClick={() => handleCopy(message.content)}
                  label="Copy"
                  icon={copied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
                  active={copied}
                />
                <ActionButton
                  onClick={() => handleFeedback('like')}
                  label="Like"
                  icon={<ThumbsUp className="h-3.5 w-3.5" />}
                  active={message.feedback === 'like'}
                  activeClass="text-emerald-400 bg-emerald-400/10"
                />
                <ActionButton
                  onClick={() => handleFeedback('dislike')}
                  label="Dislike"
                  icon={<ThumbsDown className="h-3.5 w-3.5" />}
                  active={message.feedback === 'dislike'}
                  activeClass="text-red-400 bg-red-400/10"
                />
                {onRegenerate && (
                  <ActionButton
                    onClick={onRegenerate}
                    label="Regenerate"
                    icon={<RotateCcw className="h-3.5 w-3.5" />}
                  />
                )}
                <ActionButton
                  onClick={handleShare}
                  label="Share"
                  icon={<Share2 className="h-3.5 w-3.5" />}
                />
              </>
            )}
          </div>
        </div>
      </div>
    </motion.div>
  );
});

// Helper micro-button component
const ActionButton = ({
  onClick,
  label,
  icon,
  active,
  activeClass,
}: {
  onClick: () => void;
  label: string;
  icon: React.ReactNode;
  active?: boolean;
  activeClass?: string;
}) => (
  <Button
    variant="ghost"
    size="icon"
    className={cn(
      "h-8 w-8 rounded-[10px] border border-transparent text-muted-foreground shadow-none transition-colors hover:border-border/40 hover:bg-muted/60 hover:text-foreground",
      active && (activeClass || "text-primary bg-primary/10")
    )}
    onClick={onClick}
    aria-label={label}
  >
    {icon}
  </Button>
);

ChatBubble.displayName = 'ChatBubble';
