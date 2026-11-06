import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  CircleAlert,
  FileText,
  FolderOpen,
  LibraryBig,
  LoaderCircle,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  Upload,
  X,
} from 'lucide-react'
import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from 'react'
import { api, formatApiError } from '../../api'
import type { CreateKnowledgeBaseRequest, DocumentRecord, DocumentStatus, KnowledgeBase } from '../../api/types'
import './library.css'

type LibraryTab = 'knowledge' | 'documents'
type DocumentFilter = 'all' | 'ready' | 'working' | 'failed'
type DisplayDocumentStatus = DocumentStatus | 'unknown'
type OperationResult = { name: string; status: 'working' | 'done' | 'failed'; detail: string }
type DeleteTarget =
  | { kind: 'knowledge'; knowledgeBase: KnowledgeBase }
  | { kind: 'document'; document: DocumentRecord }
  | { kind: 'member'; knowledgeBase: KnowledgeBase; document: DocumentRecord }

interface LibraryPageProps {
  active: boolean
  onAsk: (knowledgeBase: KnowledgeBase) => void
}

const documentStates: Record<DisplayDocumentStatus, { label: string; tone: string }> = {
  pending: { label: '等待解析', tone: 'warning' },
  processing: { label: '解析中', tone: 'warning' },
  ready: { label: '解析完成', tone: 'success' },
  failed: { label: '解析失败', tone: 'danger' },
  deleting: { label: '删除中', tone: 'warning' },
  unknown: { label: '状态未知', tone: 'neutral' },
}

const dateFormatter = new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium' })
const acceptedFiles = '.pdf,.docx,.doc,.txt,.md'

function documentStatus(document: DocumentRecord): DisplayDocumentStatus {
  const status = document.metadata?.status
  if (status && Object.hasOwn(documentStates, status)) return status
  return document.metadata?.is_prased ? 'ready' : 'unknown'
}

function documentTitle(document: DocumentRecord) {
  return document.metadata?.title?.trim() || document.source || '未命名文档'
}

function formatDate(value: string | null | undefined) {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : dateFormatter.format(date)
}

function isWorking(status: DisplayDocumentStatus) {
  return status === 'pending' || status === 'processing' || status === 'deleting'
}

function DocumentBadge({ document }: { document: DocumentRecord }) {
  const status = documentStatus(document)
  const { tone, label } = documentStates[status]
  return (
    <span className={`status-badge library-badge library-badge-${tone}`}>
      {isWorking(status) ? <LoaderCircle className="library-spin" size={13} aria-hidden="true" /> : (
        <span className="library-status-dot" aria-hidden="true" />
      )}
      {label}
    </span>
  )
}

function LibraryDialog({
  title,
  busy = false,
  close,
  children,
}: {
  title: string
  busy?: boolean
  close: () => void
  children: ReactNode
}) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const titleId = useId()

  useEffect(() => {
    const dialog = dialogRef.current
    dialog?.showModal()
    return () => dialog?.close()
  }, [])

  return (
    <dialog
      ref={dialogRef}
      className="library-dialog"
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault()
        if (!busy) close()
      }}
    >
      <div className="library-dialog-inner">
        <header className="library-dialog-header">
          <h2 id={titleId}>{title}</h2>
          <button className="icon-button" type="button" aria-label="关闭" disabled={busy} onClick={close}>
            <X size={18} aria-hidden="true" />
          </button>
        </header>
        {children}
      </div>
    </dialog>
  )
}

function EmptyState({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children?: ReactNode
}) {
  return (
    <div className="library-empty">
      <span className="library-entity-icon"><FolderOpen size={22} aria-hidden="true" /></span>
      <h3>{title}</h3>
      {description && <p>{description}</p>}
      {children}
    </div>
  )
}

function ErrorNotice({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <div className="library-error" role="alert">
      <CircleAlert size={17} aria-hidden="true" />
      <span>{message}</span>
      {retry && <button type="button" className="button button-ghost" onClick={retry}>重试</button>}
    </div>
  )
}

