export type PageKey = 'dashboard' | 'invoices' | 'manual' | 'export'
export type RangeKey = 'month' | 'last_month' | 'year' | 'all' | 'custom'

export interface HealthResponse {
  status: string
  paperless_ok: boolean
  paperless_latency_ms: number | null
}

export interface ConfigResponse {
  paperless_base_url: string
  project_name: string
  project_tag_name: string
  pool_tag_name: string
  scheduler_enabled: boolean
  scheduler_interval_minutes: number
  scheduler_run_on_startup: boolean
}

export interface SummaryBucket {
  name?: string
  category?: string
  amount: number
}

export interface SummaryResponse {
  total_amount: number
  paperless_total: number
  manual_total: number
  invoice_count: number
  manual_cost_count: number
  needs_review_count: number
  top_vendors: SummaryBucket[]
  costs_by_category: SummaryBucket[]
}

export interface Invoice {
  id: number
  source: string
  paperless_doc_id: number
  paperless_created: string | null
  title: string | null
  vendor: string | null
  vendor_source: 'auto' | 'manual'
  amount: number | null
  amount_source: 'auto' | 'manual'
  currency: string
  confidence: number
  needs_review: boolean
  extracted_at: string
  updated_at: string
  debug_json: string | null
  correspondent: string | null
  document_type: string | null
  ocr_text: string | null
  ocr_snippet: string | null
}

export interface InvoiceUpdatePayload {
  vendor?: string | null
  amount?: number | null
  needs_review?: boolean
  reset_vendor?: boolean
  reset_amount?: boolean
}

export interface ManualCost {
  id: number
  source: string
  date: string
  vendor: string
  amount: number
  currency: string
  category: string | null
  note: string | null
  created_at: string
  updated_at: string
}

export interface ManualCostPayload {
  date?: string | null
  vendor: string
  amount: number
  currency?: string
  category?: string | null
  note?: string | null
}

export interface SyncError {
  count: number
  first_error: string | null
}

export interface SyncResponse {
  started_at: string
  finished_at: string
  duration_ms: number
  checked_docs: number
  new_invoices: number
  updated_invoices: number
  skipped_invoices: number
  errors: SyncError
}

export interface SyncRunResponse extends SyncResponse {}
