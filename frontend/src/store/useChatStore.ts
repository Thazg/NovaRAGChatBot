import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { v4 as uuidv4 } from 'uuid';
import { toast } from 'sonner';
import type { Conversation, Message } from '../types';
import { auth, api, getSessionRevision, type UserPreferences } from '../services/api';

const preferenceState = (preferences: UserPreferences): Partial<ChatState> => ({
  displayName: preferences.display_name,
  theme: preferences.theme,
  language: preferences.language,
  characterStyle: preferences.character_style,
  nickname: preferences.nickname,
  customInstructions: preferences.custom_instructions,
});

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
  selectedDocument: { id: string; name: string } | null;

  // Actions
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string) => Promise<void>;
  bootstrapSession: () => Promise<void>;
  logout: () => Promise<void>;
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
  syncPreferences: () => Promise<void>;
  savePreferences: () => Promise<void>;
  setSidebarActiveTab: (tab: 'conversations' | 'documents') => void;
  setSelectedDocument: (document: { id: string; name: string } | null) => void;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;

  // Conversation actions
  createConversation: () => string;
  setCurrentConversation: (id: string) => void;
  deleteConversation: (id: string) => Promise<void>;
  renameConversation: (id: string, title: string) => Promise<void>;
  pinConversation: (id: string) => Promise<void>;
  duplicateConversation: (id: string) => Promise<void>;
  clearAllConversations: () => Promise<void>;

  // Message actions
  addMessage: (conversationId: string, message: Omit<Message, 'id' | 'createdAt'>) => string;
  appendStreamToMessage: (conversationId: string, messageId: string, textChunk: string) => void;
  setIsStreaming: (isStreaming: boolean) => void;
  setIsLoading: (isLoading: boolean) => void;
  updateMessageContent: (conversationId: string, messageId: string, content: string) => void;
  updateMessage: (conversationId: string, messageId: string, changes: Partial<Pick<Message, 'retrievedDocs' | 'interrupted'>>) => void;
  setMessageFeedback: (conversationId: string, messageId: string, feedback: 'like' | 'dislike' | null) => void;
  regenerateLastMessage: (conversationId: string) => void;
}

// Browser storage is shared across accounts on this device. Keep account
// context on the server/in memory, never in the persisted UI preference blob.
type PersistedChatState = Pick<ChatState, 'theme' | 'sidebarOpen' | 'developerMode' | 'sidebarActiveTab'>;

const accountDefaults = {
  avatar: null,
  displayName: 'User',
  nickname: '',
  customInstructions: '',
  characterStyle: 'warm',
  language: 'auto' as const,
  selectedDocument: null,
};