function CreateForm({
  busy,
  error,
  onClose,
  onCreate,
}: {
  busy: boolean
  error: string
  onClose: () => void
  onCreate: (payload: CreateKnowledgeBaseRequest) => void
}) {
  const [splitMethod, setSplitMethod] = useState<CreateKnowledgeBaseRequest['split_method']>('hierarchical')
  const [validationError, setValidationError] = useState('')

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const name = String(data.get('name') || '').trim()
    const chunkSize = Number(data.get('chunk_size'))
    const chunkOverlap = Number(data.get('chunk_overlap') ?? 50)
    if (!name) {
      setValidationError('请输入知识库名称。')
      return
    }
    if (splitMethod !== 'hierarchical' && chunkOverlap >= chunkSize) {
      setValidationError('分块重叠大小必须小于分块大小。')
      return
    }
    setValidationError('')
    onCreate({
      name,
      description: String(data.get('description') || '').trim(),
      chunk_size: chunkSize,
      chunk_overlap: chunkOverlap,
      split_method: splitMethod,
      retriever_type: data.get('retriever_type') as CreateKnowledgeBaseRequest['retriever_type'],
      record_ids: [],
    })
  }

  return (
    <form className="library-form" onSubmit={submit}>
      <p className="library-muted">先为一组相关资料建库，创建后即可添加已解析的文档。</p>
      <fieldset disabled={busy}>
        <label>知识库名称<input className="field" name="name" placeholder="例如：产品研究资料" required /></label>
        <label>描述（可选）<textarea className="field" name="description" rows={3} placeholder="记录这个库包含哪些资料" /></label>
        <details className="library-advanced">
          <summary>高级检索设置</summary>
          <div className="library-form-grid">
            <label>分块方式
              <select className="field" name="split_method" value={splitMethod} onChange={(event) => setSplitMethod(event.target.value as typeof splitMethod)}>
                <option value="hierarchical">按标题分层</option>
                <option value="recursive">递归分块</option>
                <option value="character">按字符分块</option>
              </select>
            </label>
            <label>检索方式
              <select className="field" name="retriever_type" defaultValue="hybrid">
                <option value="hybrid">混合检索</option>
                <option value="vector">向量检索</option>
                <option value="sparse">关键词检索</option>
              </select>
            </label>
            <label>分块大小<input className="field" name="chunk_size" type="number" min={1} defaultValue={300} required /></label>
            {splitMethod !== 'hierarchical' && (
              <label>分块重叠大小<input className="field" name="chunk_overlap" type="number" min={0} defaultValue={50} required /></label>
            )}
          </div>
        </details>
      </fieldset>
      {(validationError || error) && <ErrorNotice message={validationError || error} />}
      <footer className="library-dialog-actions">
        <button className="button button-secondary" type="button" disabled={busy} onClick={onClose}>取消</button>
        <button className="button button-primary" type="submit" disabled={busy}>
          {busy ? '创建中…' : '创建知识库'}
        </button>
      </footer>
    </form>
  )
}

function deleteDescription(target: DeleteTarget) {
  if (target.kind === 'knowledge') {
    return {
      title: '删除知识库',
      detail: `将删除「${target.knowledgeBase.name}」及其检索索引，源文档仍保存在资料库中。`,
    }
  }
  const title = documentTitle(target.document)
  if (target.kind === 'member') {
    return {
      title: '从知识库移除',
      detail: `将从「${target.knowledgeBase.name}」移除「${title}」及其在该库的索引。源文档和其他知识库中的关联会保留。`,
    }
  }
  return {
    title: '删除源文档',
    detail: `将删除「${title}」、解析内容及它在所有知识库中的索引。此操作无法撤销。`,
  }
}

