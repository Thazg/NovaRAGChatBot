import { z } from 'zod';

// Production authentication must stay same-origin so the host-only refresh
// cookie is sent through the Vercel/nginx `/api` proxy. Ignore stale hosting
// environment overrides in production; a direct Render URL is also rejected
// by the production Content-Security-Policy.
export const API_BASE_URL = (
  import.meta.env.PROD
    ? '/api'
    : (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000')
).replace(/\/+$/, '');
const MAX_UPLOAD_BYTES = 25 * 1024 * 1024;
const ALLOWED_UPLOAD_EXTENSIONS = ['.pdf', '.md', '.markdown', '.rst', '.txt', '.py', '.docx', '.ipynb'];

let accessToken: string | null = null;
let refreshPromise: Promise<AuthResponse> | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

function authHeaders(): Record<string, string> {
  const token = accessToken;
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

const AuthResponseSchema = z.object({
  access_token: z.string().min(20),
  user_id: z.string().uuid(),
  username: z.string().optional(),
});
export type AuthResponse = z.infer<typeof AuthResponseSchema>;

const StatusSchema = z.object({ status: z.string() });
const DeleteCountSchema = StatusSchema.extend({ deleted: z.number().int().nonnegative() });
const AccountDeleteSchema = StatusSchema.extend({ message: z.string() });
const MeSchema = z.object({ user_id: z.string().uuid(), username: z.string().optional().nullable() });
const ChatResponseSchema = z.object({ answer: z.string() });
const ErrorResponseSchema = z.object({ detail: z.string() });

async function responseError(response: Response, fallback: string): Promise<Error> {
  const parsed = ErrorResponseSchema.safeParse(await response.json().catch(() => null));
  return new Error(parsed.success ? parsed.data.detail : fallback);
}

const MessageSchema = z.object({
  id: z.string().optional(),
  role: z.enum(['user', 'assistant', 'system']),
  content: z.string(),
  createdAt: z.number().optional(),
});

const ConversationSchema = z.object({
  id: z.string(),
  title: z.string(),
  messages: z.array(MessageSchema).default([]),
  createdAt: z.number().optional(),
  updatedAt: z.number().optional(),
  pinned: z.boolean().optional(),
});

const DocumentSchema = z.object({
  id: z.string(),
  name: z.string(),
  size: z.number().nonnegative(),
  indexed: z.boolean().optional(),
  chunks: z.number().int().nonnegative().optional(),
  // Older backend deployments serialize a missing source URL as null.
  // Normalize that legacy response so one ordinary upload cannot make the
  // entire workspace document list fail schema validation.
  source_url: z.string().url().nullish().transform((value) => value ?? undefined),
});

const IndexJobSchema = z.object({
  id: z.string(),
  status: z.enum(['queued', 'started', 'deferred', 'scheduled', 'stopped', 'canceled', 'finished', 'failed']),
  progress: z.number().min(0).max(100),
  result: z.object({
    indexed: z.boolean().optional(),
    chunks: z.number().optional(),
    documents: z.number().optional(),
    message: z.string().optional(),
  }).optional().nullable(),
  error: z.string().optional().nullable(),
});

const UploadResponseSchema = z.object({
  status: z.string(),
  // Legacy synchronous backends did not return an id. Keeping this optional
  // lets the session-security commit remain backward compatible; hardened
  // UUID uploads will always provide it in the next step.
  id: z.string().optional(),
  filename: z.string(),
  indexed: z.boolean().optional(),
  chunks: z.number().optional(),
  job_id: z.string().optional(),
  progress: z.number().optional(),
  message: z.string().optional(),
});

const SummarySchema = z.object({
  summary: z.string(),
  chunks: z.number().int().nonnegative(),
  filename: z.string(),
});

const DownloadedDocumentSchema = z.object({
  id: z.string(),
  file_name: z.string(),
  new: z.boolean(),
});

const SearchDownloadSchema = StatusSchema.extend({
  downloaded: z.array(DownloadedDocumentSchema),
  message: z.string(),
  job_id: z.string().optional().nullable(),
});

const ReindexSchema = StatusSchema.extend({
  message: z.string(),
  job_id: z.string().optional(),
  progress: z.number().min(0).max(100).optional(),
});

const HealthStatusSchema = z.object({
  status: z.string(),
  version: z.string().optional(),
  environment: z.string().optional(),
  uptime_seconds: z.number().optional(),
  llm_provider: z.string().optional(),
  groq_model: z.string().optional(),
  model: z.string().optional(),
  retrieval: z.string().optional(),
  embedding_model: z.string().nullable().optional(),
  infrastructure: z.record(z.string(), z.union([z.string(), z.number()])).optional(),
  rag_config: z.object({
    top_k: z.number().int().positive(),
    context_window: z.number().int().positive(),
    max_tokens: z.number().int().positive(),
    max_context_chars: z.number().int().positive(),
    max_upload_bytes: z.number().int().positive(),
  }).optional(),
}).passthrough();

const ReadinessStatusSchema = z.object({
  status: z.enum(['ready', 'degraded']),
  ready: z.boolean(),
  provider_status: z.string(),
  model: z.string().optional(),
  model_available: z.boolean().optional(),
  message: z.string(),
  checked_at: z.number().optional(),
  llm_provider: z.string().optional(),
  infrastructure: z.record(z.string(), z.union([z.string(), z.number()])).optional(),
}).passthrough();

const UserPreferencesSchema = z.object({
  display_name: z.string().max(80),
  theme: z.enum(['light', 'dark', 'system']),
  language: z.enum(['auto', 'english', 'vietnamese']),
  character_style: z.enum(['warm', 'enthusiastic', 'professional', 'concise', 'friendly', 'custom']),
  nickname: z.string().max(80),
  custom_instructions: z.string().max(4000),
});

const AccountExportSchema = z.object({
  exported_at: z.string(),
  account: z.object({ user_id: z.string().uuid(), username: z.string().nullable().optional() }),
  preferences: UserPreferencesSchema,
  conversations: z.array(ConversationSchema),
  documents: z.array(DocumentSchema),
});

const StreamEventSchema = z.union([
  z.object({ token: z.string() }),
  z.object({ action: z.literal('search_offer'), query: z.string().optional() }),
]);

async function performRefresh(): Promise<AuthResponse> {
  const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
    method: 'POST',
    credentials: 'include',
  });
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) {
      setAccessToken(null);
      throw new Error('Session expired');
    }
    throw await responseError(response, 'Session service unavailable');
  }
  const data = AuthResponseSchema.parse(await response.json());
  setAccessToken(data.access_token);
  return data;
}

