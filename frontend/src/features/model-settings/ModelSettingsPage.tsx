import { Check, CircleAlert, KeyRound, Settings2 } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { api, formatApiError } from '../../api'
import type {
  CredentialSource,
  ModelAssignments,
  ModelProvider,
  ModelSelection,
  ModelSettings,
  UpdateModelSettingsRequest,
} from '../../api/types'
import './model-settings.css'

const providers = [
  { id: 'deepseek', name: 'DeepSeek', example: 'deepseek-chat', environment: 'DEEPSEEK_API_KEY' },
  { id: 'bailian', name: '阿里云百炼', example: 'qwen-plus', environment: 'BAILIAN_API_KEY' },
] as const

const roles = [
  { id: 'dialog', name: '对话', description: '生成对话回答和会话标题' },
  { id: 'memory', name: '记忆', description: '总结和合并会话记忆' },
  { id: 'rag', name: '知识检索与文档处理', description: '改写问题、评估检索结果和提取文档信息' },
] as const

const credentialLabels: Record<CredentialSource, string> = {
  stored: '已保存密钥',
  environment: '使用环境变量',
  missing: '未配置密钥',
}

function assignments({ dialog, memory, rag }: ModelSettings): ModelAssignments {
  return { dialog, memory, rag }
}

function ModelSettingsForm({ initial }: { initial: ModelSettings }) {
  const [saved, setSaved] = useState(initial)
  const [models, setModels] = useState(() => assignments(initial))
  const [keyChanges, setKeyChanges] = useState<NonNullable<UpdateModelSettingsRequest['api_keys']>>({})
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [savedNotice, setSavedNotice] = useState(false)

  function updateModel(role: keyof ModelAssignments, selection: ModelSelection) {
    setModels((current) => ({ ...current, [role]: selection }))
    setError('')
    setSavedNotice(false)
  }

  function updateKey(provider: ModelProvider, value: string | null) {
    setKeyChanges((current) => ({ ...current, [provider]: value }))
    setError('')
    setSavedNotice(false)
  }

  const changed = roles.some(({ id }) => (
    models[id].provider !== saved[id].provider || models[id].model.trim() !== saved[id].model
  )) || providers.some(({ id }) => keyChanges[id] === null || Boolean(keyChanges[id]))

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (saving || !changed) return

    const payload: UpdateModelSettingsRequest = { ...models }
    for (const { id, name } of roles) {
      const model = models[id].model.trim()
      if (!model) {
        setError(`请输入「${name}」的模型 ID。`)
        return
      }
      payload[id] = { ...models[id], model }
    }

    const keys: NonNullable<UpdateModelSettingsRequest['api_keys']> = {}
    for (const { id, name } of providers) {
      const value = keyChanges[id]
      if (value === undefined || value === '') continue
      const key = value === null ? null : value.trim()
      if (key !== null && !/^[\x21-\x7e]+$/.test(key)) {
        setError(`${name} 的 API 密钥只能包含英文半角字母、数字或标点。`)
        return
      }
      keys[id] = key
    }
    if (Object.keys(keys).length) payload.api_keys = keys

    setError('')
    setSaving(true)
    try {
      const settings = await api.updateModelSettings(payload)
      setSaved(settings)
      setModels(assignments(settings))
      setKeyChanges({})
      setSavedNotice(true)
    } catch (failure) {
      setError(formatApiError(failure, '保存模型配置失败，请稍后重试。'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="model-settings-form" onSubmit={save}>
      <fieldset disabled={saving}>
        <section className="model-settings-card" aria-labelledby="model-assignment-heading">
          <div className="model-settings-card-heading">
            <Settings2 size={20} aria-hidden="true" />
            <div>
              <h2 id="model-assignment-heading">模型分配</h2>
              <p>选择服务商，并填写该服务商提供的模型 ID。</p>
            </div>
          </div>
          {roles.map(({ id, name, description }) => {
            const selection = models[id]
            const example = providers.find((provider) => provider.id === selection.provider)?.example
            return (
              <div key={id} className="model-settings-row" role="group" aria-labelledby={`model-role-${id}`}>
                <div>
                  <h3 id={`model-role-${id}`}>{name}</h3>
                  <p>{description}</p>
                </div>
                <label>服务商
                  <select className="field" value={selection.provider} onChange={(event) => {
                    const provider = event.target.value as ModelProvider
                    updateModel(id, { provider, model: provider === saved[id].provider ? saved[id].model : '' })
                  }}>
                    {providers.map((provider) => <option key={provider.id} value={provider.id}>{provider.name}</option>)}
                  </select>
                </label>
                <label>模型 ID
                  <input className="field" value={selection.model} onChange={(event) => updateModel(id, { ...selection, model: event.target.value })} placeholder={example} maxLength={200} autoComplete="off" spellCheck={false} required />
                </label>
              </div>
            )
          })}
        </section>

        <section className="model-settings-card" aria-labelledby="model-credential-heading">
          <div className="model-settings-card-heading">
            <KeyRound size={20} aria-hidden="true" />
            <div>
              <h2 id="model-credential-heading">服务商密钥</h2>
              <p>文本模型优先使用已保存的密钥，移除后改用对应环境变量。文档向量化使用 <code>BAILIAN_API_KEY</code> 环境变量。</p>
            </div>
          </div>
          {providers.map(({ id, name, environment }) => {
            const source = saved.credentials[id]
            const removing = keyChanges[id] === null
            return (
              <div key={id} className="model-settings-row model-settings-key-row" role="group" aria-labelledby={`model-key-${id}`}>
                <div>
                  <div className="model-settings-key-heading">
                    <h3 id={`model-key-${id}`}>{name}</h3>
                    <span className={`status-badge model-settings-key-${source}`}>{credentialLabels[source]}</span>
                  </div>
                  <p><code>{environment}</code></p>
                </div>
                <label>API 密钥
                  <input className="field" type="password" autoComplete="new-password" spellCheck={false} maxLength={1024} disabled={removing} value={keyChanges[id] ?? ''} placeholder={removing ? '保存后移除' : '留空保留当前设置'} onChange={(event) => updateKey(id, event.target.value)} />
                </label>
                {source === 'stored' && (
                  <button type="button" className="button button-secondary" onClick={() => updateKey(id, removing ? '' : null)}>
                    {removing ? '取消移除' : '移除密钥'}
                  </button>
                )}
              </div>
            )
          })}
        </section>
      </fieldset>

      <footer className="model-settings-actions">
        {error && <p className="model-settings-error" role="alert"><CircleAlert size={17} aria-hidden="true" />{error}</p>}
        {savedNotice && <p className="model-settings-success" role="status"><Check size={17} aria-hidden="true" />配置已保存。</p>}
        <button type="submit" className="button button-primary" disabled={saving || !changed}>{saving ? '保存中…' : '保存配置'}</button>
      </footer>
    </form>
  )
}

export default function ModelSettingsPage() {
  const [settings, setSettings] = useState<ModelSettings | null>(null)
  const [loadError, setLoadError] = useState('')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    api.getModelSettings(controller.signal).then((response) => {
      if (!controller.signal.aborted) setSettings(response)
    }).catch((error) => {
      if (!controller.signal.aborted) setLoadError(formatApiError(error, '无法加载模型配置，请稍后重试。'))
    })
    return () => controller.abort()
  }, [attempt])

  return (
    <div className="model-settings-page">
      <header className="model-settings-header">
        <h1>模型配置</h1>
        <p>为对话、记忆和知识检索指定模型。保存后，后续模型调用会使用新配置。</p>
      </header>
      {loadError && (
        <div className="model-settings-load-error" role="alert">
          <p className="model-settings-error"><CircleAlert size={17} aria-hidden="true" />{loadError}</p>
          <button type="button" className="button button-secondary" onClick={() => {
            setLoadError('')
            setAttempt((current) => current + 1)
          }}>重试</button>
        </div>
      )}
      {!settings && !loadError && <p className="app-loading" role="status">正在加载模型配置…</p>}
      {settings && <ModelSettingsForm initial={settings} />}
    </div>
  )
}
