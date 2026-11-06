import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { Layers3, LibraryBig, MessagesSquare, SlidersHorizontal } from 'lucide-react'
import { Navigate, useLocation, useMatch, useNavigate } from 'react-router-dom'
import type { KnowledgeBase } from './api/types'
import ChatPage from './features/chat/ChatPage'

const LibraryPage = lazy(() => import('./features/library/LibraryPage'))
const ModelSettingsPage = lazy(() => import('./features/model-settings/ModelSettingsPage'))

interface ChatLocation {
  path: string
  sessionId: string | null
  knowledgeBaseId: string | null
}

interface ChatNavigation {
  replace?: boolean
  knowledgeBaseId?: string
}

export default function App() {
  const location = useLocation()
  const navigate = useNavigate()
  const chatMatch = useMatch('/chat/:sessionId?')
  const libraryMatch = useMatch('/library')
  const modelSettingsMatch = useMatch('/model-settings')
  const chatActive = Boolean(chatMatch)
  const libraryActive = Boolean(libraryMatch)
  const modelSettingsActive = Boolean(modelSettingsMatch)
  const [libraryVisited, setLibraryVisited] = useState(libraryActive)
  const [chatBusy, setChatBusy] = useState(false)
  const lastChat = useRef<ChatLocation>({ path: '/chat', sessionId: null, knowledgeBaseId: null })
  const sessionId = chatActive ? chatMatch?.params.sessionId ?? null : lastChat.current.sessionId
  const knowledgeBaseId = chatActive
    ? new URLSearchParams(location.search).get('kb')
    : lastChat.current.knowledgeBaseId

  useEffect(() => {
    if (chatActive) lastChat.current = { path: location.pathname + location.search, sessionId, knowledgeBaseId }
  }, [chatActive, location.pathname, location.search, sessionId, knowledgeBaseId])

  useEffect(() => {
    if (libraryActive) setLibraryVisited(true)
  }, [libraryActive])

  const navigateChat = useCallback((id: string | null, options?: ChatNavigation) => {
    const path = id ? `/chat/${encodeURIComponent(id)}` : '/chat'
    const search = options?.knowledgeBaseId ? `?${new URLSearchParams({ kb: options.knowledgeBaseId })}` : ''
    navigate(path + search, { replace: options?.replace })
  }, [navigate])

  const askFromLibrary = useCallback((knowledgeBase: KnowledgeBase) => {
    navigateChat(null, { knowledgeBaseId: knowledgeBase.id })
  }, [navigateChat])

  if (!chatActive && !libraryActive && !modelSettingsActive) return <Navigate to="/chat" replace />

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-brand">
          <span className="app-brand-mark"><Layers3 size={19} aria-hidden="true" /></span>
          <span className="app-brand-name">RAG 工作台</span>
        </div>
        <nav className="app-nav" aria-label="工作区">
          <button type="button" aria-current={chatActive ? 'page' : undefined} onClick={() => { if (!chatActive) navigate(lastChat.current.path) }}>
            <MessagesSquare size={16} aria-hidden="true" /> 对话
          </button>
          <button type="button" aria-current={libraryActive ? 'page' : undefined} disabled={chatBusy} onClick={() => { if (!libraryActive) navigate('/library') }}>
            <LibraryBig size={16} aria-hidden="true" /> 资料库
          </button>
          <button type="button" aria-current={modelSettingsActive ? 'page' : undefined} disabled={chatBusy} onClick={() => { if (!modelSettingsActive) navigate('/model-settings') }}>
            <SlidersHorizontal size={16} aria-hidden="true" /> 模型配置
          </button>
        </nav>
      </header>

      <main className="app-main">
        <section className="app-view" aria-label="对话工作区" hidden={!chatActive}>
          <ChatPage
            active={chatActive}
            sessionId={sessionId}
            queryKnowledgeBaseId={knowledgeBaseId}
            onNavigateChat={navigateChat}
            onBusyChange={setChatBusy}
          />
        </section>
        {(libraryActive || libraryVisited) && (
          <section className="app-view" aria-label="资料工作区" hidden={!libraryActive}>
            <Suspense fallback={<p className="app-loading" role="status">正在打开资料库…</p>}>
              <LibraryPage active={libraryActive} onAsk={askFromLibrary} />
            </Suspense>
          </section>
        )}
        {modelSettingsActive && (
          <section className="app-view" aria-label="模型配置工作区">
            <Suspense fallback={<p className="app-loading" role="status">正在打开模型配置…</p>}>
              <ModelSettingsPage />
            </Suspense>
          </section>
        )}
      </main>
    </div>
  )
}
