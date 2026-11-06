import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { ApiError, api, formatApiError } from '../../api'
import type { Message, Session } from '../../api/types'

const MESSAGE_PAGE_SIZE = 30

export interface Question {
  content: string
  knowledgeBaseId: string
  knowledgeBaseName: string
}

export interface Turn extends Question {
  id: string
  answer: string
  status: 'waiting' | 'streaming' | 'checking' | 'interrupted'
  checked?: boolean
  error?: string
}

interface History {
  id: string
  messages: Message[]
  hasOlder: boolean
  loading: boolean
  error?: string
}

interface Operation {
  sessionId: string | null
  controller: AbortController
}

interface ConversationOptions {
  active: boolean
  sessionId: string | null
  onSessionCreated: (session: Session, question: Question, open: boolean) => void
  onSessionExited: () => void
  onBusyChange: (busy: boolean) => void
}

function mergeLatest(previous: Message[], latest: Message[]) {
  const last = previous.at(-1)
  if (!last) return latest

  const anchor = latest.findIndex((message) =>
    message.timestamp === last.timestamp && message.role === last.role && message.content === last.content,
  )
  return anchor === -1 ? latest : [...previous, ...latest.slice(anchor + 1)]
}

function isMissing(error: unknown) {
  return error instanceof ApiError && error.status === 404
}