function refreshAccessToken(): Promise<AuthResponse> {
  // A single-use refresh token must only be rotated once. Sharing this promise
  // prevents concurrent 401 responses (or React StrictMode) from replaying the
  // same cookie and accidentally invalidating a freshly rotated session.
  if (!refreshPromise) {
    refreshPromise = performRefresh().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

async function authorizedFetch(path: string, init: RequestInit = {}, retry = true): Promise<Response> {
  const headers = new Headers(init.headers);
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    credentials: 'include',
  });
  if (response.status === 401 && retry) {
    await refreshAccessToken();
    return authorizedFetch(path, init, false);
  }
  return response;
}

export const auth = {
  async register(username: string, password: string): Promise<AuthResponse> {
    const res = await fetch(`${API_BASE_URL}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
      credentials: 'include',
    });
    if (!res.ok) {
      throw await responseError(res, res.statusText || 'Registration failed');
    }
    const data = AuthResponseSchema.parse(await res.json());
    setAccessToken(data.access_token);
    return data;
  },

  async login(username: string, password: string): Promise<AuthResponse> {
    const res = await fetch(`${API_BASE_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
      credentials: 'include',
    });
    if (!res.ok) {
      throw await responseError(res, res.statusText || 'Login failed');
    }
    const data = AuthResponseSchema.parse(await res.json());
    setAccessToken(data.access_token);
    return data;
  },

  async refresh(): Promise<AuthResponse> {
    return refreshAccessToken();
  },

  async logout(): Promise<void> {
    try {
      await fetch(`${API_BASE_URL}/auth/logout`, { method: 'POST', credentials: 'include' });
    } finally {
      setAccessToken(null);
    }
  },

  async me(): Promise<{ user_id: string }> {
    const res = await authorizedFetch('/auth/me', { headers: authHeaders() });
    if (!res.ok) throw new Error('Session expired');
    return MeSchema.parse(await res.json());
  },
};

export interface ChatRequest {
  session_id: string;
  question: string;
  instructions?: string;
}

export interface ChatResponse {
  answer: string;
}

