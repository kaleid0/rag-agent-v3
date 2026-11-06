import {
  ArrowDown, ArrowUp, ArrowUpRight, BookOpen, Check, Copy, History, Menu, MessageCircle,
  Plus, RefreshCw, Square, Trash2, X,
} from 'lucide-react'
import { lazy, memo, Suspense, useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError, api, formatApiError } from '../../api'
import type { KnowledgeBase, Message, Session } from '../../api/types'
import { useConversation } from './useConversation'
import type { Turn } from './useConversation'
import './chat.css'

const AnswerContent = lazy(() => import('./AnswerContent'))
const SESSION_PAGE_SIZE = 20
const EMPTY_DRAFT = { content: '', knowledgeBaseId: '' }
const DRAFT_KEY = 'new'
const dateFormat = new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric' })

interface ChatPageProps {
  active: boolean
  sessionId: string | null
  queryKnowledgeBaseId: string | null
  onNavigateChat: (sessionId: string | null, options?: { replace?: boolean; knowledgeBaseId?: string }) => void
  onBusyChange: (busy: boolean) => void
}

function titleFor(session: Session, fallback?: string) {
  const title = session.metadata?.title
  return (typeof title === 'string' && title.trim()) || fallback || '未命名对话'
}

function displayDate(value?: string | null) {
  return value && Number.isFinite(Date.parse(value)) ? dateFormat.format(new Date(value)) : ''
}

function firstLine(value: string) {
  return value.split('\n', 1)[0].trim()
}

function scopeFor(message: Message) {
  const label = message.metadata?.knowledge_base_name
  if (typeof label === 'string' && label) return label
  if (message.metadata?.knowledge_base_id === null) return '通用对话'
  return undefined
}

const MessageBubble = memo(function MessageBubble({
  user = false, content, scope, inProgress = false,
}: { user?: boolean; content: string; scope?: string; inProgress?: boolean }) {
  const [copyStatus, setCopyStatus] = useState<'idle' | 'copied' | 'failed'>('idle')

  async function copy() {
    try {
      await navigator.clipboard.writeText(content)
      setCopyStatus('copied')
    } catch {
      setCopyStatus('failed')
    }
  }

  return (
    <article className={`chat-message ${user ? 'chat-message-user' : 'chat-message-assistant'}`}>
      <div className="chat-message-head">
        {!user && <span className="chat-assistant-mark" aria-hidden="true"><MessageCircle size={14} /></span>}
        <span>{user ? '你' : '资料助手'}</span>
        {scope && <span className="chat-scope-tag" title={scope}><BookOpen size={13} aria-hidden="true" />{scope}</span>}
      </div>
      {user
        ? <p className="chat-pre-wrap">{content}</p>
        : <Suspense fallback={<p className="chat-pre-wrap">{content}</p>}><AnswerContent content={content} /></Suspense>}
      {!user && !inProgress && content && (
        <button type="button" className="button button-ghost chat-copy" onClick={() => void copy()}>
          {copyStatus === 'copied' ? <Check size={15} aria-hidden="true" /> : <Copy size={15} aria-hidden="true" />}
          {copyStatus === 'copied' ? '已复制' : copyStatus === 'failed' ? '复制失败，重试' : '复制回复'}
        </button>
      )}
    </article>
  )
})

function PendingTurn({ turn, onRetry, onVerify, onDiscard }: {
  turn: Turn; onRetry: () => void; onVerify: () => void; onDiscard: () => void;
}) {
  const interrupted = turn.status === 'interrupted'
  return (
    <>
      <MessageBubble user content={turn.content} scope={turn.knowledgeBaseName || '通用对话'} />
      {turn.answer && <MessageBubble content={turn.answer} inProgress={!interrupted} />}
      {interrupted ? (
        <div className="chat-interrupted" role="status">
          <p><strong>本轮回复未确认保存</strong><span>{turn.error}</span></p>
          <div>
            {turn.checked
              ? <button type="button" className="button button-secondary" onClick={onRetry}>编辑后重试</button>
              : <button type="button" className="button button-secondary" onClick={onVerify}>核对历史</button>}
            <button type="button" className="button button-ghost" onClick={onDiscard}>关闭本轮</button>
          </div>
        </div>
      ) : (
        <div className="chat-generation-status" role="status">
          <span className="chat-status-dot" aria-hidden="true" />
          {turn.status === 'waiting' ? '正在准备回复' : turn.status === 'checking' ? '正在核对保存状态' : '正在生成'}
        </div>
      )}
    </>
  )
}