export function useConversation({
  active, sessionId, onSessionCreated, onSessionExited, onBusyChange,
}: ConversationOptions) {
  const [history, setHistory] = useState<History | null>(null)
  const [turns, setTurns] = useState<Record<string, Turn>>({})
  const [busy, setBusy] = useState(false)
  const [sendError, setSendError] = useState('')
  const operation = useRef<Operation | null>(null)
  const historyRequest = useRef<AbortController | null>(null)
  const lastSession = useRef(sessionId)
  const location = useRef({ active, sessionId })
  const unfinishedNewSessions = useRef(new Set<string>())

  useLayoutEffect(() => {
    location.current = { active, sessionId }
  }, [active, sessionId])

  const readHistory = useCallback(async (id: string, offset = 0, beforeInsert?: () => void) => {
    historyRequest.current?.abort()
    const controller = new AbortController()
    historyRequest.current = controller
    setHistory((previous) => ({
      id,
      messages: offset && previous?.id === id ? previous.messages : [],
      hasOlder: Boolean(offset),
      loading: true,
    }))

    try {
      const messages = await api.listMessages(id, offset, MESSAGE_PAGE_SIZE, controller.signal)
      if (controller.signal.aborted || location.current.sessionId !== id) return
      beforeInsert?.()
      setHistory((previous) => ({
        id,
        messages: [...messages, ...(offset && previous?.id === id ? previous.messages : [])],
        hasOlder: messages.length === MESSAGE_PAGE_SIZE,
        loading: false,
      }))
    } catch (error) {
      if (controller.signal.aborted || location.current.sessionId !== id) return
      setHistory((previous) => ({
        id,
        messages: previous?.id === id ? previous.messages : [],
        hasOlder: Boolean(offset),
        loading: false,
        error: isMissing(error) ? '此会话已不存在。' : formatApiError(error, '读取消息失败'),
      }))
    }
  }, [])

  const exit = useCallback(async (id: string) => {
    // An unsaved first turn can still be retried from the history rail.
    if (unfinishedNewSessions.current.has(id)) return
    try {
      await api.exitSession(id)
      onSessionExited()
    } catch (error) {
      if (!isMissing(error)) onSessionExited()
    }
  }, [onSessionExited])

  useEffect(() => {
    const previous = lastSession.current
    lastSession.current = sessionId
    if (previous && previous !== sessionId && operation.current?.sessionId !== previous) {
      void exit(previous)
    }
  }, [exit, sessionId])

  useEffect(() => {
    setSendError('')
    if (sessionId) void readHistory(sessionId)
    else setHistory(null)
    return () => historyRequest.current?.abort()
  }, [readHistory, sessionId])

  useEffect(() => () => operation.current?.controller.abort(), [])

  function updateTurn(id: string, turn?: Turn) {
    setTurns((previous) => {
      if (turn) return { ...previous, [id]: turn }
      const next = { ...previous }
      delete next[id]
      return next
    })
  }

  function begin(id: string | null): Operation | null {
    if (operation.current) return null
    const next = { sessionId: id, controller: new AbortController() }
    operation.current = next
    setSendError('')
    setBusy(true)
    onBusyChange(true)
    return next
  }

  function finish(current: Operation) {
    if (operation.current !== current) return
    operation.current = null
    setBusy(false)
    onBusyChange(false)
    if (current.sessionId && location.current.sessionId !== current.sessionId) {
      void exit(current.sessionId)
    }
  }

  async function reconcile(id: string, turn: Turn, error: string, interrupted: boolean) {
    updateTurn(id, { ...turn, status: 'checking' })
    try {
      let latest = await api.listMessages(id, 0, MESSAGE_PAGE_SIZE)
      const containsTurn = (messages: Message[]) => messages.some((message) =>
        message.role === 'user' && message.metadata?.client_turn_id === turn.id,
      )

      if (interrupted && !containsTurn(latest)) {
        // A disconnect can arrive just before the backend commits a completed turn.
        await new Promise((resolve) => setTimeout(resolve, 400))
        latest = await api.listMessages(id, 0, MESSAGE_PAGE_SIZE)
      }

      if (location.current.sessionId === id) {
        historyRequest.current?.abort()
        setHistory((previous) => ({
          id,
          messages: mergeLatest(previous?.id === id ? previous.messages : [], latest),
          hasOlder: latest.length === MESSAGE_PAGE_SIZE,
          loading: false,
        }))
      }

      if (containsTurn(latest)) {
        unfinishedNewSessions.current.delete(id)
        updateTurn(id)
      } else {
        updateTurn(id, { ...turn, status: 'interrupted', checked: true, error })
      }
    } catch (checkError) {
      updateTurn(id, {
        ...turn,
        status: 'interrupted',
        checked: false,
        error: isMissing(checkError) ? '会话已不存在。你仍可复制本轮内容。' : '暂时无法确认这轮是否已保存，请先核对历史。',
      })
    }
  }

  async function send(question: Question, onStarted: (id: string) => void) {
    const current = begin(sessionId)
    if (!current) return

    try {
      if (!current.sessionId) {
        const firstLine = question.content.split('\n', 1)[0].trim()
        const initialTitle = Array.from(firstLine).slice(0, 72).join('')
        const session = await api.createSession(initialTitle)
        current.sessionId = session.session_id
        unfinishedNewSessions.current.add(session.session_id)
        onSessionCreated(session, question, location.current.active && !location.current.sessionId)
      }
      const id = current.sessionId
      onStarted(id)

      const turn: Turn = {
        ...question,
        id: globalThis.crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`,
        answer: '',
        status: 'waiting',
      }
      updateTurn(id, turn)

      let error = '没有找到已保存的回复，可以重试这轮。'
      let interrupted = false
      let frame = 0
      let answer = ''
      try {
        await api.streamChat({
          session_id: id,
          content: question.content,
          knowledge_base_id: question.knowledgeBaseId || null,
          metadata: {
            client_turn_id: turn.id,
            knowledge_base_id: question.knowledgeBaseId || null,
            knowledge_base_name: question.knowledgeBaseName || null,
          },
        }, (chunk) => {
          answer += chunk
          if (!frame) {
            frame = requestAnimationFrame(() => {
              frame = 0
              updateTurn(id, { ...turn, answer, status: 'streaming' })
            })
          }
        }, current.controller.signal)
      } catch (streamError) {
        interrupted = true
        error = current.controller.signal.aborted
          ? '已停止接收，下面是本轮收到的内容。'
          : formatApiError(streamError, '回复中断，已保留本轮内容。')
      } finally {
        cancelAnimationFrame(frame)
      }
      await reconcile(id, { ...turn, answer }, error, interrupted)
    } catch (error) {
      if (location.current.sessionId === sessionId) {
        setSendError(formatApiError(error, '创建会话失败，请重试。'))
      }
    } finally {
      finish(current)
    }
  }

  async function verify() {
    if (!sessionId || !turns[sessionId]) return
    const current = begin(sessionId)
    if (!current) return
    const turn = turns[sessionId]
    try {
      await reconcile(sessionId, turn, '没有找到已保存的回复，可以重试这轮。', true)
    } finally {
      finish(current)
    }
  }

  function discard(id: string) {
    unfinishedNewSessions.current.delete(id)
    updateTurn(id)
  }

  return {
    history: history?.id === sessionId ? history : null,
    turn: sessionId ? turns[sessionId] : undefined,
    busy,
    sendError,
    send,
    verify,
    discard,
    stop: () => operation.current?.controller.abort(),
    readHistory,
  }
}