export interface Document {
  id: string;
  name: string;
  size: number;
  indexed?: boolean;
  chunks?: number;
  source_url?: string;
}

export interface IndexJob {
  id: string;
  status: 'queued' | 'started' | 'deferred' | 'scheduled' | 'stopped' | 'canceled' | 'finished' | 'failed';
  progress: number;
  result?: { indexed?: boolean; chunks?: number; documents?: number; message?: string } | null;
  error?: string | null;
}

export interface DownloadedDocument {
  id: string;
  file_name: string;
  new: boolean;
}

export interface Conversation {
  id: string;
  title: string;
  messages: Array<{
    id?: string;
    role: 'user' | 'assistant' | 'system';
    content: string;
    createdAt?: number;
  }>;
  createdAt?: number;
  updatedAt?: number;
  pinned?: boolean;
}

export interface HealthStatus {
  status: string;
  version?: string;
  environment?: string;
  uptime_seconds?: number;
  llm_provider?: string;
  groq_model?: string;
  model?: string;
  retrieval?: string;
  embedding_model?: string | null;
  infrastructure?: Record<string, string | number>;
  rag_config?: {
    top_k: number;
    context_window: number;
    max_tokens: number;
    max_context_chars: number;
    max_upload_bytes: number;
  };
}

export interface ReadinessStatus {
  status: 'ready' | 'degraded';
  ready: boolean;
  provider_status: string;
  model?: string;
  model_available?: boolean;
  message: string;
  checked_at?: number;
  llm_provider?: string;
}

export type UserPreferences = z.infer<typeof UserPreferencesSchema>;
export type AccountExport = z.infer<typeof AccountExportSchema>;

