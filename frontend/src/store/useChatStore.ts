import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { v4 as uuidv4 } from 'uuid';
import type { Conversation, Message } from '../types';
import { auth, api } from '../services/api';

interface ChatState {
  // Auth
  token: string | null;
  userId: string | null;
  username: string | null;

  conversations: Conversation[];
  currentConversationId: string | null;
  sidebarOpen: boolean;
  theme: 'light' | 'dark' | 'system';
  isStreaming: boolean;
  isLoading: boolean;
  avatar: string | null;
  displayName: string;
  settingsOpen: boolean;
  aboutOpen: boolean;
  customInstructions: string;
  characterStyle: string;
  nickname: string;
  developerMode: boolean;
  language: 'auto' | 'english' | 'vietnamese';
  sidebarActiveTab: 'conversations' | 'documents';
  
  // Actions
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string) => Promise<void>;
  logout: () => void;
  setTheme: (theme: 'light' | 'dark' | 'system') => void;
  setSettingsOpen: (open: boolean) => void;
  setAboutOpen: (open: boolean) => void;
  setAvatar: (avatar: string | null) => void;
  setDisplayName: (name: string) => void;
  setCustomInstructions: (instructions: string) => void;
  setCharacterStyle: (style: string) => void;
  setNickname: (nickname: string) => void;
  setDeveloperMode: (mode: boolean) => void;
  setLanguage: (lang: 'auto' | 'english' | 'vietnamese') => void;
  setSidebarActiveTab: (tab: 'conversations' | 'documents') => void;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  
  // Conversation actions
  createConversation: () => string;
  setCurrentConversation: (id: string) => void;
  deleteConversation: (id: string) => void;
  renameConversation: (id: string, title: string) => void;
  pinConversation: (id: string) => void;
  duplicateConversation: (id: string) => void;
  clearAllConversations: () => void;
  
  // Message actions
  addMessage: (conversationId: string, message: Omit<Message, 'id' | 'createdAt'>) => string;
  appendStreamToMessage: (conversationId: string, messageId: string, textChunk: string) => void;
  setIsStreaming: (isStreaming: boolean) => void;
  setIsLoading: (isLoading: boolean) => void;
  updateMessageContent: (conversationId: string, messageId: string, content: string) => void;
  setMessageFeedback: (conversationId: string, messageId: string, feedback: 'like' | 'dislike' | null) => void;
  regenerateLastMessage: (conversationId: string) => void;
}

type PersistedChatState = Pick<ChatState,
  | 'token'
  | 'userId'
  | 'username'
  | 'conversations'
  | 'theme'
  | 'sidebarOpen'
  | 'currentConversationId'
  | 'avatar'
  | 'displayName'
  | 'customInstructions'
  | 'characterStyle'
  | 'nickname'
  | 'developerMode'
  | 'language'
  | 'sidebarActiveTab'
>;