export default function ChatPage({ active, sessionId, queryKnowledgeBaseId, onNavigateChat, onBusyChange }: ChatPageProps) {
  const [sessions, setSessions] = useState<Session[]>([])
  const [sessionsLoading, setSessionsLoading] = useState(false)
  const [sessionsError, setSessionsError] = useState('')
  const [hasMoreSessions, setHasMoreSessions] = useState(false)
  const [drafts, setDrafts] = useState<Record<string, typeof EMPTY_DRAFT>>({})
  const [catalog, setCatalog] = useState<KnowledgeBase[]>([])
  const [catalogLoading, setCatalogLoading] = useState(true)
  const [catalogError, setCatalogError] = useState('')
  const [railOpen, setRailOpen] = useState(false)
  const [showJump, setShowJump] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<Session | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState('')

  const sessionRequest = useRef<AbortController | null>(null)
  const catalogRequest = useRef<AbortController | null>(null)
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const scroll = useRef<HTMLDivElement>(null)
  const thread = useRef<HTMLDivElement>(null)
  const followLatest = useRef(true)
  const olderAnchor = useRef<number | null>(null)
  const textarea = useRef<HTMLTextAreaElement>(null)
  const form = useRef<HTMLFormElement>(null)
  const deleteDialog = useRef<HTMLDialogElement>(null)
  const openHistoryButton = useRef<HTMLButtonElement>(null)
  const closeHistoryButton = useRef<HTMLButtonElement>(null)
  const focusedSessionId = useRef(sessionId)

  const draftKey = sessionId || DRAFT_KEY
  const draft = drafts[draftKey] || EMPTY_DRAFT
  const selectedKnowledgeBase = catalog.find((item) => item.id === draft.knowledgeBaseId)
  const scopeUnavailable = Boolean(draft.knowledgeBaseId && !selectedKnowledgeBase)

  const loadSessions = useCallback(async (offset = 0, background = false) => {
    if (background && sessionRequest.current) return
    sessionRequest.current?.abort()
    const controller = new AbortController()
    sessionRequest.current = controller
    if (!background) setSessionsLoading(true)
    setSessionsError('')

    try {
      const page = await api.listSessions(offset, SESSION_PAGE_SIZE, controller.signal)
      if (controller.signal.aborted) return
      setSessions((previous) => {
        if (offset) {
          const present = new Set(previous.map((item) => item.session_id))
          return [...previous, ...page.filter((item) => !present.has(item.session_id))]
        }
        if (background && previous.length > SESSION_PAGE_SIZE) {
          const present = new Set(page.map((item) => item.session_id))
          return [...page, ...previous.filter((item) => !present.has(item.session_id))]
        }
        return page
      })
      if (!background) setHasMoreSessions(page.length === SESSION_PAGE_SIZE)
    } catch (error) {
      if (!controller.signal.aborted && !background) {
        setSessionsError(formatApiError(error, '读取对话记录失败。'))
      }
    } finally {
      if (sessionRequest.current === controller) {
        sessionRequest.current = null
        setSessionsLoading(false)
      }
    }
  }, [])

  const loadCatalog = useCallback(async () => {
    catalogRequest.current?.abort()
    const controller = new AbortController()
    catalogRequest.current = controller
    setCatalogLoading(true)
    setCatalogError('')

    try {
      const items = await api.listKnowledgeBases(controller.signal)
      if (!controller.signal.aborted) setCatalog(items)
    } catch (error) {
      if (!controller.signal.aborted) setCatalogError(formatApiError(error, '知识库列表暂不可用。'))
    } finally {
      if (!controller.signal.aborted) setCatalogLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!active) return
    void loadSessions()
    void loadCatalog()
    return () => {
      sessionRequest.current?.abort()
      catalogRequest.current?.abort()
      clearTimeout(refreshTimer.current)
    }
  }, [active, loadCatalog, loadSessions])

  const onSessionExited = useCallback(() => {
    clearTimeout(refreshTimer.current)
    // The exit endpoint schedules title generation and returns before it finishes.
    refreshTimer.current = setTimeout(() => { void loadSessions(0, true) }, 1200)
  }, [loadSessions])

  const { history, turn, busy, sendError, send, verify, discard, stop, readHistory } = useConversation({
    active,
    sessionId,
    onSessionExited,
    onBusyChange,
    onSessionCreated: (session, question, open) => {
      setSessions((previous) => [session, ...previous.filter((item) => item.session_id !== session.session_id)])
      void loadSessions()
      setDrafts((previous) => ({
        ...previous,
        [DRAFT_KEY]: { ...previous[DRAFT_KEY], content: '', knowledgeBaseId: previous[DRAFT_KEY]?.knowledgeBaseId || '' },
        [session.session_id]: { content: '', knowledgeBaseId: question.knowledgeBaseId },
      }))
      if (open) onNavigateChat(session.session_id, { replace: true })
    },
  })

  useEffect(() => {
    if (!active || sessionId || !queryKnowledgeBaseId) return
    setDrafts((previous) => ({
      ...previous,
      [DRAFT_KEY]: { ...EMPTY_DRAFT, ...previous[DRAFT_KEY], knowledgeBaseId: queryKnowledgeBaseId },
    }))
    onNavigateChat(null, { replace: true })
  }, [active, onNavigateChat, queryKnowledgeBaseId, sessionId])

  useEffect(() => {
    if (!sessionId || !history?.messages.length) return
    const lastQuestion = history.messages.slice().reverse().find((message) => message.role === 'user')
    const scope = lastQuestion?.metadata?.knowledge_base_id
    if (typeof scope !== 'string' || !scope) return
    setDrafts((previous) => previous[sessionId] ? previous : {
      ...previous, [sessionId]: { content: '', knowledgeBaseId: scope },
    })
  }, [history?.messages, sessionId])

  useLayoutEffect(() => {
    focusedSessionId.current = sessionId
    olderAnchor.current = null
    followLatest.current = true
    setShowJump(false)
  }, [sessionId])

  useLayoutEffect(() => {
    const container = scroll.current
    if (!container || !active) return
    if (olderAnchor.current !== null) {
      container.scrollTop = container.scrollHeight - olderAnchor.current
      olderAnchor.current = null
    } else if (followLatest.current) {
      container.scrollTop = container.scrollHeight
    }
  }, [active, history?.messages, sessionId, turn?.answer, turn?.status])

  useEffect(() => {
    if (!active || !thread.current) return
    const observer = new ResizeObserver(() => {
      if (followLatest.current && scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight
    })
    observer.observe(thread.current)
    return () => observer.disconnect()
  }, [active])

  useEffect(() => {
    if (!active || !railOpen) return
    closeHistoryButton.current?.focus()
    function dismiss(event: KeyboardEvent) {
      if (event.key === 'Escape' && !deleteDialog.current?.open) {
        setRailOpen(false)
        openHistoryButton.current?.focus()
      }
    }
    window.addEventListener('keydown', dismiss)
    return () => window.removeEventListener('keydown', dismiss)
  }, [active, railOpen])

  useEffect(() => {
    const dialog = deleteDialog.current
    if (active && deleteTarget && dialog && !dialog.open) dialog.showModal()
    if ((!active || !deleteTarget) && dialog?.open) dialog.close()
  }, [active, deleteTarget])

  const selectedSession = sessions.find((item) => item.session_id === sessionId)
  const fallbackTitle = history && !history.hasOlder
    ? firstLine(history.messages.find((message) => message.role === 'user')?.content || '')
    : undefined
  const pageTitle = sessionId ? (selectedSession ? titleFor(selectedSession, fallbackTitle || undefined) : fallbackTitle || '对话') : '新对话'
  const historyReady = !sessionId || Boolean(history && !history.loading && (!history.error || history.messages.length))
  const canSend = Boolean(draft.content.trim() && !busy && !turn && !scopeUnavailable && historyReady)

  function updateDraft(next: Partial<typeof EMPTY_DRAFT>) {
    setDrafts((previous) => ({ ...previous, [draftKey]: { ...EMPTY_DRAFT, ...previous[draftKey], ...next } }))
  }

  function jumpToLatest() {
    followLatest.current = true
    setShowJump(false)
    if (scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight
  }

  function trackScroll() {
    const container = scroll.current
    if (!container) return
    const closeToLatest = container.scrollHeight - container.scrollTop - container.clientHeight < 72
    followLatest.current = closeToLatest
    setShowJump(!closeToLatest)
  }

  function navigate(id: string | null) {
    if (busy || deleting) return
    setRailOpen(false)
    if (id !== sessionId) onNavigateChat(id)
    if (!id) window.requestAnimationFrame(() => textarea.current?.focus())
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!canSend) return
    jumpToLatest()
    void send({
      content: draft.content.trim(),
      knowledgeBaseId: draft.knowledgeBaseId,
      knowledgeBaseName: selectedKnowledgeBase ? optionLabel(selectedKnowledgeBase) : '',
    }, (id) => {
      if (sessionId === id) updateDraft({ content: '' })
    })
  }

  function retry() {
    if (!sessionId || !turn?.checked) return
    updateDraft({ content: turn.content, knowledgeBaseId: turn.knowledgeBaseId })
    discard(sessionId)
    window.requestAnimationFrame(() => textarea.current?.focus())
  }

  async function removeSession() {
    if (!deleteTarget || deleting || busy) return
    const id = deleteTarget.session_id
    setDeleting(true)
    setDeleteError('')
    try {
      await api.deleteSession(id)
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 404)) {
        setDeleteError(formatApiError(error, '删除对话失败，请重试。'))
        setDeleting(false)
        return
      }
    }
    discard(id)
    setSessions((previous) => previous.filter((item) => item.session_id !== id))
    setDrafts((previous) => {
      const next = { ...previous }
      delete next[id]
      return next
    })
    if (focusedSessionId.current === id) onNavigateChat(null, { replace: true })
    setDeleteTarget(null)
    setDeleting(false)
    void loadSessions()
  }

  function optionLabel(item: KnowledgeBase) {
    return catalog.some((other) => other.name === item.name && other.id !== item.id)
      ? `${item.name} · ${item.id.slice(-6)}`
      : item.name
  }

  const starterQuestions = selectedKnowledgeBase
    ? ['这份资料主要讲了什么？', '提炼资料中的关键结论']
    : ['帮我梳理一个研究问题', '把复杂概念解释给初学者']

  return (
    <div className="chat-workspace" aria-label="对话工作区">
      {railOpen && <button type="button" className="chat-rail-backdrop" onClick={() => {
        setRailOpen(false)
        openHistoryButton.current?.focus()
      }} aria-label="关闭对话记录" />}
      <aside id="chat-history" className={`chat-rail ${railOpen ? 'is-open' : ''}`} aria-label="对话记录">
        <div className="chat-rail-heading">
          <span><History size={16} aria-hidden="true" />对话记录</span>
          <button type="button" className="icon-button" aria-label="刷新对话记录" title="刷新对话记录" disabled={sessionsLoading} onClick={() => void loadSessions()}>
            <RefreshCw size={16} aria-hidden="true" />
          </button>
          <button type="button" ref={closeHistoryButton} className="icon-button chat-mobile-toggle" aria-label="关闭对话记录" onClick={() => {
            setRailOpen(false)
            openHistoryButton.current?.focus()
          }}>
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <button type="button" className="button button-primary chat-new-button" disabled={busy || deleting} onClick={() => navigate(null)}>
          <Plus size={17} aria-hidden="true" />新对话
        </button>
        <div className="chat-rail-scroll">
          {sessionsError && <p className="chat-rail-note" role="status">{sessionsError}</p>}
          {!sessions.length && !sessionsError && <p className="chat-rail-note">{sessionsLoading ? '正在读取记录' : '历史对话将在这里显示。'}</p>}
          <ul className="chat-session-list">
            {sessions.map((session) => {
              const id = session.session_id
              const title = titleFor(session, id === sessionId ? fallbackTitle : undefined)
              return (
                <li className={id === sessionId ? 'is-current' : undefined} key={id}>
                  <button type="button" className="chat-session-link" disabled={busy || deleting} aria-current={id === sessionId ? 'page' : undefined} title={title} onClick={() => navigate(id)}>
                    <MessageCircle size={15} aria-hidden="true" />
                    <span>{title}</span>
                    <small>{displayDate(session.created_at)}</small>
                  </button>
                  <button type="button" className="icon-button chat-session-delete" aria-label={`删除对话：${title}`} title="删除对话" disabled={busy || deleting} onClick={() => {
                    setDeleteError('')
                    setDeleteTarget(session)
                  }}>
                    <Trash2 size={15} aria-hidden="true" />
                  </button>
                </li>
              )
            })}
          </ul>
          {hasMoreSessions && (
            <button type="button" className="button button-ghost chat-older-sessions" disabled={sessionsLoading || busy || deleting} onClick={() => void loadSessions(sessions.length)}>
              {sessionsLoading ? '读取中' : '更多对话'}
            </button>
          )}
        </div>
      </aside>

      <section className="chat-main" aria-labelledby="chat-title">
        <header className="chat-titlebar">
          <button type="button" ref={openHistoryButton} className="icon-button chat-mobile-toggle" aria-label="打开对话记录" aria-controls="chat-history" aria-expanded={railOpen} onClick={() => setRailOpen(true)}>
            <Menu size={19} aria-hidden="true" />
          </button>
          <h1 id="chat-title">{pageTitle}</h1>
        </header>

        <div className="chat-scroll-frame">
          <div className="chat-scroll" ref={scroll} onScroll={trackScroll}>
            <div ref={thread} className={`chat-thread ${!sessionId && !turn ? 'chat-thread-empty' : ''}`}>
              {!sessionId && (
                <div className="chat-welcome">
                  <div className="chat-welcome-icon"><MessageCircle size={28} aria-hidden="true" /></div>
                  <h2>想一起研究什么？</h2>
                  <p>从一个问题开始，也可以先选定知识库，让问题围绕你的资料展开。</p>
                  <div className="chat-starters">
                    {starterQuestions.map((question) => (
                      <button key={question} type="button" className="button button-secondary" disabled={busy} onClick={() => {
                        updateDraft({ content: question })
                        textarea.current?.focus()
                      }}>
                        {question}<ArrowUpRight size={15} aria-hidden="true" />
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {sessionId && (!history || (history.loading && !history.messages.length)) && !turn && (
                <p className="chat-thread-note" role="status">正在读取对话</p>
              )}
              {history?.error && (
                <div className="chat-thread-note" role="status">
                  <p>{history.error}</p>
                  <button type="button" className="button button-secondary" disabled={busy} onClick={() => sessionId && void readHistory(sessionId)}>重新读取</button>
                </div>
              )}
              {history?.hasOlder && (
                <button type="button" className="button button-secondary chat-older-messages" disabled={history.loading || busy} onClick={() => {
                  if (sessionId) void readHistory(sessionId, history.messages.length, () => {
                    if (scroll.current) olderAnchor.current = scroll.current.scrollHeight - scroll.current.scrollTop
                  })
                }}>
                  {history.loading ? '正在读取更早消息' : '查看更早消息'}
                </button>
              )}
              {history && !history.loading && !history.error && !history.messages.length && !turn && (
                <p className="chat-thread-note">输入第一个问题，继续这段对话。</p>
              )}
              {history?.messages.map((message, index) => (
                <MessageBubble key={message.timestamp ? `${message.timestamp}-${message.role}` : `legacy-${history.messages.length - index}`} user={message.role === 'user'} content={message.content} scope={scopeFor(message)} />
              ))}
              {turn && <PendingTurn turn={turn} onRetry={retry} onVerify={() => void verify()} onDiscard={() => sessionId && discard(sessionId)} />}
            </div>
          </div>
          {showJump && (
            <button type="button" className="button button-secondary chat-jump" onClick={jumpToLatest}>
              <ArrowDown size={15} aria-hidden="true" />回到最新
            </button>
          )}
        </div>

        <footer className="chat-composer-area">
          <form className="chat-composer" ref={form} onSubmit={submit}>
            <label className="chat-visually-hidden" htmlFor="chat-input">输入问题</label>
            <textarea id="chat-input" ref={textarea} rows={2} value={draft.content} disabled={busy || Boolean(turn)} placeholder="输入你的问题…" onChange={(event) => updateDraft({ content: event.target.value })} onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) {
                event.preventDefault()
                if (canSend) form.current?.requestSubmit()
              }
            }} />
            <div className="chat-composer-actions">
              <label className="chat-scope-control">
                <BookOpen size={16} aria-hidden="true" />
                <span className="chat-visually-hidden">本轮知识库</span>
                <select value={draft.knowledgeBaseId} onChange={(event) => updateDraft({ knowledgeBaseId: event.target.value })} disabled={busy || Boolean(turn)}>
                  <option value="">通用对话</option>
                  {scopeUnavailable && <option value={draft.knowledgeBaseId} disabled>{catalogLoading ? '正在确认知识库' : '所选知识库不可用'}</option>}
                  {catalog.map((item) => <option key={item.id} value={item.id}>{optionLabel(item)}</option>)}
                </select>
              </label>
              {turn?.status === 'waiting' || turn?.status === 'streaming' ? (
                <button type="button" className="button button-secondary" onClick={stop}><Square size={14} aria-hidden="true" />停止接收</button>
              ) : (
                <button type="submit" className="button button-primary" disabled={!canSend}>
                  {busy && !sessionId ? '正在创建' : '发送'}<ArrowUp size={17} aria-hidden="true" />
                </button>
              )}
            </div>
          </form>
          <div className="chat-composer-caption">
            {sendError && <span className="chat-composer-error" role="status">{sendError}</span>}
            {!sendError && (catalogError || (scopeUnavailable && !catalogLoading)) && (
              <span className="chat-composer-error" role="status">
                {catalogError || '请选择一个可用的知识库或切换为通用对话。'}
                {catalogError && <button type="button" className="button button-ghost" onClick={() => void loadCatalog()}>刷新知识库</button>}
              </span>
            )}
            {!sendError && !catalogError && !scopeUnavailable && <span className="chat-keyboard-hint">Enter 发送 · Shift + Enter 换行</span>}
          </div>
        </footer>
      </section>

      <dialog className="chat-delete-dialog" ref={deleteDialog} aria-labelledby="chat-delete-title" onCancel={(event) => {
        event.preventDefault()
        if (!deleting) setDeleteTarget(null)
      }}>
        {deleteTarget && (
          <>
            <h2 id="chat-delete-title">删除这段对话？</h2>
            <p>「{titleFor(deleteTarget, deleteTarget.session_id === sessionId ? fallbackTitle : undefined)}」中的消息和相关会话记忆将被删除。</p>
            {deleteError && <p className="chat-composer-error" role="alert">{deleteError}</p>}
            <div className="chat-dialog-actions">
              <button type="button" className="button button-secondary" autoFocus disabled={deleting} onClick={() => setDeleteTarget(null)}>取消</button>
              <button type="button" className="button button-danger" disabled={deleting} onClick={() => void removeSession()}>{deleting ? '正在删除' : '删除对话'}</button>
            </div>
          </>
        )}
      </dialog>
    </div>
  )
}