export const api = {
  async sendMessage(sessionId: string, question: string, abortSignal?: AbortSignal): Promise<ChatResponse> {
    const response = await authorizedFetch('/chat', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ session_id: sessionId, question }),
      signal: abortSignal,
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.statusText}`);
    }

    return ChatResponseSchema.parse(await response.json());
  },

  async streamMessage(
    sessionId: string,
    question: string,
    onToken: (token: string) => void,
    abortSignal?: AbortSignal,
    instructions?: string,
    onAction?: (action: { type: string; query: string }) => void,
    language?: string,
    regenerate = false,
    reconnectAttempt = 0,
    replayPrefix = '',
  ): Promise<void> {
    const body: Record<string, string | boolean> = { session_id: sessionId, question, stream: true };
    if (instructions) body.instructions = instructions;
    if (language && language !== 'auto') body.language = language;
    if (regenerate) body.regenerate = true;
    let response: Response;
    try {
      response = await authorizedFetch('/chat/stream', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify(body),
        signal: abortSignal,
      });
    } catch (error) {
      if (reconnectAttempt < 1 && !abortSignal?.aborted) {
        await new Promise((resolve) => setTimeout(resolve, 500));
        return api.streamMessage(
          sessionId, question, onToken, abortSignal, instructions,
          onAction, language, regenerate, reconnectAttempt + 1, replayPrefix,
        );
      }
      throw error;
    }

    if (!response.ok) {
      throw new Error(`API error: ${response.statusText}`);
    }

    if (!response.body) {
      throw new Error('ReadableStream not supported by this browser.');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    let attemptText = '';
    let emittedText = replayPrefix;

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
      
      // Attempt to split by lines or SSE data format
      const lines = buffer.split('\n');
      buffer = lines.pop() || ''; // Keep the incomplete line in buffer

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        
        let jsonStr = trimmed;
        // Handle SSE format "data: {...}"
        if (trimmed.startsWith('data:')) {
          jsonStr = trimmed.substring(5).trim();
          if (jsonStr === '[DONE]') continue; // common SSE end signal
        }

        try {
          const parsed = StreamEventSchema.safeParse(JSON.parse(jsonStr));
          if (!parsed.success) continue;
          if ('token' in parsed.data) {
            const previousAttemptLength = attemptText.length;
            attemptText += parsed.data.token;
            if (!replayPrefix) {
              onToken(parsed.data.token);
              emittedText += parsed.data.token;
            } else if (replayPrefix.startsWith(attemptText)) {
              // Suppress the deterministic replay that was already rendered.
            } else if (attemptText.startsWith(replayPrefix)) {
              const delta = attemptText.slice(Math.max(previousAttemptLength, replayPrefix.length));
              if (delta) {
                onToken(delta);
                emittedText += delta;
              }
            } else {
              throw new Error('The regenerated stream changed after reconnecting. Please regenerate the answer.');
            }
          } else if (parsed.data.action === 'search_offer') {
            onAction?.({ type: 'search_offer', query: parsed.data.query || '' });
          }
          } catch {
            // Incomplete JSON or other format, ignore for now
          }
        }
      }
    } catch (streamError: unknown) {
      // StreamClosed / AbortError — expected when user cancels or connection drops
      const errorName = streamError instanceof DOMException ? streamError.name : '';
      const errorMessage = streamError instanceof Error ? streamError.message : '';
      if (errorName === 'AbortError' || errorMessage.includes('StreamClosed')) {
        return;
      }
      if (reconnectAttempt < 1 && !abortSignal?.aborted) {
        await new Promise((resolve) => setTimeout(resolve, 500));
        return api.streamMessage(
          sessionId, question, onToken, abortSignal, instructions,
          onAction, language, regenerate, reconnectAttempt + 1, emittedText,
        );
      }
      throw streamError;
    }
  },

  // Documents API
  async getDocuments(): Promise<Document[]> {
    const response = await authorizedFetch('/documents', { headers: authHeaders() });
    if (!response.ok) {
      throw new Error(`API error: ${response.statusText}`);
    }
    return z.array(DocumentSchema).parse(await response.json());
  },

  async uploadDocument(file: File): Promise<{ status: string; id?: string; filename: string; indexed?: boolean; chunks?: number; job_id?: string; progress?: number; message?: string }> {
    const extension = file.name.includes('.') ? `.${file.name.split('.').pop()?.toLowerCase()}` : '';
    if (!ALLOWED_UPLOAD_EXTENSIONS.includes(extension)) {
      throw new Error('Unsupported file type. Use PDF, DOCX, Markdown, text, Python, or notebook files.');
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      throw new Error('File is too large. The maximum size is 25 MB.');
    }
    const formData = new FormData();
    formData.append('file', file);
    const token = accessToken;
    const headers: Record<string, string> = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const response = await authorizedFetch('/documents/upload', {
      method: 'POST',
      headers,
      body: formData,
    });

    if (!response.ok) {
      throw await responseError(response, `Upload failed (${response.status})`);
    }

    return UploadResponseSchema.parse(await response.json());
  },

  async getIndexJob(jobId: string): Promise<IndexJob> {
    const response = await authorizedFetch(`/documents/jobs/${encodeURIComponent(jobId)}`, {
      headers: authHeaders(),
    });
    if (!response.ok) throw new Error(`Unable to read indexing progress (${response.status})`);
    return IndexJobSchema.parse(await response.json()) as IndexJob;
  },

  async waitForIndexJob(jobId: string, timeoutMs = 180_000): Promise<IndexJob> {
    const startedAt = Date.now();
    while (Date.now() - startedAt < timeoutMs) {
      const job = await api.getIndexJob(jobId);
      if (job.status === 'finished') return job;
      if (job.status === 'failed' || job.status === 'stopped' || job.status === 'canceled') {
        throw new Error(job.error || 'Document indexing did not complete');
      }
      await new Promise((resolve) => setTimeout(resolve, 700));
    }
    throw new Error('Document indexing is still running. Check back shortly.');
  },

  async deleteDocument(id: string): Promise<{ status: string }> {
    const response = await authorizedFetch(`/documents/${id}`, {
      method: 'DELETE',
      headers: authHeaders(),
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.statusText}`);
    }

    return StatusSchema.parse(await response.json());
  },

  async clearAllDocuments(): Promise<{ status: string; deleted: number }> {
    const response = await authorizedFetch('/documents/clear-all', {
      method: 'DELETE',
      headers: authHeaders(),
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.statusText}`);
    }

    return DeleteCountSchema.parse(await response.json());
  },

  async summarizeDocument(filename: string): Promise<{ summary: string; chunks: number; filename: string }> {
    const response = await authorizedFetch('/documents/summarize', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ filename }),
    });
    if (!response.ok) {
      throw new Error(`API error: ${response.statusText}`);
    }
    return SummarySchema.parse(await response.json());
  },

  async searchDownload(query: string, maxResults: number = 3): Promise<{ status: string; downloaded: DownloadedDocument[]; message: string; job_id?: string | null }> {
    const response = await authorizedFetch('/documents/search-download', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ query, max_results: maxResults }),
    });
    if (!response.ok) {
      throw new Error(`API error: ${response.statusText}`);
    }
    return SearchDownloadSchema.parse(await response.json());
  },

  async reindexDocuments(): Promise<{ status: string; message: string; job_id?: string; progress?: number }> {
    const response = await authorizedFetch('/documents/reindex', {
      method: 'POST',
      headers: authHeaders(),
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.statusText}`);
    }

    return ReindexSchema.parse(await response.json());
  },

  // Conversations API
  async getConversations(): Promise<Conversation[]> {
    const response = await authorizedFetch('/conversation', { headers: authHeaders() });
    if (!response.ok) {
      throw new Error(`API error: ${response.statusText}`);
    }
    return z.array(ConversationSchema).parse(await response.json());
  },

  async createConversation(
    id?: string,
    conversation?: Partial<Conversation> & { pinned?: boolean },
  ): Promise<Conversation> {
    const response = await authorizedFetch('/conversation/new', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({
        id,
        title: conversation?.title || 'New Chat',
        messages: conversation?.messages || [],
        pinned: conversation?.pinned || false,
      }),
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.statusText}`);
    }

    return ConversationSchema.parse(await response.json());
  },

  async deleteConversation(id: string): Promise<{ status: string }> {
    const response = await authorizedFetch(`/conversation/${id}`, {
      method: 'DELETE',
      headers: authHeaders(),
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.statusText}`);
    }

    return StatusSchema.parse(await response.json());
  },

  async updateConversation(id: string, update: { title?: string; pinned?: boolean }): Promise<Conversation> {
    const response = await authorizedFetch(`/conversation/${id}`, {
      method: 'PUT',
      headers: authHeaders(),
      body: JSON.stringify(update),
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.statusText}`);
    }

    return ConversationSchema.parse(await response.json());
  },

  async clearConversations(): Promise<{ status: string; deleted: number }> {
    const response = await authorizedFetch('/conversation', {
      method: 'DELETE',
      headers: authHeaders(),
    });
    if (!response.ok) throw new Error(`API error: ${response.statusText}`);
    return DeleteCountSchema.parse(await response.json());
  },

  // Health check
  async healthCheck(): Promise<HealthStatus> {
    const response = await authorizedFetch('/health', { headers: authHeaders() });
    if (!response.ok) {
      throw new Error(`API error: ${response.statusText}`);
    }
    return HealthStatusSchema.parse(await response.json());
  },

  async readinessCheck(refresh = false): Promise<ReadinessStatus> {
    const response = await authorizedFetch(`/health/ready${refresh ? '?refresh=true' : ''}`, { headers: authHeaders() });
    const data = await response.json().catch(() => null);
    if (!data) {
      throw new Error(`API error: ${response.statusText}`);
    }
    return ReadinessStatusSchema.parse(data);
  },

  // Account
  async getPreferences(): Promise<UserPreferences> {
    const response = await authorizedFetch('/auth/preferences', { headers: authHeaders() });
    if (!response.ok) throw await responseError(response, 'Failed to load preferences');
    return UserPreferencesSchema.parse(await response.json());
  },

  async updatePreferences(preferences: UserPreferences): Promise<UserPreferences> {
    const response = await authorizedFetch('/auth/preferences', {
      method: 'PUT',
      headers: authHeaders(),
      body: JSON.stringify(preferences),
    });
    if (!response.ok) throw await responseError(response, 'Failed to save preferences');
    return UserPreferencesSchema.parse(await response.json());
  },

  async changePassword(currentPassword: string, newPassword: string): Promise<{ status: string; message: string }> {
    const response = await authorizedFetch('/auth/change-password', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    });
    if (!response.ok) throw await responseError(response, 'Failed to update password');
    return AccountDeleteSchema.parse(await response.json());
  },

  async exportAccountData(): Promise<AccountExport> {
    const response = await authorizedFetch('/auth/export', { headers: authHeaders() });
    if (!response.ok) throw await responseError(response, 'Failed to export account data');
    return AccountExportSchema.parse(await response.json());
  },

  async deleteAccount(): Promise<{ status: string; message: string }> {
    const response = await authorizedFetch('/auth/account', {
      method: 'DELETE',
      headers: authHeaders(),
    });
    if (!response.ok) {
      throw await responseError(response, response.statusText || 'Failed to delete account');
    }
    return AccountDeleteSchema.parse(await response.json());
  },
};