export const useChatStore = create<ChatState>()(
  persist<ChatState, [], [], PersistedChatState>(
    (set: (partial: Partial<ChatState> | ((state: ChatState) => Partial<ChatState>)) => void) => ({
      token: null,
      userId: null,
      username: null,
      conversations: [],
      currentConversationId: null,
      sidebarOpen: true,
      theme: 'dark',
      isStreaming: false,
      isLoading: false,
      avatar: null,
      displayName: 'User',
      settingsOpen: false,
      aboutOpen: false,
      customInstructions: '',
      characterStyle: 'warm',
      nickname: '',
      developerMode: false,
      language: 'auto',
      sidebarActiveTab: 'conversations',

      login: async (username: string, password: string) => {
        const res = await auth.login(username, password);
        set({ token: res.token, userId: res.user_id, username, displayName: username, conversations: [], currentConversationId: null });
        try {
          const convs = await api.getConversations(res.token);
          const mapped: Conversation[] = convs.map((c: any) => ({
            id: c.id,
            title: c.title || 'New Chat',
            messages: (c.messages || []).map((m: any) => ({
              id: m.id || uuidv4(),
              role: m.role || 'user',
              content: m.content || '',
              createdAt: m.createdAt || Date.now(),
            })),
            createdAt: c.createdAt || Date.now(),
            updatedAt: c.updatedAt || Date.now(),
            pinned: c.pinned || false,
          }));
          set({ conversations: mapped, currentConversationId: mapped.length > 0 ? mapped[0].id : null });
        } catch {
          set({ conversations: [], currentConversationId: null });
        }
      },
      register: async (username: string, password: string) => {
        const res = await auth.register(username, password);
        set({ token: res.token, userId: res.user_id, username, displayName: username, conversations: [], currentConversationId: null });
      },
      logout: () => set({
        token: null,
        userId: null,
        username: null,
        conversations: [],
        currentConversationId: null,
        avatar: null,
        displayName: 'User',
        nickname: '',
        customInstructions: '',
      }),

      setLanguage: (language: 'auto' | 'english' | 'vietnamese') => set({ language }),
      setSidebarActiveTab: (sidebarActiveTab: 'conversations' | 'documents') => set({ sidebarActiveTab }),
      setSettingsOpen: (settingsOpen: boolean) => set({ settingsOpen }),
      setAboutOpen: (aboutOpen: boolean) => set({ aboutOpen }),
      setCustomInstructions: (customInstructions: string) => set({ customInstructions }),
      setCharacterStyle: (characterStyle: string) => set({ characterStyle }),
      setNickname: (nickname: string) => set({ nickname }),
      setDeveloperMode: (developerMode: boolean) => set({ developerMode }),

      setTheme: (theme: 'light' | 'dark' | 'system') => set({ theme }),
      setAvatar: (avatar: string | null) => set({ avatar }),
      setDisplayName: (displayName: string) => set({ displayName }),
      
      toggleSidebar: () => set((state: ChatState) => ({ sidebarOpen: !state.sidebarOpen })),
      setSidebarOpen: (open: boolean) => set({ sidebarOpen: open }),

      createConversation: () => {
        const newId = uuidv4();
        const newConversation: Conversation = {
          id: newId,
          title: 'New Chat',
          messages: [],
          createdAt: Date.now(),
          updatedAt: Date.now(),
        };
        set((state: ChatState) => ({
          conversations: [newConversation, ...state.conversations],
          currentConversationId: newId,
        }));
        api.createConversation(newId, newConversation).catch(() => {});
        return newId;
      },

      setCurrentConversation: (id: string) => set({ currentConversationId: id }),

      deleteConversation: (id: string) => {
        api.deleteConversation(id).catch(() => {});
        set((state: ChatState) => {
          const filtered = state.conversations.filter((c: Conversation) => c.id !== id);
          return {
            conversations: filtered,
            currentConversationId: state.currentConversationId === id 
              ? (filtered.length > 0 ? filtered[0].id : null) 
              : state.currentConversationId
          };
        });
      },

      renameConversation: (id: string, title: string) => {
        const safeTitle = title.trim().slice(0, 120) || 'New Chat';
        api.updateConversation(id, { title: safeTitle }).catch(() => {});
        set((state: ChatState) => ({
          conversations: state.conversations.map((c: Conversation) => 
            c.id === id ? { ...c, title: safeTitle, updatedAt: Date.now() } : c
          )
        }));
      },

      pinConversation: (id: string) => set((state: ChatState) => {
        const current = state.conversations.find((c: Conversation) => c.id === id);
        const pinned = !current?.pinned;
        api.updateConversation(id, { pinned }).catch(() => {});
        return {
          conversations: state.conversations.map((c: Conversation) =>
            c.id === id ? { ...c, pinned, updatedAt: Date.now() } : c
          ),
        };
      }),

      duplicateConversation: (id: string) => set((state: ChatState) => {
        const original = state.conversations.find((c: Conversation) => c.id === id);
        if (!original) return state;
        const newId = uuidv4();
        const duplicate: Conversation = {
          ...original,
          id: newId,
          title: `${original.title} (Copy)`.slice(0, 120),
          messages: original.messages.map((m: Message) => ({ ...m, id: uuidv4() })),
          createdAt: Date.now(),
          updatedAt: Date.now(),
          pinned: false,
        };
        api.createConversation(newId, duplicate).catch(() => {});
        return {
          conversations: [duplicate, ...state.conversations],
          currentConversationId: newId,
        };
      }),

      clearAllConversations: () => {
        api.clearConversations().catch(() => {});
        set({ conversations: [], currentConversationId: null });
      },

      addMessage: (conversationId: string, message: Omit<Message, 'id' | 'createdAt'>) => {
        const messageId = uuidv4();
        const newMessage: Message = {
          ...message,
          id: messageId,
          createdAt: Date.now(),
        };

        set((state: ChatState) => {
          const conversations = state.conversations.map((c: Conversation) => {
            if (c.id === conversationId) {
              return {
                ...c,
                messages: [...c.messages, newMessage],
                updatedAt: Date.now(),
                title: c.title === 'New Chat' && newMessage.role === 'user' 
                  ? newMessage.content.slice(0, 30) + (newMessage.content.length > 30 ? '...' : '')
                  : c.title
              };
            }
            return c;
          });
          return { conversations };
        });
        
        return messageId;
      },

      appendStreamToMessage: (conversationId: string, messageId: string, textChunk: string) => {
        set((state: ChatState) => ({
          conversations: state.conversations.map((c: Conversation) => {
            if (c.id === conversationId) {
              return {
                ...c,
                messages: c.messages.map((m: Message) => 
                  m.id === messageId 
                    ? { ...m, content: m.content + textChunk } 
                    : m
                ),
                updatedAt: Date.now(),
              };
            }
            return c;
          })
        }));
      },
      
      updateMessageContent: (conversationId: string, messageId: string, content: string) => {
        set((state: ChatState) => ({
          conversations: state.conversations.map((c: Conversation) => {
            if (c.id === conversationId) {
              return {
                ...c,
                messages: c.messages.map((m: Message) => 
                  m.id === messageId 
                    ? { ...m, content } 
                    : m
                ),
                updatedAt: Date.now(),
              };
            }
            return c;
          })
        }));
      },

      setMessageFeedback: (conversationId: string, messageId: string, feedback: 'like' | 'dislike' | null) => {
        set((state: ChatState) => ({
          conversations: state.conversations.map((c: Conversation) => {
            if (c.id === conversationId) {
              return {
                ...c,
                messages: c.messages.map((m: Message) => 
                  m.id === messageId 
                    ? { ...m, feedback } 
                    : m
                ),
                updatedAt: Date.now(),
              };
            }
            return c;
          })
        }));
      },

      regenerateLastMessage: (conversationId: string) => {
        set((state: ChatState) => {
          const conversations = state.conversations.map((c: Conversation) => {
            if (c.id === conversationId) {
              const messages = [...c.messages];
              const lastAssistantIndex = messages.findLastIndex((m: Message) => m.role === 'assistant');
              if (lastAssistantIndex !== -1) messages.splice(lastAssistantIndex, 1);
              return { ...c, messages, updatedAt: Date.now() };
            }
            return c;
          });
          return { conversations };
        });
      },

      setIsStreaming: (isStreaming: boolean) => set({ isStreaming }),
      setIsLoading: (isLoading: boolean) => set({ isLoading }),
    }),
    {
      name: 'rag-chat-storage',
      version: 2,
      migrate: (persistedState: unknown, version: number) => {
        const state = persistedState as PersistedChatState;
        if (version < 2 && (!state.theme || state.theme === 'system')) {
          return { ...state, theme: 'dark' };
        }
        return state;
      },
      partialize: (state: ChatState) => ({
        token: state.token,
        userId: state.userId,
        username: state.username,
        conversations: state.conversations,
        theme: state.theme,
        sidebarOpen: state.sidebarOpen,
        currentConversationId: state.currentConversationId,
        avatar: state.avatar,
        displayName: state.displayName,
        customInstructions: state.customInstructions,
        characterStyle: state.characterStyle,
        nickname: state.nickname,
        developerMode: state.developerMode,
        language: state.language,
        sidebarActiveTab: state.sidebarActiveTab,
      }),
    }
  )
);
