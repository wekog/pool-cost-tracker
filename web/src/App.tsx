import { useEffect, useMemo, useState } from 'react'
import { format, parseISO } from 'date-fns'
import { de } from 'date-fns/locale'
import { api, extractApiError } from './api'
import InvoiceCard from './components/InvoiceCard'
import ManualCostCard from './components/ManualCostCard'
import type {
  ConfigResponse,
  HealthResponse,
  Invoice,
  InvoiceReviewResponse,
  InvoiceUpdatePayload,
  ManualArchiveView,
  ManualCost,
  ManualCostPayload,
  PageKey,
  RangeKey,
  ReviewSort,
  SummaryResponse,
  SyncResponse,
  SyncRunResponse,
} from './types'

type NoticeType = 'success' | 'error' | 'info'

interface Notice {
  type: NoticeType
  message: string
}

interface InvoiceFilters {
  needsReview: 'all' | 'only'
  search: string
  sort: 'date_desc' | 'date_asc' | 'amount_desc' | 'amount_asc'
}

interface ActiveRange {
  range: RangeKey
  from: string
  to: string
}

function formatCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '–'
  }

  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return '–'
  }

  try {
    return format(parseISO(value), 'dd.MM.yyyy HH:mm', { locale: de })
  } catch {
    return value
  }
}

function formatDateOnly(value: string | null | undefined): string {
  if (!value) {
    return '–'
  }

  try {
    return format(parseISO(value), 'dd.MM.yyyy', { locale: de })
  } catch {
    return value
  }
}

function formatDuration(durationMs: number): string {
  if (durationMs < 1000) {
    return `${durationMs}ms`
  }

  return `${(durationMs / 1000).toFixed(1)}s`
}

function formatLastSync(value: string | null | undefined): string {
  if (!value) {
    return 'Noch kein Sync'
  }

  return formatDateTime(value)
}

function buildRangeParams(activeRange: ActiveRange): Record<string, string> {
  const params: Record<string, string> = { range: activeRange.range }
  if (activeRange.range === 'custom') {
    if (activeRange.from) {
      params.from = activeRange.from
    }
    if (activeRange.to) {
      params.to = activeRange.to
    }
  }
  return params
}

function buildInvoiceFilterParams(filters: InvoiceFilters): Record<string, string> {
  const params: Record<string, string> = { sort: filters.sort }
  if (filters.needsReview === 'only') {
    params.needs_review = 'true'
  }
  if (filters.search.trim()) {
    params.search = filters.search.trim()
  }
  return params
}

function buildExportHref(params: Record<string, string>): string {
  const searchParams = new URLSearchParams(params)
  return `/api/export.csv?${searchParams.toString()}`
}

function buildPaperlessDocumentHref(baseUrl: string | null | undefined, docId: number): string {
  const normalizedBaseUrl = baseUrl?.trim()
  if (!normalizedBaseUrl) {
    return ''
  }
  return `${normalizedBaseUrl.replace(/\/$/, '')}/documents/${docId}/details/`
}

