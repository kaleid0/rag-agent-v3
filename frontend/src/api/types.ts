export interface Session {
  session_id: string
  user_id: string
  created_at?: string | null
  metadata?: { title?: string | null } | null
}

export interface Message {
  role: string
  content: string
  timestamp?: string | null
  metadata?: Record<string, unknown> | null
}

export interface ChatRequest {
  session_id: string
  content: string
  knowledge_base_id?: string | null
  metadata?: Record<string, unknown>
}

export type ModelProvider = 'deepseek' | 'bailian'
export type CredentialSource = 'stored' | 'environment' | 'missing'

export interface ModelSelection {
  provider: ModelProvider
  model: string
}

export interface ModelAssignments {
  dialog: ModelSelection
  memory: ModelSelection
  rag: ModelSelection
}

export interface ModelSettings extends ModelAssignments {
  credentials: Record<ModelProvider, CredentialSource>
}

export interface UpdateModelSettingsRequest extends ModelAssignments {
  api_keys?: Partial<Record<ModelProvider, string | null>>
}

export interface KnowledgeBase {
  id: string
  name: string
  description: string
  document_ids: string[]
  document_titles: string[]
  created_at?: string | null
}

export interface CreateKnowledgeBaseRequest {
  name: string
  description?: string
  chunk_size?: number
  chunk_overlap?: number
  split_method?: 'character' | 'recursive' | 'hierarchical'
  retriever_type?: 'vector' | 'sparse' | 'hybrid'
  record_ids?: string[]
}

export type DocumentStatus = 'pending' | 'processing' | 'ready' | 'failed' | 'deleting'

export interface DocumentRecord {
  id: string
  source: string
  created_at?: string | null
  metadata?: {
    status?: DocumentStatus | null
    is_prased?: boolean
    error?: string | null
    title?: string | null
    abstract?: string | null
    keywords?: string[] | null
    directory?: string[] | null
    language?: string | null
  } | null
}
