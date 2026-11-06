import type { ChatRequest, CreateKnowledgeBaseRequest, DocumentRecord, KnowledgeBase, Message, ModelSettings, Session, UpdateModelSettingsRequest } from './types'

const BASE = '/api/v1'
const DEMO_USER_ID = import.meta.env.VITE_DEMO_USER_ID?.trim() || 'streamlit_user'

export class ApiError extends Error {
  constructor(readonly status: number, readonly detail: unknown) {
    super(typeof detail === 'string' ? detail : `HTTP ${status}`)
    this.name = 'ApiError'
  }
}

export function formatApiError(error: unknown, fallback = '操作失败，请稍后再试。'): string {
  if (error instanceof ApiError) {
    switch (error.status) {
      case 404: return '该记录已不存在，请刷新后重试。'
      case 409: return '资源正在处理或状态已变化，请刷新后重试。'
      case 413: return '文件超过服务端允许的大小。'
      case 415: return '服务端不支持该文件类型。'
      case 422: return '服务端无法处理当前内容，请检查后重试。'
      default: return fallback
    }
  }
  if (error instanceof TypeError) return '连接中断或服务不可用，请检查后重试。'
  return fallback
}

async function fetchApi(path: string, options?: RequestInit): Promise<Response> {
  const response = await fetch(`${BASE}${path}`, options)
  if (!response.ok) {
    const error = await response.json().catch(() => undefined) as { detail?: unknown } | undefined
    throw new ApiError(response.status, error?.detail)
  }
  return response
}

async function json<T>(path: string, options?: RequestInit): Promise<T> {
  return (await fetchApi(path, options)).json() as Promise<T>
}

function postJson(body: object, signal?: AbortSignal): RequestInit {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  }
}

function sessionPath(id: string) {
  return `/sessions/${encodeURIComponent(id)}`
}

function knowledgeBasePath(id: string) {
  return `/knowledge-bases/${encodeURIComponent(id)}`
}

export const api = {
  getModelSettings(signal?: AbortSignal) {
    return json<ModelSettings>('/model-settings', { signal })
  },
  updateModelSettings(request: UpdateModelSettingsRequest) {
    return json<ModelSettings>('/model-settings', { ...postJson(request), method: 'PUT' })
  },
  listSessions(offset = 0, limit = 20, signal?: AbortSignal) {
    const params = new URLSearchParams({ user_id: DEMO_USER_ID, offset: String(offset), limit: String(limit), order: 'desc' })
    return json<Session[]>(`/session-list?${params}`, { signal })
  },
  createSession(title?: string) {
    return json<Session>('/sessions', postJson({
      user_id: DEMO_USER_ID,
      metadata: title ? { title } : undefined,
    }))
  },
  listMessages(id: string, offset = 0, limit = 50, signal?: AbortSignal) {
    return json<Message[]>(`${sessionPath(id)}/messages?offset=${offset}&limit=${limit}`, { signal })
  },
  async exitSession(id: string) {
    await fetchApi(`${sessionPath(id)}/exit`, { method: 'POST' })
  },
  async deleteSession(id: string) {
    await fetchApi(sessionPath(id), { method: 'DELETE' })
  },
  async streamChat(request: ChatRequest, onChunk: (chunk: string) => void, signal: AbortSignal) {
    const response = await fetchApi('/chat-stream', postJson(request, signal))
    if (!response.body || !response.headers.get('content-type')?.startsWith('text/plain')) {
      throw new Error('Invalid chat stream response')
    }

    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
    try {
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        onChunk(value)
      }
    } finally {
      reader.releaseLock()
    }
  },
  async listKnowledgeBases(signal?: AbortSignal) {
    const items: KnowledgeBase[] = []
    const limit = 100
    for (;;) {
      const page = await json<{ knowledge_base_list: KnowledgeBase[] }>(`/knowledge-bases?skip=${items.length}&limit=${limit}`, { signal })
      items.push(...page.knowledge_base_list)
      if (page.knowledge_base_list.length < limit) return items
    }
  },
  createKnowledgeBase(request: CreateKnowledgeBaseRequest) {
    return json<KnowledgeBase>('/knowledge-bases', postJson(request))
  },
  listKnowledgeBaseFiles(id: string, signal?: AbortSignal) {
    return json<DocumentRecord[]>(`${knowledgeBasePath(id)}/files`, { signal })
  },
  async deleteKnowledgeBase(id: string) {
    await fetchApi(knowledgeBasePath(id), { method: 'DELETE' })
  },
  async addKnowledgeBaseFile(id: string, fileId: string) {
    await fetchApi(`${knowledgeBasePath(id)}/files/${encodeURIComponent(fileId)}`, { method: 'POST' })
  },
  async removeKnowledgeBaseFile(id: string, fileId: string) {
    await fetchApi(`${knowledgeBasePath(id)}/files/${encodeURIComponent(fileId)}`, { method: 'DELETE' })
  },
  async listDocuments(signal?: AbortSignal) {
    return (await json<{ documents: DocumentRecord[] }>('/document', { signal })).documents
  },
  uploadDocument(file: File) {
    const body = new FormData()
    body.append('file', file)
    return json<DocumentRecord>('/document/upload', { method: 'POST', body })
  },
  async deleteDocument(id: string) {
    await fetchApi(`/document/${encodeURIComponent(id)}`, { method: 'DELETE' })
  },
}