function App() {
  const [activePage, setActivePage] = useState<PageKey>('dashboard')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [notice, setNotice] = useState<Notice | null>(null)
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [config, setConfig] = useState<ConfigResponse | null>(null)
  const [summary, setSummary] = useState<SummaryResponse | null>(null)
  const [lastSync, setLastSync] = useState<SyncRunResponse | null>(null)
  const [syncRuns, setSyncRuns] = useState<SyncRunResponse[]>([])
  const [syncing, setSyncing] = useState(false)
  const [rangeDraft, setRangeDraft] = useState<ActiveRange>({
    range: 'all',
    from: '',
    to: '',
  })
  const [activeRange, setActiveRange] = useState<ActiveRange>({
    range: 'all',
    from: '',
    to: '',
  })

  const [invoiceDraft, setInvoiceDraft] = useState<InvoiceFilters>({
    needsReview: 'all',
    search: '',
    sort: 'date_desc',
  })
  const [invoiceFilters, setInvoiceFilters] = useState<InvoiceFilters>({
    needsReview: 'all',
    search: '',
    sort: 'date_desc',
  })
  const [invoiceLoading, setInvoiceLoading] = useState(false)
  const [invoices, setInvoices] = useState<Invoice[]>([])
  const [reviewLoading, setReviewLoading] = useState(false)
  const [reviewSaving, setReviewSaving] = useState(false)
  const [reviewItems, setReviewItems] = useState<Invoice[]>([])
  const [reviewSessionTotal, setReviewSessionTotal] = useState(0)
  const [reviewCursor, setReviewCursor] = useState(0)
  const [reviewSort, setReviewSort] = useState<ReviewSort>('amount_desc')
  const [invoiceEditor, setInvoiceEditor] = useState<Invoice | null>(null)
  const [invoiceSaving, setInvoiceSaving] = useState(false)

  const [manualLoading, setManualLoading] = useState(false)
  const [manualCosts, setManualCosts] = useState<ManualCost[]>([])
  const [manualArchiveView, setManualArchiveView] = useState<ManualArchiveView>('active')
  const [manualSaving, setManualSaving] = useState(false)
  const [manualDeleting, setManualDeleting] = useState<number | null>(null)
  const [manualEditor, setManualEditor] = useState<ManualCost | null>(null)
  const [manualForm, setManualForm] = useState<ManualCostPayload>({
    date: format(new Date(), 'yyyy-MM-dd'),
    vendor: '',
    amount: 0,
    currency: 'EUR',
    category: '',
    note: '',
  })

  const [invoiceForm, setInvoiceForm] = useState<{
    vendor: string
    amount: string
    needsReview: boolean
  }>({
    vendor: '',
    amount: '',
    needsReview: false,
  })
  const [reviewForm, setReviewForm] = useState<{
    vendor: string
    amount: string
  }>({
    vendor: '',
    amount: '',
  })

  useEffect(() => {
    void initialize()
  }, [])

  useEffect(() => {
    if (!invoiceEditor) {
      return
    }
    setInvoiceForm({
      vendor: invoiceEditor.vendor ?? '',
      amount: invoiceEditor.amount !== null && invoiceEditor.amount !== undefined ? String(invoiceEditor.amount) : '',
      needsReview: invoiceEditor.needs_review,
    })
  }, [invoiceEditor])

  useEffect(() => {
    if (!manualEditor) {
      return
    }
    setManualForm({
      date: manualEditor.date,
      vendor: manualEditor.vendor,
      amount: manualEditor.amount,
      currency: manualEditor.currency,
      category: manualEditor.category ?? '',
      note: manualEditor.note ?? '',
    })
  }, [manualEditor])

  const currentReview = reviewItems[reviewCursor] ?? null

  useEffect(() => {
    if (!currentReview) {
      setReviewForm({ vendor: '', amount: '' })
      return
    }
    setReviewForm({
      vendor: currentReview.vendor ?? '',
      amount:
        currentReview.amount !== null && currentReview.amount !== undefined
          ? String(currentReview.amount)
          : '',
    })
  }, [currentReview])

  useEffect(() => {
    if (activePage === 'inbox') {
      void loadReviewInbox(activeRange, reviewSort)
    }
    if (activePage === 'invoices') {
      void loadInvoices(invoiceFilters, activeRange)
    }
    if (activePage === 'manual') {
      void loadManualCosts(activeRange, manualArchiveView)
    }
  }, [activePage, activeRange, reviewSort, invoiceFilters, manualArchiveView])

  useEffect(() => {
    void loadSummary(activeRange)
  }, [activeRange])

  useEffect(() => {
    document.body.style.overflow = sidebarOpen ? 'hidden' : ''
    return () => {
      document.body.style.overflow = ''
    }
  }, [sidebarOpen])

  useEffect(() => {
    function handleInboxKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        if (invoiceEditor) {
          event.preventDefault()
          setInvoiceEditor(null)
          return
        }
        if (manualEditor) {
          event.preventDefault()
          setManualEditor(null)
          return
        }
        if (sidebarOpen) {
          event.preventDefault()
          setSidebarOpen(false)
        }
        return
      }

      if (activePage !== 'inbox' || !currentReview) {
        return
      }

      const activeTagName = document.activeElement?.tagName ?? ''
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(activeTagName)) {
        return
      }

      if (event.key === 'Enter') {
        event.preventDefault()
        void handleReviewSaveAndNext()
        return
      }

      if (event.key === 'n' || event.key === 'N') {
        event.preventDefault()
        handleReviewNext()
        return
      }

      if (event.key === 'p' || event.key === 'P') {
        event.preventDefault()
        handleReviewPrev()
      }
    }

    window.addEventListener('keydown', handleInboxKeyDown)
    return () => {
      window.removeEventListener('keydown', handleInboxKeyDown)
    }
  }, [activePage, currentReview, invoiceEditor, manualEditor, sidebarOpen, reviewItems.length, reviewCursor, reviewForm])

  async function initialize() {
    try {
      const [healthRes, configRes, lastSyncRes, syncRunsRes] = await Promise.all([
        api.get<HealthResponse>('/health'),
        api.get<ConfigResponse>('/config'),
        api.get<SyncRunResponse | null>('/sync/last'),
        api.get<SyncRunResponse[]>('/sync/runs', { params: { limit: '10' } }),
      ])
      setHealth(healthRes.data)
      setConfig(configRes.data)
      setLastSync(lastSyncRes.data)
      setSyncRuns(syncRunsRes.data)
      setManualForm((current) => ({
        ...current,
        currency: configRes.data.default_currency?.trim() || 'EUR',
      }))
    } catch (error) {
      showNotice('error', extractApiError(error))
    }
  }

  async function loadSummary(range: ActiveRange) {
    try {
      const response = await api.get<SummaryResponse>('/summary', { params: buildRangeParams(range) })
      setSummary(response.data)
    } catch (error) {
      showNotice('error', extractApiError(error))
    }
  }

  async function loadInvoices(filters: InvoiceFilters, range: ActiveRange) {
    setInvoiceLoading(true)
    try {
      const params: Record<string, string> = {
        sort: filters.sort,
        ...buildRangeParams(range),
      }
      if (filters.needsReview === 'only') {
        params.needs_review = 'true'
      }
      if (filters.search.trim()) {
        params.search = filters.search.trim()
      }
      const response = await api.get<Invoice[]>('/invoices', { params })
      setInvoices(response.data)
    } catch (error) {
      showNotice('error', extractApiError(error))
    } finally {
      setInvoiceLoading(false)
    }
  }

  async function loadReviewInbox(range: ActiveRange, sort: ReviewSort) {
    setReviewLoading(true)
    try {
      const response = await api.get<InvoiceReviewResponse>('/invoices/review', {
        params: {
          ...buildRangeParams(range),
          sort,
        },
      })
      setReviewItems(response.data.items)
      setReviewSessionTotal(response.data.total)
      setReviewCursor(0)
    } catch (error) {
      showNotice('error', extractApiError(error))
    } finally {
      setReviewLoading(false)
    }
  }

  async function loadManualCosts(range: ActiveRange, archiveView: ManualArchiveView) {
    setManualLoading(true)
    try {
      const response = await api.get<ManualCost[]>('/manual-costs', {
        params: {
          ...buildRangeParams(range),
          archived: archiveView,
        },
      })
      setManualCosts(response.data)
    } catch (error) {
      showNotice('error', extractApiError(error))
    } finally {
      setManualLoading(false)
    }
  }

  async function loadSyncRuns() {
    try {
      const response = await api.get<SyncRunResponse[]>('/sync/runs', { params: { limit: '10' } })
      setSyncRuns(response.data)
    } catch (error) {
      showNotice('error', extractApiError(error))
    }
  }

  async function handleSync() {
    setSyncing(true)
    try {
      const response = await api.post<SyncResponse>('/sync')
      setLastSync(response.data)
      const errorSuffix =
        response.data.errors.count > 0
          ? ` Fehler: ${response.data.errors.count}${response.data.errors.first_error ? ` (${response.data.errors.first_error})` : ''}.`
          : ''
      showNotice(
        'success',
        `Sync abgeschlossen: ${response.data.checked_docs} geprüft, ${response.data.new_invoices} neu, ${response.data.updated_invoices} aktualisiert (${formatDuration(response.data.duration_ms)}).${errorSuffix}`,
      )
      const [healthRes] = await Promise.all([
        api.get<HealthResponse>('/health'),
        loadSummary(activeRange),
        activePage === 'invoices' ? loadInvoices(invoiceFilters, activeRange) : Promise.resolve(),
        activePage === 'manual' ? loadManualCosts(activeRange, manualArchiveView) : Promise.resolve(),
        loadSyncRuns(),
      ])
      setHealth(healthRes.data)
    } catch (error) {
      showNotice('error', extractApiError(error))
    } finally {
      setSyncing(false)
    }
  }

  async function handleInvoiceSave() {
    if (!invoiceEditor) {
      return
    }

    const payload: InvoiceUpdatePayload = {
      vendor: invoiceForm.vendor.trim() || null,
      amount: invoiceForm.amount.trim() ? Number(invoiceForm.amount) : null,
      needs_review: invoiceForm.needsReview,
    }

    setInvoiceSaving(true)
    try {
      const response = await api.put<Invoice>(`/invoices/${invoiceEditor.id}`, payload)
      setInvoiceEditor(response.data)
      showNotice('success', 'Rechnung aktualisiert.')
      await Promise.all([loadInvoices(invoiceFilters, activeRange), loadSummary(activeRange)])
    } catch (error) {
      showNotice('error', extractApiError(error))
    } finally {
      setInvoiceSaving(false)
    }
  }

  async function handleInvoiceReset(field: 'vendor' | 'amount') {
    if (!invoiceEditor) {
      return
    }

    setInvoiceSaving(true)
    try {
      const payload: InvoiceUpdatePayload =
        field === 'vendor'
          ? { reset_vendor: true }
          : { reset_amount: true }
      const response = await api.put<Invoice>(`/invoices/${invoiceEditor.id}`, payload)
      setInvoiceEditor(response.data)
      showNotice('success', `${field === 'vendor' ? 'Unternehmen' : 'Betrag'} wieder auf automatisch gesetzt.`)
      await Promise.all([loadInvoices(invoiceFilters, activeRange), loadSummary(activeRange)])
    } catch (error) {
      showNotice('error', extractApiError(error))
    } finally {
      setInvoiceSaving(false)
    }
  }

  function removeReviewItemFromState(invoiceId: number, resolvedInvoice: Invoice) {
    setReviewItems((current) => {
      const removedIndex = current.findIndex((item) => item.id === invoiceId)
      if (removedIndex === -1) {
        return current
      }
      const nextItems = current.filter((item) => item.id !== invoiceId)
      setReviewCursor((currentCursor) => {
        if (nextItems.length === 0) {
          return 0
        }
        if (currentCursor > removedIndex) {
          return currentCursor - 1
        }
        return Math.min(currentCursor, nextItems.length - 1)
      })
      return nextItems
    })
    setInvoices((current) => current.map((item) => (item.id === resolvedInvoice.id ? resolvedInvoice : item)))
    setSummary((current) =>
      current
        ? {
            ...current,
            needs_review_count: Math.max(0, current.needs_review_count - 1),
          }
        : current,
    )
  }

  async function handleReviewSaveAndNext() {
    if (!currentReview) {
      return
    }

    const vendorValue = reviewForm.vendor.trim()
    const amountValue = reviewForm.amount.trim()
    if (amountValue) {
      const parsedAmount = Number(amountValue)
      if (Number.isNaN(parsedAmount) || parsedAmount < 0) {
        showNotice('error', 'Betrag muss eine gültige Zahl sein.')
        return
      }
    }

    const payload: InvoiceUpdatePayload = {
      needs_review: false,
      vendor: vendorValue || null,
      amount: amountValue ? Number(amountValue) : null,
    }

    setReviewSaving(true)
    try {
      const response = await api.put<Invoice>(`/invoices/${currentReview.id}`, payload)
      removeReviewItemFromState(currentReview.id, response.data)
      showNotice('success', 'Rechnung gespeichert und aus der Inbox entfernt.')
    } catch (error) {
      showNotice('error', extractApiError(error))
    } finally {
      setReviewSaving(false)
    }
  }

  async function handleReviewResolve() {
    if (!currentReview) {
      return
    }

    setReviewSaving(true)
    try {
      const response = await api.patch<Invoice>(`/invoices/${currentReview.id}/resolve`)
      removeReviewItemFromState(currentReview.id, response.data)
      showNotice('success', 'Rechnung als geprüft markiert.')
    } catch (error) {
      showNotice('error', extractApiError(error))
    } finally {
      setReviewSaving(false)
    }
  }

  function handleReviewNext() {
    setReviewCursor((current) => Math.min(current + 1, Math.max(reviewItems.length - 1, 0)))
  }

  function handleReviewPrev() {
    setReviewCursor((current) => Math.max(current - 1, 0))
  }

  async function handleManualCreate() {
    if (!manualForm.vendor.trim()) {
      showNotice('error', 'Unternehmen ist ein Pflichtfeld.')
      return
    }
    const amount = Number(manualForm.amount)
    if (Number.isNaN(amount) || amount <= 0) {
      showNotice('error', 'Betrag muss größer als 0 sein.')
      return
    }

    setManualSaving(true)
    try {
      await api.post('/manual-costs', {
        date: manualForm.date || null,
        vendor: manualForm.vendor.trim(),
        amount,
        currency: manualForm.currency || defaultCurrency,
        category: manualForm.category?.trim() || null,
        note: manualForm.note?.trim() || null,
      } satisfies ManualCostPayload)
      showNotice('success', 'Manuelle Kostenposition angelegt.')
      setManualForm({
        date: format(new Date(), 'yyyy-MM-dd'),
        vendor: '',
        amount: 0,
        currency: defaultCurrency,
        category: '',
        note: '',
      })
      await Promise.all([loadManualCosts(activeRange, manualArchiveView), loadSummary(activeRange)])
    } catch (error) {
      showNotice('error', extractApiError(error))
    } finally {
      setManualSaving(false)
    }
  }

  async function handleManualUpdate() {
    if (!manualEditor) {
      return
    }
    if (!manualForm.vendor.trim()) {
      showNotice('error', 'Unternehmen ist ein Pflichtfeld.')
      return
    }

    const amount = Number(manualForm.amount)
    if (Number.isNaN(amount) || amount <= 0) {
      showNotice('error', 'Betrag muss größer als 0 sein.')
      return
    }

    setManualSaving(true)
    try {
      await api.put(`/manual-costs/${manualEditor.id}`, {
        date: manualForm.date || null,
        vendor: manualForm.vendor.trim(),
        amount,
        currency: manualForm.currency || defaultCurrency,
        category: manualForm.category?.trim() || null,
        note: manualForm.note?.trim() || null,
      } satisfies ManualCostPayload)
      showNotice('success', 'Eintrag aktualisiert.')
      setManualEditor(null)
      await Promise.all([loadManualCosts(activeRange, manualArchiveView), loadSummary(activeRange)])
    } catch (error) {
      showNotice('error', extractApiError(error))
    } finally {
      setManualSaving(false)
    }
  }

  async function handleManualArchive(itemId: number) {
    setManualDeleting(itemId)
    try {
      await api.patch(`/manual-costs/${itemId}/archive`)
      showNotice('success', 'Archiviert. Zum Rückgängig machen den Filter "Archiv anzeigen" aktivieren.')
      await Promise.all([loadManualCosts(activeRange, manualArchiveView), loadSummary(activeRange)])
    } catch (error) {
      showNotice('error', extractApiError(error))
    } finally {
      setManualDeleting(null)
    }
  }

  async function handleManualRestore(itemId: number) {
    setManualDeleting(itemId)
    try {
      await api.patch(`/manual-costs/${itemId}/restore`)
      showNotice('success', 'Eintrag wiederhergestellt.')
      await Promise.all([loadManualCosts(activeRange, manualArchiveView), loadSummary(activeRange)])
    } catch (error) {
      showNotice('error', extractApiError(error))
    } finally {
      setManualDeleting(null)
    }
  }

  function showNotice(type: NoticeType, message: string) {
    setNotice({ type, message })
  }

  function handlePageChange(page: PageKey) {
    setActivePage(page)
    setSidebarOpen(false)
  }

  function handleRangeApply() {
    if (rangeDraft.range === 'custom' && (!rangeDraft.from || !rangeDraft.to)) {
      showNotice('error', 'Bitte für den benutzerdefinierten Zeitraum Start und Ende setzen.')
      return
    }
    setActiveRange(rangeDraft)
  }

  const topVendors = useMemo(() => summary?.top_vendors ?? [], [summary])
  const topCategories = useMemo(() => summary?.costs_by_category ?? [], [summary])
  const maxVendorAmount = Math.max(...topVendors.map((item) => item.amount), 1)
  const maxCategoryAmount = Math.max(...topCategories.map((item) => item.amount), 1)
  const appTitle = 'Kostenübersicht'
  const projectName = config?.project_name?.trim() || 'Pool'
  const projectTagName = config?.project_tag_name?.trim() || config?.pool_tag_name?.trim() || 'Pool'
  const defaultCurrency = config?.default_currency?.trim() || 'EUR'
  const schedulerStatus = config?.scheduler_enabled ? 'aktiv' : 'inaktiv'
  const paperlessStatus = health?.paperless_ok ? '🟢 erreichbar' : '🔴 prüfen'
  const exportBaseParams = useMemo(() => {
    const invoiceParams = buildInvoiceFilterParams(invoiceFilters)
    return {
      ...buildRangeParams(activeRange),
      ...invoiceParams,
      archived: manualArchiveView,
    }
  }, [activeRange, invoiceFilters, manualArchiveView])
  const exportCurrentHref = useMemo(() => buildExportHref(exportBaseParams), [exportBaseParams])
  const exportNeedsReviewHref = useMemo(
    () => buildExportHref({ ...exportBaseParams, needs_review: 'true' }),
    [exportBaseParams],
  )
  const exportManualHref = useMemo(
    () =>
      buildExportHref({
        ...exportBaseParams,
        source: 'manual',
        needs_review: 'all',
      }),
    [exportBaseParams],
  )
  const reviewProcessedCount = Math.max(reviewSessionTotal - reviewItems.length, 0)
  const reviewPosition = currentReview ? Math.min(reviewProcessedCount + 1, reviewSessionTotal) : reviewSessionTotal
  const reviewRemainingCount = reviewItems.length

  return (
    <div className="app-shell">
      {sidebarOpen && <button className="sidebar-backdrop" onClick={() => setSidebarOpen(false)} aria-label="Navigation schließen" />}

      <aside className={`sidebar ${sidebarOpen ? 'mobile-open' : ''}`}>
        <div>
          <div className="sidebar-title">{appTitle}</div>
          <div className="sidebar-subtitle">Projekt: {projectName}</div>
        </div>

        <nav className="nav-list">
          <button className={navClass(activePage, 'dashboard')} onClick={() => handlePageChange('dashboard')}>
            Dashboard
          </button>
          <button className={navClass(activePage, 'inbox')} onClick={() => handlePageChange('inbox')}>
            <span>Inbox</span>
            {(summary?.needs_review_count ?? 0) > 0 && <span className="nav-badge">{summary?.needs_review_count}</span>}
          </button>
          <button className={navClass(activePage, 'invoices')} onClick={() => handlePageChange('invoices')}>
            Paperless-Rechnungen
          </button>
          <button className={navClass(activePage, 'manual')} onClick={() => handlePageChange('manual')}>
            Manuelle Kosten
          </button>
          <button className={navClass(activePage, 'export')} onClick={() => handlePageChange('export')}>
            Export
          </button>
        </nav>

        <div className="sidebar-footer">
          <div className="status-chip">{health?.status === 'ok' ? 'API erreichbar' : 'API prüfen'}</div>
          <div className="muted-text">/api Proxy aktiv</div>
        </div>
      </aside>

      <main className="main-shell">
        <header className="topbar panel">
          <div className="topbar-head">
            <div className="topbar-main">
              <button className="menu-button" onClick={() => setSidebarOpen(true)} aria-label="Navigation öffnen">
                <span />
                <span />
                <span />
              </button>
              <div className="topbar-title">{appTitle}</div>
              <div className="muted-text topbar-subtitle">
                Projekt: {projectName} · Tag: {projectTagName} · Standard: {defaultCurrency} · Scheduler: {schedulerStatus}
                {config ? ` (${config.scheduler_interval_minutes} min)` : ''}
              </div>
            </div>
            <div className="topbar-status">
              <div className="status-chip" title={health?.paperless_latency_ms ? `Latenz ${health.paperless_latency_ms}ms` : 'Paperless Status'}>
                Paperless {paperlessStatus}
              </div>
              <div className="status-meta">Letzter Sync: {formatLastSync(lastSync?.finished_at)}</div>
              <button className="primary-button sync-button" onClick={() => void handleSync()} disabled={syncing}>
                {syncing ? 'Synchronisiert…' : 'Sync jetzt'}
              </button>
            </div>
          </div>

          {activePage !== 'inbox' && (
            <div className="range-toolbar">
              <label>
                Zeitraum
                <select
                  value={rangeDraft.range}
                  onChange={(event) =>
                    setRangeDraft((current) => ({ ...current, range: event.target.value as RangeKey }))
                  }
                >
                  <option value="all">Alle</option>
                  <option value="month">Aktueller Monat</option>
                  <option value="last_month">Letzter Monat</option>
                  <option value="year">Aktuelles Jahr</option>
                  <option value="custom">Benutzerdefiniert</option>
                </select>
              </label>
              {rangeDraft.range === 'custom' && (
                <>
                  <label>
                    Von
                    <div className="date-input-shell">
                      <input
                        type="date"
                        value={rangeDraft.from}
                        onChange={(event) => setRangeDraft((current) => ({ ...current, from: event.target.value }))}
                      />
                    </div>
                  </label>
                  <label>
                    Bis
                    <div className="date-input-shell">
                      <input
                        type="date"
                        value={rangeDraft.to}
                        onChange={(event) => setRangeDraft((current) => ({ ...current, to: event.target.value }))}
                      />
                    </div>
                  </label>
                </>
              )}
              <div className="range-toolbar-action">
                <button className="secondary-button" onClick={handleRangeApply}>
                  Zeitraum anwenden
                </button>
              </div>
            </div>
          )}
        </header>

        {notice && (
          <div className={`notice ${notice.type}`}>
            <span>{notice.message}</span>
            <button className="notice-close" onClick={() => setNotice(null)}>
              Schließen
            </button>
          </div>
        )}

        {activePage === 'inbox' && (
          <section className="page-stack">
            <section className="panel">
              <div className="section-header">
                <div>
                  <h2>{reviewItems.length === 0 ? 'Inbox leer 🎉' : `${reviewItems.length} Rechnungen prüfen`}</h2>
                  <div className="muted-text inbox-progress-meta">
                    {reviewItems.length === 0
                      ? 'Für den gewählten Zeitraum gibt es keine offenen Review-Fälle.'
                      : `${reviewPosition} von ${reviewSessionTotal} · Noch ${reviewRemainingCount} offen`}
                  </div>
                </div>
              </div>
              <div className="form-grid form-grid-inbox">
                <label>
                  Zeitraum
                  <select
                    value={rangeDraft.range}
                    onChange={(event) =>
                      setRangeDraft((current) => ({ ...current, range: event.target.value as RangeKey }))
                    }
                  >
                    <option value="all">Alle</option>
                    <option value="month">Aktueller Monat</option>
                    <option value="last_month">Letzter Monat</option>
                    <option value="year">Aktuelles Jahr</option>
                    <option value="custom">Benutzerdefiniert</option>
                  </select>
                </label>
                {rangeDraft.range === 'custom' && (
                  <>
                    <label>
                      Von
                      <div className="date-input-shell">
                        <input
                          type="date"
                          value={rangeDraft.from}
                          onChange={(event) => setRangeDraft((current) => ({ ...current, from: event.target.value }))}
                        />
                      </div>
                    </label>
                    <label>
                      Bis
                      <div className="date-input-shell">
                        <input
                          type="date"
                          value={rangeDraft.to}
                          onChange={(event) => setRangeDraft((current) => ({ ...current, to: event.target.value }))}
                        />
                      </div>
                    </label>
                  </>
                )}
                <label>
                  Sortierung
                  <select
                    value={reviewSort}
                    onChange={(event) => setReviewSort(event.target.value as ReviewSort)}
                  >
                    <option value="amount_desc">Betrag zuerst</option>
                    <option value="date_desc">Neueste zuerst</option>
                  </select>
                </label>
                <div className="filter-action">
                  <button
                    className="primary-button"
                    onClick={handleRangeApply}
                    disabled={reviewLoading || reviewSaving}
                  >
                    Anwenden
                  </button>
                </div>
              </div>
            </section>

            {reviewLoading && (
              <section className="panel">
                <div className="section-header">
                  <div>
                    <h2>Inbox lädt…</h2>
                  </div>
                </div>
              </section>
            )}

            {!reviewLoading && currentReview && (
              <section className="panel inbox-panel">
                <div className="section-header">
                  <div>
                    <h2>{currentReview.vendor ?? 'Unbekanntes Unternehmen'}</h2>
                    <div className="muted-text">
                      {formatDateTime(currentReview.paperless_created)} · Confidence {Math.round(currentReview.confidence * 100)}%
                    </div>
                  </div>
                  <div className="inbox-progress">{reviewPosition} / {reviewSessionTotal}</div>
                </div>
                <div className="inbox-card">
                  <div className="inbox-summary">
                    <div className="inbox-amount">{formatCurrency(currentReview.amount)}</div>
                    <div className="inbox-title-line">{currentReview.title ?? 'Ohne Titel'}</div>
                    <div className="inbox-meta-list">
                      <div className="muted-text">Doc ID {currentReview.paperless_doc_id}</div>
                      {buildPaperlessDocumentHref(config?.paperless_base_url, currentReview.paperless_doc_id) && (
                        <a
                          className="secondary-button inbox-link"
                          href={buildPaperlessDocumentHref(config?.paperless_base_url, currentReview.paperless_doc_id)}
                          target="_blank"
                          rel="noreferrer"
                        >
                          In Paperless öffnen
                        </a>
                      )}
                    </div>
                    {(currentReview.vendor_source === 'manual' || currentReview.amount_source === 'manual') && (
                      <div className="inbox-lock-note">
                        <span>🔒 Manuelle Überschreibung aktiv</span>
                        {currentReview.vendor_source === 'manual' && <span>Unternehmen</span>}
                        {currentReview.amount_source === 'manual' && <span>Betrag</span>}
                      </div>
                    )}
                  </div>

                  <div className="form-grid">
                    <label>
                      Unternehmen
                      <input
                        value={reviewForm.vendor}
                        onChange={(event) => setReviewForm((current) => ({ ...current, vendor: event.target.value }))}
                      />
                    </label>
                    <label>
                      Betrag
                      <input
                        type="number"
                        step="0.01"
                        value={reviewForm.amount}
                        onChange={(event) => setReviewForm((current) => ({ ...current, amount: event.target.value }))}
                      />
                    </label>
                    <label className="full-width">
                      OCR Kontext
                      <textarea value={currentReview.ocr_snippet ?? currentReview.ocr_text ?? ''} readOnly />
                    </label>
                  </div>

                  <div className="inbox-actions">
                    <button
                      className="primary-button"
                      onClick={() => void handleReviewSaveAndNext()}
                      disabled={reviewSaving}
                    >
                      {reviewSaving ? 'Speichert…' : 'Speichern & Weiter'}
                    </button>
                    <button
                      className="secondary-button"
                      onClick={() => void handleReviewResolve()}
                      disabled={reviewSaving}
                    >
                      Nur als geprüft markieren
                    </button>
                    <button
                      className="secondary-button"
                      onClick={handleReviewNext}
                      disabled={reviewSaving || reviewItems.length <= 1}
                    >
                      Überspringen
                    </button>
                  </div>

                  <div className="shortcut-hint">
                    Shortcuts: Enter = Speichern & Weiter · N = Weiter · P = Zurück · Esc = Schließen
                  </div>

                  <div className="inbox-nav">
                    <button
                      className="table-button"
                      onClick={handleReviewPrev}
                      disabled={reviewSaving || reviewCursor === 0}
                    >
                      Zurück (P)
                    </button>
                    <button
                      className="table-button"
                      onClick={handleReviewNext}
                      disabled={reviewSaving || reviewCursor >= reviewItems.length - 1}
                    >
                      Weiter (N)
                    </button>
                  </div>
                </div>
              </section>
            )}

            {!reviewLoading && !currentReview && (
              <section className="panel">
                <div className="section-header">
                  <div>
                    <h2>Inbox leer 🎉</h2>
                    <div className="muted-text">Alle unsicheren Rechnungen für diesen Zeitraum sind abgearbeitet.</div>
                  </div>
                </div>
              </section>
            )}
          </section>
        )}

        {activePage === 'dashboard' && (
          <section className="page-grid">
            <div className="metrics-grid">
              <MetricCard label="Gesamtsumme" value={formatCurrency(summary?.total_amount)} />
              <MetricCard label="Paperless" value={formatCurrency(summary?.paperless_total)} />
              <MetricCard label="Manuell" value={formatCurrency(summary?.manual_total)} />
              <MetricCard label="Needs Review" value={String(summary?.needs_review_count ?? 0)} />
            </div>

            <div className="content-grid">
              <section className="panel">
                <h2>Top 10 Unternehmen</h2>
                <div className="muted-text">Summierte Paperless-Kosten</div>
                <div className="bar-list">
                  {topVendors.length === 0 && <div className="empty-state">Noch keine Rechnungen vorhanden.</div>}
                  {topVendors.map((item) => (
                    <BarRow
                      key={item.name}
                      label={item.name ?? 'Ohne Name'}
                      value={item.amount}
                      maxValue={maxVendorAmount}
                    />
                  ))}
                </div>
              </section>

              <section className="panel">
                <h2>Kosten nach Kategorie</h2>
                <div className="muted-text">Nur manuelle Kostenpositionen</div>
                <div className="bar-list">
                  {topCategories.length === 0 && <div className="empty-state">Noch keine manuellen Kosten vorhanden.</div>}
                  {topCategories.map((item) => (
                    <BarRow
                      key={item.category}
                      label={item.category ?? 'Unkategorisiert'}
                      value={item.amount}
                      maxValue={maxCategoryAmount}
                    />
                  ))}
                </div>
              </section>
            </div>

            <section className="panel">
              <div className="section-header">
                <div>
                  <h2>Letzte Syncs</h2>
                  <div className="muted-text">Die letzten 10 Synchronisationsläufe</div>
                </div>
              </div>
              <div className="table-wrap">
                <table className="data-table sync-table">
                  <thead>
                    <tr>
                      <th>Zeit</th>
                      <th>Dauer</th>
                      <th>Geprüft</th>
                      <th>Neu</th>
                      <th>Aktualisiert</th>
                      <th>Fehler</th>
                    </tr>
                  </thead>
                  <tbody>
                    {syncRuns.map((run) => (
                      <tr
                        key={run.id ?? run.finished_at}
                        className={run.errors.first_error ? 'clickable-row' : ''}
                        onClick={() => {
                          if (run.errors.first_error) {
                            showNotice('info', run.errors.first_error)
                          }
                        }}
                      >
                        <td className="cell-nowrap">{formatDateTime(run.finished_at)}</td>
                        <td className="cell-nowrap">{formatDuration(run.duration_ms)}</td>
                        <td className="cell-nowrap">{run.checked_docs}</td>
                        <td className="cell-nowrap">{run.new_invoices}</td>
                        <td className="cell-nowrap">{run.updated_invoices}</td>
                        <td className="cell-nowrap">{run.errors.count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {syncRuns.length === 0 && <div className="empty-state">Noch keine Sync-Läufe vorhanden.</div>}
              </div>
            </section>
          </section>
        )}

        {activePage === 'invoices' && (
          <section className="page-stack">
            <section className="panel">
              <h2>Filter</h2>
              <div className="form-grid form-grid-filters">
                <label>
                  Needs Review
                  <select
                    value={invoiceDraft.needsReview}
                    onChange={(event) =>
                      setInvoiceDraft((current) => ({ ...current, needsReview: event.target.value as InvoiceFilters['needsReview'] }))
                    }
                  >
                    <option value="all">Alle</option>
                    <option value="only">Nur needs_review</option>
                  </select>
                </label>
                <label>
                  Unternehmen/Titel
                  <input
                    value={invoiceDraft.search}
                    onChange={(event) => setInvoiceDraft((current) => ({ ...current, search: event.target.value }))}
                    placeholder="z. B. Muster GmbH"
                  />
                </label>
                <label>
                  Sortierung
                  <select
                    value={invoiceDraft.sort}
                    onChange={(event) =>
                      setInvoiceDraft((current) => ({ ...current, sort: event.target.value as InvoiceFilters['sort'] }))
                    }
                  >
                    <option value="date_desc">Neueste zuerst</option>
                    <option value="date_asc">Älteste zuerst</option>
                    <option value="amount_desc">Betrag absteigend</option>
                    <option value="amount_asc">Betrag aufsteigend</option>
                  </select>
                </label>
                <div className="filter-action">
                  <button
                    className="primary-button"
                    onClick={() => {
                      setInvoiceFilters(invoiceDraft)
                    }}
                    disabled={invoiceLoading}
                  >
                    Anwenden
                  </button>
                </div>
              </div>
            </section>

            <section className="panel">
              <div className="section-header">
                <div>
                  <h2>Paperless-Rechnungen</h2>
                  <div className="muted-text">{invoiceLoading ? 'Lädt…' : `${invoices.length} Einträge`}</div>
                </div>
              </div>
              <div className="desktop-only table-wrap">
                <table className="data-table invoices-table">
                  <thead>
                    <tr>
                      <th>Datum</th>
                      <th>Unternehmen</th>
                      <th>Betrag</th>
                      <th>Titel</th>
                      <th>Confidence</th>
                      <th>Needs Review</th>
                      <th>Doc ID</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {invoices.map((invoice) => (
                      <tr key={invoice.id}>
                        <td className="cell-nowrap">{formatDateTime(invoice.paperless_created)}</td>
                        <td className="cell-nowrap">
                          {invoice.vendor_source === 'manual' && (
                            <span className="override-lock" title="Manuell angepasst – wird beim Sync nicht überschrieben">
                              🔒
                            </span>
                          )}
                          {invoice.vendor ?? '–'}
                        </td>
                        <td className="cell-nowrap">
                          {invoice.amount_source === 'manual' && (
                            <span className="override-lock" title="Manuell angepasst – wird beim Sync nicht überschrieben">
                              🔒
                            </span>
                          )}
                          {formatCurrency(invoice.amount)}
                        </td>
                        <td className="cell-truncate">{invoice.title ?? '–'}</td>
                        <td className="cell-nowrap">{Math.round(invoice.confidence * 100)}%</td>
                        <td className="cell-nowrap">{invoice.needs_review ? 'Ja' : 'Nein'}</td>
                        <td className="cell-nowrap">{invoice.paperless_doc_id}</td>
                        <td>
                          <button className="table-button" onClick={() => setInvoiceEditor(invoice)}>
                            Bearbeiten
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!invoiceLoading && invoices.length === 0 && <div className="empty-state">Keine Rechnungen gefunden.</div>}
              </div>
              <div className="mobile-only mobile-card-list">
                {invoices.map((invoice) => (
                  <InvoiceCard
                    key={invoice.id}
                    invoice={invoice}
                    amountLabel={formatCurrency(invoice.amount)}
                    dateLabel={formatDateTime(invoice.paperless_created)}
                    paperlessHref={buildPaperlessDocumentHref(config?.paperless_base_url, invoice.paperless_doc_id)}
                    onEdit={(item) => setInvoiceEditor(item)}
                  />
                ))}
                {!invoiceLoading && invoices.length === 0 && <div className="empty-state">Keine Rechnungen gefunden.</div>}
              </div>
            </section>
          </section>
        )}

        {activePage === 'manual' && (
          <section className="page-stack">
            <section className="panel">
              <h2>Neue Position</h2>
              <div className="form-grid">
                <label>
                  Datum
                  <div className="date-input-shell">
                    <input
                      type="date"
                      value={String(manualForm.date ?? '')}
                      onChange={(event) => setManualForm((current) => ({ ...current, date: event.target.value }))}
                    />
                  </div>
                </label>
                <label>
                  Unternehmen *
                  <input
                    value={manualForm.vendor}
                    onChange={(event) => setManualForm((current) => ({ ...current, vendor: event.target.value }))}
                    placeholder="z. B. Musterfirma GmbH"
                  />
                </label>
                <label>
                  Betrag *
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={String(manualForm.amount)}
                    onChange={(event) => setManualForm((current) => ({ ...current, amount: Number(event.target.value) }))}
                    placeholder="1299.00"
                  />
                </label>
                <label>
                  Kategorie
                  <input
                    value={manualForm.category ?? ''}
                    onChange={(event) => setManualForm((current) => ({ ...current, category: event.target.value }))}
                    placeholder="z. B. Technik"
                  />
                </label>
                <label className="full-width">
                  Notiz
                  <textarea
                    value={manualForm.note ?? ''}
                    onChange={(event) => setManualForm((current) => ({ ...current, note: event.target.value }))}
                    placeholder="Optional…"
                  />
                </label>
              </div>
              <div className="actions-row">
                <button className="primary-button" onClick={() => void handleManualCreate()} disabled={manualSaving}>
                  {manualSaving ? 'Speichert…' : 'Anlegen'}
                </button>
              </div>
            </section>

            <section className="panel">
              <div className="section-header">
                <div>
                  <h2>Manuelle Kosten</h2>
                  <div className="muted-text">{manualLoading ? 'Lädt…' : `${manualCosts.length} Einträge`}</div>
                </div>
                <label className="toggle-inline">
                  <input
                    type="checkbox"
                    checked={manualArchiveView === 'all'}
                    onChange={(event) => setManualArchiveView(event.target.checked ? 'all' : 'active')}
                  />
                  <span>Archiv anzeigen</span>
                </label>
              </div>
              <div className="desktop-only table-wrap">
                <table className="data-table manual-table">
                  <thead>
                    <tr>
                      <th>Datum</th>
                      <th>Unternehmen</th>
                      <th>Betrag</th>
                      <th>Kategorie</th>
                      <th>Notiz</th>
                      <th>Archiviert</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {manualCosts.map((item) => (
                      <tr key={item.id}>
                        <td className="cell-nowrap">{formatDateOnly(item.date)}</td>
                        <td className="cell-nowrap">{item.vendor}</td>
                        <td className="cell-nowrap">{formatCurrency(item.amount)}</td>
                        <td className="cell-nowrap">{item.category ?? '–'}</td>
                        <td className="cell-truncate">{item.note ?? '–'}</td>
                        <td className="cell-nowrap">{item.is_archived ? 'Ja' : 'Nein'}</td>
                        <td>
                          <div className="table-actions">
                            <button className="table-button" onClick={() => setManualEditor(item)}>
                              Bearbeiten
                            </button>
                            <button
                              className="table-button danger"
                              onClick={() => void (item.is_archived ? handleManualRestore(item.id) : handleManualArchive(item.id))}
                              disabled={manualDeleting === item.id}
                            >
                              {manualDeleting === item.id ? 'Speichert…' : item.is_archived ? 'Wiederherstellen' : 'Archivieren'}
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!manualLoading && manualCosts.length === 0 && <div className="empty-state">Noch keine Einträge vorhanden.</div>}
              </div>
              <div className="mobile-only mobile-card-list">
                {manualCosts.map((item) => (
                  <ManualCostCard
                    key={item.id}
                    item={item}
                    amountLabel={formatCurrency(item.amount)}
                    dateLabel={formatDateOnly(item.date)}
                    isBusy={manualDeleting === item.id}
                    onEdit={(entry) => setManualEditor(entry)}
                    onArchiveToggle={(entry) => {
                      void (entry.is_archived ? handleManualRestore(entry.id) : handleManualArchive(entry.id))
                    }}
                  />
                ))}
                {!manualLoading && manualCosts.length === 0 && <div className="empty-state">Noch keine Einträge vorhanden.</div>}
              </div>
            </section>
          </section>
        )}

        {activePage === 'export' && (
          <section className="page-stack">
            <section className="panel">
              <h2>Export</h2>
              <p className="muted-text">CSV verwendet den aktuellen Zeitraum und die aktiven Filter. Downloads laufen direkt ueber den UI-Proxy.</p>
              <div className="actions-row">
                <a className="primary-button link-button" href={exportCurrentHref} target="_blank" rel="noreferrer">
                  CSV exportieren (aktueller Filter)
                </a>
                <a className="secondary-button link-button" href={exportNeedsReviewHref} target="_blank" rel="noreferrer">
                  CSV exportieren: nur Needs Review
                </a>
                <a className="secondary-button link-button" href={exportManualHref} target="_blank" rel="noreferrer">
                  CSV exportieren: nur Manuell
                </a>
              </div>
            </section>
          </section>
        )}

        {invoiceEditor && (
          <div className="modal-backdrop" onClick={() => setInvoiceEditor(null)}>
            <div className="modal panel" onClick={(event) => event.stopPropagation()}>
              <div className="section-header">
                <div>
                  <h2>Rechnung bearbeiten</h2>
                  <div className="muted-text">Doc ID {invoiceEditor.paperless_doc_id}</div>
                </div>
                <button className="table-button" onClick={() => setInvoiceEditor(null)}>
                  Schließen
                </button>
              </div>
              <div className="form-grid">
                <label>
                  Unternehmen
                  <input
                    value={invoiceForm.vendor}
                    onChange={(event) => setInvoiceForm((current) => ({ ...current, vendor: event.target.value }))}
                  />
                </label>
                <label>
                  Betrag
                  <input
                    type="number"
                    step="0.01"
                    value={invoiceForm.amount}
                    onChange={(event) => setInvoiceForm((current) => ({ ...current, amount: event.target.value }))}
                  />
                </label>
                <label className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={invoiceForm.needsReview}
                    onChange={(event) =>
                      setInvoiceForm((current) => ({ ...current, needsReview: event.target.checked }))
                    }
                  />
                  <span>Needs Review</span>
                </label>
                <label className="full-width">
                  OCR Kontext
                  <textarea value={invoiceEditor.ocr_snippet ?? invoiceEditor.ocr_text ?? ''} readOnly />
                </label>
              </div>
              <div className="actions-row">
                {invoiceEditor.vendor_source === 'manual' && (
                  <button className="secondary-button" onClick={() => void handleInvoiceReset('vendor')} disabled={invoiceSaving}>
                    Unternehmen auf auto
                  </button>
                )}
                {invoiceEditor.amount_source === 'manual' && (
                  <button className="secondary-button" onClick={() => void handleInvoiceReset('amount')} disabled={invoiceSaving}>
                    Betrag auf auto
                  </button>
                )}
                <button className="primary-button" onClick={() => void handleInvoiceSave()} disabled={invoiceSaving}>
                  {invoiceSaving ? 'Speichert…' : 'Speichern'}
                </button>
              </div>
            </div>
          </div>
        )}

        {manualEditor && (
          <div className="modal-backdrop" onClick={() => setManualEditor(null)}>
            <div className="modal panel" onClick={(event) => event.stopPropagation()}>
              <div className="section-header">
                <div>
                  <h2>Manuelle Kosten bearbeiten</h2>
                  <div className="muted-text">Eintrag #{manualEditor.id}</div>
                </div>
                <button className="table-button" onClick={() => setManualEditor(null)}>
                  Schließen
                </button>
              </div>
              <div className="form-grid">
                <label>
                  Datum
                  <div className="date-input-shell">
                    <input
                      type="date"
                      value={String(manualForm.date ?? '')}
                      onChange={(event) => setManualForm((current) => ({ ...current, date: event.target.value }))}
                    />
                  </div>
                </label>
                <label>
                  Unternehmen
                  <input
                    value={manualForm.vendor}
                    onChange={(event) => setManualForm((current) => ({ ...current, vendor: event.target.value }))}
                  />
                </label>
                <label>
                  Betrag
                  <input
                    type="number"
                    step="0.01"
                    value={String(manualForm.amount)}
                    onChange={(event) => setManualForm((current) => ({ ...current, amount: Number(event.target.value) }))}
                  />
                </label>
                <label>
                  Kategorie
                  <input
                    value={manualForm.category ?? ''}
                    onChange={(event) => setManualForm((current) => ({ ...current, category: event.target.value }))}
                  />
                </label>
                <label className="full-width">
                  Notiz
                  <textarea
                    value={manualForm.note ?? ''}
                    onChange={(event) => setManualForm((current) => ({ ...current, note: event.target.value }))}
                  />
                </label>
              </div>
              <div className="actions-row">
                <button className="primary-button" onClick={() => void handleManualUpdate()} disabled={manualSaving}>
                  {manualSaving ? 'Speichert…' : 'Speichern'}
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}

function navClass(activePage: PageKey, page: PageKey) {
  return activePage === page ? 'nav-button active' : 'nav-button'
}

function MetricCard(props: { label: string; value: string }) {
  return (
    <section className="panel metric-card">
      <div className="muted-text">{props.label}</div>
      <div className="metric-value">{props.value}</div>
    </section>
  )
}

function BarRow(props: { label: string; value: number; maxValue: number }) {
  const width = Math.max(8, Math.round((props.value / props.maxValue) * 100))

  return (
    <div className="bar-row">
      <div className="bar-head">
        <span>{props.label}</span>
        <span>{formatCurrency(props.value)}</span>
      </div>
      <div className="bar-track">
        <div className="bar-fill" style={{ width: `${width}%` }} />
      </div>
    </div>
  )
}

export default App
