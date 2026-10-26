import { useCallback, useEffect, useRef, useState } from 'react';
import { useChatStore } from '../../store/useChatStore';
import { ChatBubble } from './ChatBubble';
import { ChatInput } from './ChatInput';
import { WelcomeScreen } from './WelcomeScreen';
import { GlobalSearch } from './GlobalSearch';
import { api } from '../../services/api';
import { toast } from 'sonner';
import { motion } from 'framer-motion';
import { FolderOpen, Globe2, Loader2, RefreshCw } from 'lucide-react';
import { Button } from '../ui/button';

const errorMessage = (error: unknown): string => error instanceof Error ? error.message : 'Unknown error';
type ActiveRequest = { controller: AbortController; conversationId: string; messageId: string };

export const ChatArea = () => {
  const {
    conversations,
    currentConversationId,
    addMessage,
    appendStreamToMessage,
    updateMessage,
    setIsStreaming,
    setIsLoading,
    createConversation,
    regenerateLastMessage,
    isStreaming,
    isLoading,
    customInstructions,
    characterStyle,
    nickname,
    language,
    selectedDocument,
    setSelectedDocument,
    setSidebarActiveTab,
    setSidebarOpen,
  } = useChatStore();

  const scrollRef = useRef<HTMLDivElement>(null);
  const activeRequestRef = useRef<ActiveRequest | null>(null);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [searchOffer, setSearchOffer] = useState<{ query: string; loading: boolean } | null>(null);
  const showSearchOffer = Boolean(searchOffer && !searchOffer.loading && !isStreaming);

  const currentConversation = conversations.find(c => c.id === currentConversationId);
  const messages = currentConversation?.messages || [];

  const characterPrompts: Record<string, string> = {
    warm: 'Respond in a warm, caring, and affectionate manner. Use gentle and kind language.',
    enthusiastic: 'Respond with enthusiasm and energy. Be upbeat and excited in your tone.',
    professional: 'Respond in a professional, formal, and polished tone. Be precise and well-structured.',
    concise: 'Respond concisely and directly. Keep answers brief and to the point.',
    friendly: 'Respond in a casual, friendly, and approachable manner. Be conversational.',
    custom: '',
  };

  const buildInstructions = () => {
    const parts: string[] = [];
    if (nickname?.trim()) parts.push(`Address the user as "${nickname.trim()}".`);
    const characterPrompt = characterPrompts[characterStyle] || '';
    if (characterPrompt) parts.push(characterPrompt);
    if (customInstructions?.trim()) parts.push(customInstructions.trim());
    return parts.join('\n\n');
  };

  const scrollToBottom = useCallback(() => {
    if (scrollRef.current) {
      const { scrollHeight, clientHeight } = scrollRef.current;
      scrollRef.current.scrollTo({
        top: scrollHeight - clientHeight,
        behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
      });
    }
  }, []);

  const latestMessageLength = messages.at(-1)?.content.length ?? 0;
  useEffect(() => {
    const frame = requestAnimationFrame(scrollToBottom);
    return () => cancelAnimationFrame(frame);
  }, [messages.length, latestMessageLength, showSearchOffer, scrollToBottom]);

  const handleStop = useCallback(() => {
    const active = activeRequestRef.current;
    if (!active) return;
    // Release ownership before aborting: its rejected promise may settle after
    // a replacement request starts and must not clear that request's controls.
    activeRequestRef.current = null;
    active.controller.abort();
    updateMessage(active.conversationId, active.messageId, { interrupted: true });
    setSearchOffer(null);
    setIsStreaming(false);
    setIsLoading(false);
  }, [setIsLoading, setIsStreaming, updateMessage]);

  useEffect(() => {
    if (activeRequestRef.current && activeRequestRef.current.conversationId !== currentConversationId) {
      handleStop();
    }
  }, [currentConversationId, handleStop]);

  useEffect(() => () => handleStop(), [handleStop]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ctrl + N: New Chat
      if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
        e.preventDefault();
        createConversation();
      }
      
      // Ctrl + K: Global Search
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        setIsSearchOpen(prev => !prev);
      }
      
      // Ctrl + /: Focus Input
      if ((e.ctrlKey || e.metaKey) && e.key === '/') {
        e.preventDefault();
        const textarea = document.querySelector('textarea');
        if (textarea) {
          textarea.focus();
        }
      }
      
      // Esc: Stop Generation or Close Search
      if (e.key === 'Escape') {
        if (isSearchOpen) {
          e.preventDefault();
          setIsSearchOpen(false);
        } else if (isStreaming || isLoading) {
          e.preventDefault();
          handleStop();
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isStreaming, isLoading, createConversation, isSearchOpen, handleStop]);

  const runRequest = async (conversationId: string, question: string, regenerate = false) => {
    const assistantMessageId = addMessage(conversationId, { role: 'assistant', content: '' });
    const active: ActiveRequest = { controller: new AbortController(), conversationId, messageId: assistantMessageId };
    activeRequestRef.current = active;
    const ownsRequest = () => activeRequestRef.current === active && !active.controller.signal.aborted;
    const append = (text: string) => {
      if (ownsRequest()) appendStreamToMessage(conversationId, assistantMessageId, text);
    };
    const searchMatch = question.match(/^(?:search|tìm)\s+(?:for|kiếm)?\s*(.+)/i);
    setSearchOffer(null);
    setIsLoading(Boolean(searchMatch));
    setIsStreaming(!searchMatch);
    try {
      if (searchMatch) {
        const topic = searchMatch[1].trim();
        setSearchOffer({ query: topic, loading: true });
        append(`Searching for PDFs about "${topic}"…\n\n`);
        const result = await api.searchDownload(topic, 3, active.controller.signal);
        if (result.downloaded.length) {
          append(`${result.message || 'Download complete.'}\n\n`);
          const files = result.downloaded.map(document => `- ${document.file_name}`).join('\n');
          append(`**Documents:**\n${files}\n\n`);
          if (result.job_id) {
            append('Indexing the documents. They are not ready for questions yet…\n\n');
            await api.waitForIndexJob(result.job_id, undefined, active.controller.signal);
            append('Indexing completed. You can now ask questions about these documents.');
          } else {
            append('These documents are already in your library. Check their index status before asking questions.');
          }
          if (ownsRequest()) window.dispatchEvent(new Event('nova:documents-updated'));
        } else {
          append(result.message || 'No PDFs found for this topic. Try a different search term.');
        }
      } else {
        await api.streamMessage(
          conversationId, question, append, active.controller.signal,
          buildInstructions(),
          action => {
            if (ownsRequest() && action.type === 'search_offer') {
              setSearchOffer({ query: action.query, loading: false });
            }
          },
          language, regenerate, selectedDocument?.id,
          retrievedDocs => {
            if (ownsRequest()) updateMessage(conversationId, assistantMessageId, { retrievedDocs });
          },
        );
      }
    } catch (error: unknown) {
      if (!ownsRequest()) return;
      updateMessage(conversationId, assistantMessageId, { interrupted: true });
      toast.error(errorMessage(error));
    } finally {
      if (activeRequestRef.current === active) {
        activeRequestRef.current = null;
        setIsStreaming(false);
        setIsLoading(false);
        if (searchMatch) setSearchOffer(null);
      }
    }
  };

  const handleSend = async (content: string) => {
    const question = content.trim();
    if (!question || activeRequestRef.current || useChatStore.getState().isLoading) return;
    const conversationId = currentConversationId || createConversation();
    addMessage(conversationId, { role: 'user', content: question });
    await runRequest(conversationId, question);
  };

  const handleRegenerate = async () => {
    if (!currentConversationId || activeRequestRef.current || useChatStore.getState().isLoading) return;
    const conversation = useChatStore.getState().conversations.find(item => item.id === currentConversationId);
    const lastUserMessage = conversation?.messages.findLast(message => message.role === 'user');
    if (!lastUserMessage) return;
    regenerateLastMessage(currentConversationId);
    await runRequest(currentConversationId, lastUserMessage.content, true);
  };

  return (
    <div className="relative z-10 flex-1 flex flex-col h-full overflow-hidden bg-background/25">
      <GlobalSearch isOpen={isSearchOpen} onClose={() => setIsSearchOpen(false)} />
      <div 
        ref={scrollRef}
        className="flex-1 overflow-y-auto pt-4 md:pt-8 scroll-smooth"
      >
        {messages.length === 0 ? (
          <WelcomeScreen onSelectSuggestion={handleSend} />
        ) : (
          <div className="mx-auto flex w-full max-w-[960px] flex-col px-4 pb-24 md:px-8 lg:px-10">
            {messages.map((message, index) => {
              const isLastMessage = index === messages.length - 1;
              const messageIsStreaming = isLastMessage && message.role === 'assistant' && isStreaming;
              const isLastAssistantMessage = message.role === 'assistant' && index === messages.findLastIndex(m => m.role === 'assistant');
              return (
                <ChatBubble
                  key={message.id}
                  message={message}
                  isStreaming={messageIsStreaming}
                  onRegenerate={isLastAssistantMessage && !isStreaming && !isLoading ? handleRegenerate : undefined}
                />
              );
            })}

            {searchOffer && showSearchOffer && (
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                className="mx-auto mt-2 w-full max-w-[680px] rounded-[14px] border border-border/50 bg-card/75 p-3.5 shadow-sm"
              >
                <p className="text-sm font-semibold text-foreground">
                  {selectedDocument
                    ? `No matching passages found in ${selectedDocument.name}`
                    : 'No relevant document passages were found'}
                </p>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">
                  Choose a document, rebuild the index, or expand the search to the web.
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-9 rounded-[10px] px-3 text-xs"
                    onClick={() => {
                      setSidebarActiveTab('documents');
                      setSidebarOpen(true);
                      window.dispatchEvent(new CustomEvent('nova:open-sidebar'));
                    }}
                  >
                    <FolderOpen className="h-4 w-4" />
                    Choose a document
                  </Button>
                  {selectedDocument && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-9 rounded-[10px] px-3 text-xs"
                      onClick={() => setSelectedDocument(null)}
                    >
                      Clear scope
                    </Button>
                  )}
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-9 rounded-[10px] px-3 text-xs"
                    onClick={async () => {
                      try {
                        const result = await api.reindexDocuments();
                        if (result.job_id) await api.waitForIndexJob(result.job_id);
                        toast.success('Knowledge index rebuilt');
                        setSearchOffer(null);
                      } catch (error) {
                        toast.error(errorMessage(error));
                      }
                    }}
                  >
                    <RefreshCw className="h-4 w-4" />
                    Re-index
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => void handleSend(`search for ${searchOffer.query}`)}
                    className="h-9 rounded-[10px] px-3 text-xs text-muted-foreground"
                  >
                    <Globe2 className="h-4 w-4" />
                    Search web
                  </Button>
                </div>
              </motion.div>
            )}

            {searchOffer?.loading && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="flex items-center justify-center gap-2 py-3 text-xs text-muted-foreground"
              >
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Searching and downloading PDFs about "{searchOffer.query.slice(0, 50)}"...
              </motion.div>
            )}
          </div>
        )}
      </div>

      {/* Input area with a feathered backdrop instead of a hard color edge */}
      <div className="nova-composer-dock relative isolate px-4 pb-[max(1.25rem,env(safe-area-inset-bottom,0.75rem))] pt-5 md:pb-6 md:pt-6">
        <div className="relative z-10 mx-auto w-full max-w-[920px]">
          <ChatInput onSend={handleSend} onStop={handleStop} />
        </div>
      </div>
    </div>
  );
};
