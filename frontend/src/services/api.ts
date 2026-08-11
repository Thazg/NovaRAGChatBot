const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const MAX_UPLOAD_BYTES = 25 * 1024 * 1024;
const ALLOWED_UPLOAD_EXTENSIONS = ['.pdf', '.md', '.markdown', '.rst', '.txt', '.py', '.docx', '.ipynb'];

function getToken(): string | null {
  try {
    const raw = localStorage.getItem('rag-chat-storage');
    if (raw) {
      const parsed = JSON.parse(raw);
      return parsed?.state?.token || null;
    }
  } catch {}
  return null;
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

export interface AuthResponse {
  token: string;
  user_id: string;
  username: string;
}

export const auth = {
  async register(username: string, password: string): Promise<AuthResponse> {
    const res = await fetch(`${API_BASE_URL}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Registration failed');
    }
    return res.json();
  },

  async login(username: string, password: string): Promise<AuthResponse> {
    const res = await fetch(`${API_BASE_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Login failed');
    }
    return res.json();
  },

  async me(token?: string): Promise<{ user_id: string }> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    const activeToken = token || getToken();
    if (activeToken) headers.Authorization = `Bearer ${activeToken}`;
    const res = await fetch(`${API_BASE_URL}/auth/me`, { headers });
    if (!res.ok) throw new Error('Session expired');
    return res.json();
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

export interface Conversation {
  id: string;
  title: string;
  messages: any[];
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
}

export interface ReadinessStatus {
  status: 'ready' | 'degraded';
  ready: boolean;
  provider_status: string;
  model?: string;
  model_available?: boolean;
  message: string;
  checked_at?: number;
}

export const api = {
  async sendMessage(sessionId: string, question: string, abortSignal?: AbortSignal): Promise<ChatResponse> {
    const response = await fetch(`${API_BASE_URL}/chat`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ session_id: sessionId, question }),
      signal: abortSignal,
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.statusText}`);
    }

    return response.json();
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
  ): Promise<void> {
    const body: Record<string, any> = { session_id: sessionId, question, stream: true };
    if (instructions) body.instructions = instructions;
    if (language && language !== 'auto') body.language = language;
    if (regenerate) body.regenerate = true;
    const response = await fetch(`${API_BASE_URL}/chat/stream`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(body),
      signal: abortSignal,
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.statusText}`);
    }

    if (!response.body) {
      throw new Error('ReadableStream not supported by this browser.');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

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
          const parsed = JSON.parse(jsonStr);
          if (parsed.token) {
            onToken(parsed.token);
          } else if (parsed.action === 'search_offer') {
            onAction?.({ type: 'search_offer', query: parsed.query || '' });
          }
          } catch {
            // Incomplete JSON or other format, ignore for now
          }
        }
      }
    } catch (streamError: any) {
      // StreamClosed / AbortError — expected when user cancels or connection drops
      if (streamError.name === 'AbortError' || streamError.message?.includes('StreamClosed')) {
        return;
      }
      throw streamError;
    }
  },

  // Documents API
  async getDocuments(): Promise<Document[]> {
    const response = await fetch(`${API_BASE_URL}/documents`, { headers: authHeaders() });
    if (!response.ok) {
      throw new Error(`API error: ${response.statusText}`);
    }
    return response.json();
  },

  async uploadDocument(file: File): Promise<{ status: string; filename: string; indexed?: boolean; chunks?: number; message?: string }> {
    const extension = file.name.includes('.') ? `.${file.name.split('.').pop()?.toLowerCase()}` : '';
    if (!ALLOWED_UPLOAD_EXTENSIONS.includes(extension)) {
      throw new Error('Unsupported file type. Use PDF, DOCX, Markdown, text, Python, or notebook files.');
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      throw new Error('File is too large. The maximum size is 25 MB.');
    }
    const formData = new FormData();
    formData.append('file', file);
    const token = getToken();
    const headers: Record<string, string> = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const response = await fetch(`${API_BASE_URL}/documents/upload`, {
      method: 'POST',
      headers,
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail || `Upload failed (${response.status})`);
    }

    return response.json();
  },

  async deleteDocument(id: string): Promise<{ status: string }> {
    const response = await fetch(`${API_BASE_URL}/documents/${id}`, {
      method: 'DELETE',
      headers: authHeaders(),
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.statusText}`);
    }

    return response.json();
  },

  async clearAllDocuments(): Promise<{ status: string; deleted: number }> {
    const response = await fetch(`${API_BASE_URL}/documents/clear-all`, {
      method: 'DELETE',
      headers: authHeaders(),
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.statusText}`);
    }

    return response.json();
  },

  async summarizeDocument(filename: string): Promise<{ summary: string; chunks: number; filename: string }> {
    const response = await fetch(`${API_BASE_URL}/documents/summarize`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ filename }),
    });
    if (!response.ok) {
      throw new Error(`API error: ${response.statusText}`);
    }
    return response.json();
  },

  async searchDownload(query: string, maxResults: number = 3): Promise<{ status: string; downloaded: any[]; message: string }> {
    const response = await fetch(`${API_BASE_URL}/documents/search-download`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ query, max_results: maxResults }),
    });
    if (!response.ok) {
      throw new Error(`API error: ${response.statusText}`);
    }
    return response.json();
  },

  async reindexDocuments(): Promise<{ status: string; message: string }> {
    const response = await fetch(`${API_BASE_URL}/documents/reindex`, {
      method: 'POST',
      headers: authHeaders(),
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.statusText}`);
    }

    return response.json();
  },

  // Conversations API
  async getConversations(token?: string): Promise<Conversation[]> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    const t = token || getToken();
    if (t) headers['Authorization'] = `Bearer ${t}`;
    const response = await fetch(`${API_BASE_URL}/conversation`, { headers });
    if (!response.ok) {
      throw new Error(`API error: ${response.statusText}`);
    }
    return response.json();
  },

  async createConversation(
    id?: string,
    conversation?: Partial<Conversation> & { pinned?: boolean },
  ): Promise<Conversation> {
    const response = await fetch(`${API_BASE_URL}/conversation/new`, {
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

    return response.json();
  },

  async deleteConversation(id: string): Promise<{ status: string }> {
    const response = await fetch(`${API_BASE_URL}/conversation/${id}`, {
      method: 'DELETE',
      headers: authHeaders(),
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.statusText}`);
    }

    return response.json();
  },

  async updateConversation(id: string, update: { title?: string; pinned?: boolean }): Promise<Conversation> {
    const response = await fetch(`${API_BASE_URL}/conversation/${id}`, {
      method: 'PUT',
      headers: authHeaders(),
      body: JSON.stringify(update),
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.statusText}`);
    }

    return response.json();
  },

  async clearConversations(): Promise<{ status: string; deleted: number }> {
    const response = await fetch(`${API_BASE_URL}/conversation`, {
      method: 'DELETE',
      headers: authHeaders(),
    });
    if (!response.ok) throw new Error(`API error: ${response.statusText}`);
    return response.json();
  },

  // Health check
  async healthCheck(): Promise<HealthStatus> {
    const response = await fetch(`${API_BASE_URL}/health`, { headers: authHeaders() });
    if (!response.ok) {
      throw new Error(`API error: ${response.statusText}`);
    }
    return response.json();
  },

  async readinessCheck(): Promise<ReadinessStatus> {
    const response = await fetch(`${API_BASE_URL}/health/ready`, { headers: authHeaders() });
    const data = await response.json().catch(() => null);
    if (!data) {
      throw new Error(`API error: ${response.statusText}`);
    }
    return data;
  },

  // Account
  async deleteAccount(): Promise<{ status: string; message: string }> {
    const response = await fetch(`${API_BASE_URL}/auth/account`, {
      method: 'DELETE',
      headers: authHeaders(),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(err.detail || 'Failed to delete account');
    }
    return response.json();
  },
};