export default function LibraryPage({ active, onAsk }: LibraryPageProps) {
  const [tab, setTab] = useState<LibraryTab>('knowledge')
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[] | null>(null)
  const [documents, setDocuments] = useState<DocumentRecord[] | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [members, setMembers] = useState<DocumentRecord[] | null>(null)
  const [knowledgeError, setKnowledgeError] = useState('')
  const [documentsError, setDocumentsError] = useState('')
  const [membersError, setMembersError] = useState('')
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const [notice, setNotice] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [addOpen, setAddOpen] = useState(false)
  const [documentDetailId, setDocumentDetailId] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null)
  const [documentFilter, setDocumentFilter] = useState<DocumentFilter>('all')
  const [search, setSearch] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const [uploadResults, setUploadResults] = useState<OperationResult[]>([])
  const [recentRetryUntil, setRecentRetryUntil] = useState(0)
  const [selectedFiles, setSelectedFiles] = useState<string[]>([])
  const [indexResults, setIndexResults] = useState<Record<string, OperationResult>>({})
  const uploadInput = useRef<HTMLInputElement>(null)
  const mutationInProgress = useRef(false)
  const knowledgeLoad = useRef(0)
  const documentLoad = useRef(0)
  const memberLoad = useRef(0)

  const selected = knowledgeBases?.find((item) => item.id === selectedId)
  const documentDetail = documents?.find((item) => item.id === documentDetailId)
  const pendingDocuments = documents?.some((document) => isWorking(documentStatus(document))) ?? false

  const reloadKnowledgeBases = useCallback(async () => {
    const request = ++knowledgeLoad.current
    try {
      const next = await api.listKnowledgeBases()
      if (request !== knowledgeLoad.current) return
      setKnowledgeBases(next)
      setKnowledgeError('')
    } catch (error) {
      if (request === knowledgeLoad.current) setKnowledgeError(formatApiError(error, '无法读取知识库。'))
    }
  }, [])

  const reloadDocuments = useCallback(async () => {
    const request = ++documentLoad.current
    try {
      const next = await api.listDocuments()
      if (request !== documentLoad.current) return
      setDocuments(next)
      setDocumentsError('')
    } catch (error) {
      if (request === documentLoad.current) setDocumentsError(formatApiError(error, '无法读取文档。'))
    }
  }, [])

  const reloadMembers = useCallback(async (knowledgeBaseId: string) => {
    const request = ++memberLoad.current
    try {
      const next = await api.listKnowledgeBaseFiles(knowledgeBaseId)
      if (request !== memberLoad.current) return
      setMembers(next)
      setMembersError('')
      return next
    } catch (error) {
      if (request === memberLoad.current) setMembersError(formatApiError(error, '无法读取知识库中的文档。'))
    }
  }, [])

  useEffect(() => {
    if (!active) return
    void reloadKnowledgeBases()
    void reloadDocuments()
  }, [active, reloadDocuments, reloadKnowledgeBases])

  useEffect(() => {
    if (active && selectedId) void reloadMembers(selectedId)
  }, [active, selectedId, reloadMembers])

  useEffect(() => {
    if (!active || (!pendingDocuments && recentRetryUntil <= Date.now())) return
    let stopped = false
    let timer: number
    const poll = async () => {
      await reloadDocuments()
      if (!stopped && (pendingDocuments || recentRetryUntil > Date.now())) {
        timer = window.setTimeout(() => void poll(), 2500)
      }
    }
    timer = window.setTimeout(() => void poll(), 2500)
    return () => {
      stopped = true
      window.clearTimeout(timer)
    }
  }, [active, pendingDocuments, recentRetryUntil, reloadDocuments])

  function selectKnowledgeBase(id: string | null) {
    if (id === selectedId) return
    memberLoad.current += 1
    setMembers(null)
    setMembersError('')
    setSelectedId(id)
  }

  async function mutate(action: () => Promise<void>) {
    if (mutationInProgress.current) return
    mutationInProgress.current = true
    setBusy(true)
    setActionError('')
    setNotice('')
    try {
      await action()
    } catch (error) {
      setActionError(formatApiError(error, '操作未完成，请重试。'))
    } finally {
      mutationInProgress.current = false
      setBusy(false)
    }
  }

  function changeTab(next: LibraryTab) {
    setTab(next)
    setActionError('')
    setNotice('')
  }

  function createKnowledgeBase(payload: CreateKnowledgeBaseRequest) {
    void mutate(async () => {
      const created = await api.createKnowledgeBase(payload)
      setKnowledgeBases((current) => [...(current ?? []), created])
      setCreateOpen(false)
      selectKnowledgeBase(created.id)
      setNotice('知识库已创建。接下来可以添加文档。')
      await reloadKnowledgeBases()
    })
  }

  function uploadFiles(files: File[]) {
    if (!files.length) return
    void mutate(async () => {
      setUploadResults([])
      for (const [recordIndex, file] of files.entries()) {
        if (!/\.(pdf|docx?|txt|md)$/i.test(file.name)) {
          setUploadResults((current) => [...current, { name: file.name, status: 'failed', detail: '此格式不支持上传。' }])
          continue
        }
        setUploadResults((current) => [...current, { name: file.name, status: 'working', detail: '上传中' }])
        let result: OperationResult
        try {
          const uploaded = await api.uploadDocument(file)
          const status = documentStatus(uploaded)
          setDocuments((current) => [uploaded, ...(current ?? []).filter((item) => item.id !== uploaded.id)])
          if (status === 'failed') setRecentRetryUntil(Date.now() + 10000)
          result = {
            name: file.name,
            status: 'done',
            detail: status === 'ready' ? '解析完成' : status === 'failed' ? '已提交重新解析' : '上传完成',
          }
        } catch (error) {
          result = { name: file.name, status: 'failed', detail: formatApiError(error, '上传失败。') }
        }
        setUploadResults((current) => current.map((entry, index) => index === recordIndex ? result : entry))
      }
      await reloadDocuments()
    })
  }

  function openAddDocuments() {
    setSelectedFiles([])
    setIndexResults({})
    setAddOpen(true)
    void reloadDocuments()
  }

  function addSelectedFiles(knowledgeBase: KnowledgeBase) {
    void mutate(async () => {
      const failed: string[] = []
      for (const id of selectedFiles) {
        const document = documents?.find((item) => item.id === id)
        if (!document) continue
        const name = documentTitle(document)
        setIndexResults((current) => ({ ...current, [id]: { name, status: 'working', detail: '正在建立索引' } }))
        let result: OperationResult
        try {
          await api.addKnowledgeBaseFile(knowledgeBase.id, id)
          result = { name, status: 'done', detail: '已加入，索引就绪' }
        } catch (error) {
          failed.push(id)
          result = { name, status: 'failed', detail: formatApiError(error, '建立索引失败。') }
        }
        setIndexResults((current) => ({ ...current, [id]: result }))
      }
      const [actualMembers] = await Promise.all([reloadMembers(knowledgeBase.id), reloadKnowledgeBases()])
      const indexedAfterError = actualMembers?.filter((item) => failed.includes(item.id)) ?? []
      if (indexedAfterError.length) {
        setIndexResults((current) => {
          const next = { ...current }
          for (const document of indexedAfterError) {
            next[document.id] = { name: documentTitle(document), status: 'done', detail: '已加入，索引就绪' }
          }
          return next
        })
      }
      setSelectedFiles(failed.filter((id) => !indexedAfterError.some((item) => item.id === id)))
    })
  }

  function confirmDelete(target: DeleteTarget) {
    void mutate(async () => {
      try {
        if (target.kind === 'knowledge') {
          await api.deleteKnowledgeBase(target.knowledgeBase.id)
          setKnowledgeBases((current) => current?.filter((item) => item.id !== target.knowledgeBase.id) ?? [])
          selectKnowledgeBase(null)
          setNotice('知识库已删除。')
        } else if (target.kind === 'member') {
          await api.removeKnowledgeBaseFile(target.knowledgeBase.id, target.document.id)
          setMembers((current) => current?.filter((item) => item.id !== target.document.id) ?? [])
          setNotice('文档已从知识库移除。')
        } else {
          await api.deleteDocument(target.document.id)
          setDocuments((current) => current?.filter((item) => item.id !== target.document.id) ?? [])
          setDocumentDetailId(null)
          setNotice('源文档已删除。')
        }
        setDeleteTarget(null)
      } finally {
        await reloadKnowledgeBases()
        if (target.kind === 'member') await reloadMembers(target.knowledgeBase.id)
        if (target.kind === 'document') {
          await reloadDocuments()
          if (selectedId) await reloadMembers(selectedId)
        }
      }
    })
  }

  const matchingDocuments = documents?.filter((document) => {
    const status = documentStatus(document)
    const matchesStatus = documentFilter === 'all' || documentFilter === status ||
      (documentFilter === 'working' && isWorking(status))
    const query = search.trim().toLocaleLowerCase()
    return matchesStatus && (!query || `${documentTitle(document)} ${document.source}`.toLocaleLowerCase().includes(query))
  })
  const memberIds = new Set(members?.map((document) => document.id) ?? selected?.document_ids)
  const addableDocuments = documents?.filter((document) =>
    (documentStatus(document) === 'ready' && !memberIds.has(document.id)) || Boolean(indexResults[document.id]),
  )
  const deleteCopy = deleteTarget ? deleteDescription(deleteTarget) : null

  return (
    <section className="library-page" aria-labelledby="library-title">
      <div className="library-wrap">
        <header className="library-page-header">
          <div>
            <div className="library-overline"><LibraryBig size={15} aria-hidden="true" /> 资料工作区</div>
            <h1 id="library-title">资料库</h1>
            <p>管理文档和知识库，为对话提供检索范围。</p>
          </div>
        </header>
        <div className="library-tabs" role="group" aria-label="资料库视图">
          <button type="button" aria-pressed={tab === 'knowledge'} disabled={busy} onClick={() => changeTab('knowledge')}>
            <BookOpen size={17} aria-hidden="true" /> 知识库
          </button>
          <button type="button" aria-pressed={tab === 'documents'} disabled={busy} onClick={() => changeTab('documents')}>
            <FileText size={17} aria-hidden="true" /> 文档
          </button>
        </div>

        {notice && <div className="library-success" role="status"><Check size={17} aria-hidden="true" />{notice}</div>}
        {actionError && !createOpen && !addOpen && !deleteTarget && <ErrorNotice message={actionError} />}

        {tab === 'knowledge' && !selected && (
          <>
            <div className="library-section-heading">
              <div><h2>知识库</h2><p>每个知识库可包含一组用于问答的文档。</p></div>
              <button className="button button-primary" type="button" disabled={busy} onClick={() => { setActionError(''); setCreateOpen(true) }}>
                <Plus size={16} aria-hidden="true" /> 新建知识库
              </button>
            </div>
            {knowledgeError && <ErrorNotice message={knowledgeError} retry={() => void reloadKnowledgeBases()} />}
            {knowledgeBases === null && !knowledgeError && <p className="library-loading" role="status">正在读取知识库…</p>}
            {knowledgeBases?.length === 0 && !knowledgeError && (
              <EmptyState title="还没有知识库" description="创建一个知识库，把同一主题的资料集中起来。" />
            )}
            {Boolean(knowledgeBases?.length) && (
              <ul className="library-kb-grid">
                {knowledgeBases?.map((knowledgeBase) => (
                  <li key={knowledgeBase.id}>
                    <button className="library-kb-card" type="button" disabled={busy} onClick={() => selectKnowledgeBase(knowledgeBase.id)}>
                      <span className="library-card-top">
                        <span className="library-entity-icon"><BookOpen size={21} aria-hidden="true" /></span>
                        <ArrowRight className="library-card-arrow" size={17} aria-hidden="true" />
                      </span>
                      <strong>{knowledgeBase.name}</strong>
                      {knowledgeBase.description && <span className="library-card-description">{knowledgeBase.description}</span>}
                      <span className="library-card-meta">
                        <span><FileText size={14} aria-hidden="true" />{knowledgeBase.document_ids.length} 份已索引文档</span>
                        {formatDate(knowledgeBase.created_at) && <span>{formatDate(knowledgeBase.created_at)}</span>}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}

        {tab === 'knowledge' && selected && (
          <>
            <button className="button button-ghost library-back" type="button" disabled={busy} onClick={() => { setNotice(''); selectKnowledgeBase(null) }}>
              <ArrowLeft size={16} aria-hidden="true" /> 返回知识库
            </button>
            <div className="library-detail-summary">
              <span className="library-entity-icon"><BookOpen size={23} aria-hidden="true" /></span>
              <div><h2>{selected.name}</h2><p>{selected.description || '暂无描述'}</p></div>
              <button className="button button-primary" type="button" disabled={busy || !memberIds.size} onClick={() => onAsk(selected)}>
                用此知识库提问 <ArrowRight size={16} aria-hidden="true" />
              </button>
            </div>
            <div className="library-section-heading">
              <div><h3>已索引文档</h3><p>这些文档可用于此知识库的问答。</p></div>
              <button className="button button-secondary" type="button" disabled={busy} onClick={openAddDocuments}>
                <Plus size={16} aria-hidden="true" /> 添加文档
              </button>
            </div>
            {membersError && <ErrorNotice message={membersError} retry={() => void reloadMembers(selected.id)} />}
            {members === null && !membersError && <p className="library-loading" role="status">正在读取库内文档…</p>}
            {members?.length === 0 && !membersError && (
              <EmptyState title="还没有已索引的文档" description="添加已解析的文档后，就可以在对话中使用此知识库。" />
            )}
            {Boolean(members?.length) && (
              <ul className="library-record-list">
                {members?.map((document) => (
                  <li className="library-record" key={document.id}>
                    <span className="library-entity-icon"><FileText size={18} aria-hidden="true" /></span>
                    <div className="library-record-copy"><strong>{documentTitle(document)}</strong><small>{document.source}</small></div>
                    <span className="status-badge library-badge library-badge-success"><Check size={14} aria-hidden="true" /> 索引就绪</span>
                    <button className="button button-ghost" type="button" disabled={busy} onClick={() => setDeleteTarget({ kind: 'member', knowledgeBase: selected, document })}>
                      移除
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <button className="button button-ghost library-delete-link" type="button" disabled={busy} onClick={() => setDeleteTarget({ kind: 'knowledge', knowledgeBase: selected })}>
              <Trash2 size={16} aria-hidden="true" /> 删除知识库
            </button>
          </>
        )}

        {tab === 'documents' && (
          <>
            <div
              className={`library-upload${dragOver ? ' is-drag-over' : ''}`}
              onDragOver={(event) => { event.preventDefault(); setDragOver(!busy) }}
              onDragLeave={(event) => {
                if (!(event.relatedTarget instanceof Node) || !event.currentTarget.contains(event.relatedTarget)) setDragOver(false)
              }}
              onDrop={(event) => { event.preventDefault(); setDragOver(false); uploadFiles(Array.from(event.dataTransfer.files)) }}
            >
              <span className="library-entity-icon"><Upload size={22} aria-hidden="true" /></span>
              <div><h2>上传文档</h2><p>将文件拖到这里，支持 PDF、Word、TXT 和 Markdown。</p></div>
              <input
                ref={uploadInput}
                type="file"
                multiple
                accept={acceptedFiles}
                hidden
                onChange={(event) => {
                  uploadFiles(Array.from(event.currentTarget.files ?? []))
                  event.currentTarget.value = ''
                }}
              />
              <button className="button button-primary" type="button" disabled={busy} onClick={() => uploadInput.current?.click()}>
                <Plus size={17} aria-hidden="true" /> 选择文件
              </button>
            </div>
            {uploadResults.length > 0 && (
              <ul className="library-operation-list" aria-label="本次上传结果" aria-live="polite">
                {uploadResults.map((result, index) => (
                  <li key={`${result.name}-${index}`}>
                    <strong>{result.name}</strong>
                    <span className={`library-result-${result.status}`}>{result.detail}</span>
                  </li>
                ))}
              </ul>
            )}
            <div className="library-section-heading">
              <div><h2>文档列表</h2><p>解析完成后可将文档添加到知识库。</p></div>
              <div className="library-section-actions">
                {selected && <button className="button button-secondary" type="button" disabled={busy} onClick={() => changeTab('knowledge')}>返回所选知识库</button>}
                <button className="button button-ghost" type="button" disabled={busy} onClick={() => void reloadDocuments()}>
                  <RefreshCw size={16} aria-hidden="true" /> 刷新
                </button>
              </div>
            </div>
            {Boolean(documents?.length) && (
              <div className="library-filter">
                <label className="library-search"><Search size={16} aria-hidden="true" />
                  <input className="field" type="search" aria-label="搜索文档" placeholder="搜索文档" value={search} onChange={(event) => setSearch(event.target.value)} />
                </label>
                <select className="field" aria-label="按解析状态筛选" value={documentFilter} onChange={(event) => setDocumentFilter(event.target.value as DocumentFilter)}>
                  <option value="all">全部状态</option>
                  <option value="ready">解析完成</option>
                  <option value="working">处理中</option>
                  <option value="failed">解析失败</option>
                </select>
              </div>
            )}
            {documentsError && <ErrorNotice message={documentsError} retry={() => void reloadDocuments()} />}
            {documents === null && !documentsError && <p className="library-loading" role="status">正在读取文档…</p>}
            {documents?.length === 0 && !documentsError && (
              <EmptyState title="还没有文档" description="上传第一份文档，解析完成后即可加入知识库。" />
            )}
            {Boolean(documents?.length) && matchingDocuments?.length === 0 && (
              <EmptyState title="没有符合条件的文档" description="试试其他关键词或状态。" />
            )}
            {Boolean(matchingDocuments?.length) && (
              <ul className="library-record-list">
                {matchingDocuments?.map((document) => (
                  <li className="library-record" key={document.id}>
                    <span className="library-entity-icon"><FileText size={18} aria-hidden="true" /></span>
                    <div className="library-record-copy">
                      <button type="button" className="library-record-title" onClick={() => setDocumentDetailId(document.id)}>{documentTitle(document)}</button>
                      <small>{document.source}{formatDate(document.created_at) && ` · ${formatDate(document.created_at)}`}</small>
                    </div>
                    <DocumentBadge document={document} />
                    <button
                      className="icon-button library-delete-link"
                      type="button"
                      aria-label={`删除源文档 ${documentTitle(document)}`}
                      disabled={busy || documentStatus(document) === 'processing'}
                      onClick={() => setDeleteTarget({ kind: 'document', document })}
                    >
                      <Trash2 size={17} aria-hidden="true" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}

        {active && createOpen && (
          <LibraryDialog title="新建知识库" busy={busy} close={() => setCreateOpen(false)}>
            <CreateForm busy={busy} error={actionError} onClose={() => setCreateOpen(false)} onCreate={createKnowledgeBase} />
          </LibraryDialog>
        )}

        {active && addOpen && selected && (
          <LibraryDialog title="添加文档" busy={busy} close={() => setAddOpen(false)}>
            <p className="library-muted">选择已解析的文档，系统会为「{selected.name}」逐一建立索引。</p>
            {documentsError && <ErrorNotice message={documentsError} retry={() => void reloadDocuments()} />}
            {documents === null && !documentsError && <p className="library-loading" role="status">正在读取文档…</p>}
            {addableDocuments?.length === 0 && !documentsError && (
              <EmptyState title="没有可添加的文档" description="先上传文档并等待解析完成。">
                <button className="button button-secondary" type="button" onClick={() => { setAddOpen(false); changeTab('documents') }}>前往文档</button>
              </EmptyState>
            )}
            {Boolean(addableDocuments?.length) && (
              <fieldset className="library-add-files" disabled={busy}>
                <legend className="library-muted">可添加的文档</legend>
                {addableDocuments?.map((document) => {
                  const result = indexResults[document.id]
                  return (
                    <label key={document.id}>
                      <input
                        type="checkbox"
                        checked={selectedFiles.includes(document.id) && result?.status !== 'done'}
                        disabled={result?.status === 'done' || memberIds.has(document.id)}
                        onChange={(event) => {
                          const checked = event.currentTarget.checked
                          setSelectedFiles((current) => checked ? [...current, document.id] : current.filter((id) => id !== document.id))
                        }}
                      />
                      <span>{documentTitle(document)}</span>
                      {result && <small className={`library-result-${result.status}`} role="status">{result.detail}</small>}
                    </label>
                  )
                })}
              </fieldset>
            )}
            {actionError && <ErrorNotice message={actionError} />}
            <footer className="library-dialog-actions">
              <button className="button button-secondary" type="button" disabled={busy} onClick={() => setAddOpen(false)}>关闭</button>
              <button className="button button-primary" type="button" disabled={busy || !selectedFiles.length} onClick={() => addSelectedFiles(selected)}>
                {busy ? '正在建立索引…' : `添加${selectedFiles.length ? ` ${selectedFiles.length} 份文档` : '文档'}`}
              </button>
            </footer>
          </LibraryDialog>
        )}

        {active && documentDetail && (
          <LibraryDialog title={documentTitle(documentDetail)} close={() => setDocumentDetailId(null)}>
            <div className="library-document-details">
              <div className="library-document-metadata"><span>{documentDetail.source}</span><DocumentBadge document={documentDetail} /></div>
              {documentStatus(documentDetail) === 'failed' && (
                <>
                  <ErrorNotice message="文档解析失败。你可以重新上传同一个文件来重试。" />
                  <button className="button button-secondary" type="button" disabled={busy} onClick={() => { setDocumentDetailId(null); uploadInput.current?.click() }}>
                    <Upload size={16} aria-hidden="true" /> 重新上传
                  </button>
                </>
              )}
              {documentDetail.metadata?.abstract && <div><h3>摘要</h3><p>{documentDetail.metadata.abstract}</p></div>}
              {Boolean(documentDetail.metadata?.keywords?.length) && (
                <div><h3>关键词</h3><ul className="library-keywords">{documentDetail.metadata?.keywords?.map((keyword, index) => <li key={`${keyword}-${index}`}>{keyword}</li>)}</ul></div>
              )}
              {Boolean(documentDetail.metadata?.directory?.length) && (
                <div><h3>目录</h3><ul className="library-document-directory">{documentDetail.metadata?.directory?.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul></div>
              )}
            </div>
          </LibraryDialog>
        )}

        {active && deleteTarget && deleteCopy && (
          <LibraryDialog title={deleteCopy.title} busy={busy} close={() => { setActionError(''); setDeleteTarget(null) }}>
            <p className="library-muted">{deleteCopy.detail}</p>
            {actionError && <ErrorNotice message={actionError} />}
            <footer className="library-dialog-actions">
              <button className="button button-secondary" type="button" disabled={busy} onClick={() => { setActionError(''); setDeleteTarget(null) }}>取消</button>
              <button className="button button-danger" type="button" disabled={busy} onClick={() => confirmDelete(deleteTarget)}>
                {busy ? '处理中…' : deleteCopy.title}
              </button>
            </footer>
          </LibraryDialog>
        )}
      </div>
    </section>
  )
}