export const useChatStore = create<ChatState>()(
  persist<ChatState, [], [], PersistedChatState>(
    (set: (partial: Partial<ChatState> | ((state: ChatState) => Partial<ChatState>)) => void, get) => ({
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
      selectedDocument: null,

      login: async (username: string, password: string) => {
        const res = await auth.login(username, password);
        const revision = getSessionRevision();
        set({ ...accountDefaults, token: res.access_token, userId: res.user_id, username, displayName: username, conversations: [], currentConversationId: null });
        try {
          const convs = await api.getConversations();
          const mapped: Conversation[] = convs.map((c) => ({
            id: c.id,
            title: c.title || 'New Chat',
            messages: (c.messages || []).map((m) => ({
              id: m.id || uuidv4(),
              role: m.role || 'user',
              content: m.content || '',
              createdAt: m.createdAt || Date.now(),
              retrievedDocs: m.retrievedDocs,
              interrupted: m.interrupted,
            })),
            createdAt: c.createdAt || Date.now(),
            updatedAt: c.updatedAt || Date.now(),
            pinned: c.pinned || false,
          }));
          if (revision === getSessionRevision()) set({ conversations: mapped, currentConversationId: mapped.length > 0 ? mapped[0].id : null });
        } catch {
          if (revision === getSessionRevision()) set({ conversations: [], currentConversationId: null });
        }
        const preferences = await api.getPreferences().catch(() => null);
        if (preferences && revision === getSessionRevision()) set(preferenceState(preferences));
      },
      register: async (username: string, password: string) => {
        const res = await auth.register(username, password);
        const revision = getSessionRevision();
        set({ ...accountDefaults, token: res.access_token, userId: res.user_id, username, displayName: username, conversations: [], currentConversationId: null });
        const preferences = await api.getPreferences().catch(() => null);
        if (preferences && revision === getSessionRevision()) set(preferenceState(preferences));
      },
      bootstrapSession: async () => {
        const revision = getSessionRevision();
        const res = await auth.refresh();
        const username = res.username || 'User';
        const convs = await api.getConversations();
        const preferences = await api.getPreferences().catch(() => null);
        const mapped: Conversation[] = convs.map((c) => ({
          id: c.id,
          title: c.title || 'New Chat',
          messages: (c.messages || []).map((m) => ({
            id: m.id || uuidv4(),
            role: m.role || 'user',
            content: m.content || '',
            createdAt: m.createdAt || Date.now(),
            retrievedDocs: m.retrievedDocs,
            interrupted: m.interrupted,
          })),
          createdAt: c.createdAt || Date.now(),
          updatedAt: c.updatedAt || Date.now(),
          pinned: c.pinned || false,
        }));
        if (revision !== getSessionRevision()) return;
        set({
          ...accountDefaults,
          token: res.access_token,
          userId: res.user_id,
          username,
          displayName: username,
          conversations: mapped,
          currentConversationId: mapped[0]?.id || null,
          ...(preferences ? preferenceState(preferences) : {}),
        });
      },
      logout: async () => {
        set({
          ...accountDefaults,
          token: null,
          isStreaming: false,
          isLoading: false,
          userId: null,
          username: null,
          conversations: [],
          currentConversationId: null,
          avatar: null,
          displayName: 'User',
          nickname: '',
          customInstructions: '',
          selectedDocument: null,
        });
        await auth.logout().catch(() => undefined);
      },

      setLanguage: (language: 'auto' | 'english' | 'vietnamese') => set({ language }),
      syncPreferences: async () => {
        const revision = getSessionRevision();
        const preferences = await api.getPreferences();
        if (revision === getSessionRevision()) set(preferenceState(preferences));
      },
      savePreferences: async () => {
        const revision = getSessionRevision();
        const state = get();
        const preferences = await api.updatePreferences({
          display_name: state.displayName.trim().slice(0, 80),
          theme: state.theme,
          language: state.language,
          character_style: state.characterStyle as UserPreferences['character_style'],
          nickname: state.nickname.trim().slice(0, 80),
          custom_instructions: state.customInstructions.trim().slice(0, 4000),
        });
        if (revision === getSessionRevision()) set(preferenceState(preferences));
      },
      setSidebarActiveTab: (sidebarActiveTab: 'conversations' | 'documents') => set({ sidebarActiveTab }),
      setSelectedDocument: (selectedDocument) => set({ selectedDocument }),
      setSettingsOpen: (settingsOpen: boolean) => set({ settingsOpen }),
      setAboutOpen: (aboutOpen: boolean) => set({ aboutOpen }),
      setCustomInstructions: (customInstructions: string) => set({ customInstructions }),
      setCharacterStyle: (characterStyle: string) => set({ characterStyle }),
      setNickname: (nickname: string) => set({ nickname }),
      setDeveloperMode: (developerMode: boolean) => set({ developerMode }),

      setTheme: (theme: 'light' | 'dark' | 'system') => {
        set({ theme });
        // Theme changes are expected to persist immediately, including the
        // quick toggle in the sidebar. Without this, session bootstrap would
        // restore the older server preference after a page refresh.
        if (get().userId) {
          void api.patchPreferences({ theme }).catch(() => undefined);
        }
      },
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
        const revision = getSessionRevision();
        void api.createConversation(newId, newConversation).catch((error: unknown) => {
          if (revision === getSessionRevision()) toast.error(error instanceof Error ? error.message : 'Could not save the new conversation');
        });
        return newId;
      },

      setCurrentConversation: (id: string) => set({ currentConversationId: id }),

      deleteConversation: async (id: string) => {
        const revision = getSessionRevision();
        await api.deleteConversation(id);
        if (revision !== getSessionRevision()) return;
        set((state: ChatState) => {
          const filtered = state.conversations.filter(c => c.id !== id);
          return { conversations: filtered,
            currentConversationId: state.currentConversationId === id ? filtered[0]?.id || null : state.currentConversationId };
        });
      },

      renameConversation: async (id: string, title: string) => {
        const revision = getSessionRevision();
        const safeTitle = title.trim().slice(0, 120) || 'New Chat';
        await api.updateConversation(id, { title: safeTitle });
        if (revision !== getSessionRevision()) return;
        set(state => ({ conversations: state.conversations.map(c =>
          c.id === id ? { ...c, title: safeTitle, updatedAt: Date.now() } : c) }));
      },

      pinConversation: async (id: string) => {
        const current = get().conversations.find(c => c.id === id);
        if (!current) throw new Error('Conversation is no longer available');
        const pinned = !current.pinned;
        const revision = getSessionRevision();
        await api.updateConversation(id, { pinned });
        if (revision !== getSessionRevision()) return;
        set(state => ({ conversations: state.conversations.map(c =>
          c.id === id ? { ...c, pinned, updatedAt: Date.now() } : c) }));
      },

      duplicateConversation: async (id: string) => {
        const original = get().conversations.find(c => c.id === id);
        if (!original) throw new Error('Conversation is no longer available');
        const revision = getSessionRevision();
        const newId = uuidv4();
        const duplicate: Conversation = { ...original, id: newId,
          title: `${original.title} (Copy)`.slice(0, 120),
          messages: original.messages.map(m => ({ ...m, id: uuidv4() })),
          createdAt: Date.now(), updatedAt: Date.now(), pinned: false };
        await api.createConversation(newId, duplicate);
        if (revision !== getSessionRevision()) return;
        set(state => ({ conversations: [duplicate, ...state.conversations], currentConversationId: newId }));
      },

      clearAllConversations: async () => {
        const revision = getSessionRevision();
        await api.clearConversations();
        if (revision === getSessionRevision()) set({ conversations: [], currentConversationId: null });
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

      updateMessage: (conversationId, messageId, changes) => {
        set(state => ({ conversations: state.conversations.map(conversation =>
          conversation.id === conversationId
            ? { ...conversation, messages: conversation.messages.map(message =>
                message.id === messageId ? { ...message, ...changes } : message) }
            : conversation) }));
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
      version: 5,
      migrate: (persistedState: unknown, version: number) => {
        const previous = (persistedState && typeof persistedState === 'object' ? persistedState : {}) as Record<string, unknown>;
        const theme = ['light', 'dark', 'system'].includes(String(previous.theme))
          ? previous.theme as ChatState['theme'] : 'dark';
        return {
          theme: version < 2 && theme === 'system' ? 'dark' : theme,
          sidebarOpen: typeof previous.sidebarOpen === 'boolean' ? previous.sidebarOpen : true,
          developerMode: previous.developerMode === true,
          sidebarActiveTab: previous.sidebarActiveTab === 'documents' ? 'documents' : 'conversations',
        };
      },
      partialize: (state: ChatState) => ({
        theme: state.theme,
        sidebarOpen: state.sidebarOpen,
        developerMode: state.developerMode,
        sidebarActiveTab: state.sidebarActiveTab,
      }),
    }
  )
);
