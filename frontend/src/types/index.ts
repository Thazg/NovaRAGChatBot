export type Role = 'user' | 'assistant' | 'system';

export interface Message {
  id: string;
  role: Role;
  content: string;
  createdAt: number;
  feedback?: 'like' | 'dislike' | null;
  retrievedDocs?: RetrievedDocument[];
  interrupted?: boolean;
}

export interface RetrievedDocument {
  id: string;
  document_id: string;
  file_name: string;
  chunk_index: number;
  page: number | null;
  line_start: number | null;
  line_end: number | null;
  content: string;
}

export interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  createdAt: number;
  updatedAt: number;
  pinned?: boolean;
}
