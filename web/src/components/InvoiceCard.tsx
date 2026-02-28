import type { Invoice } from '../types'

interface InvoiceCardProps {
  invoice: Invoice
  amountLabel: string
  dateLabel: string
  paperlessHref: string
  onEdit: (invoice: Invoice) => void
}

function InvoiceCard(props: InvoiceCardProps) {
  const reviewClass = props.invoice.needs_review ? 'status-badge review' : 'status-badge ok'
  const reviewLabel = props.invoice.needs_review ? 'Needs Review' : 'OK'

  return (
    <article className="mobile-card">
      <div className="mobile-card-header">
        <div className="mobile-card-title">
          {props.invoice.vendor_source === 'manual' && (
            <span className="override-lock" title="Manuell angepasst – wird beim Sync nicht überschrieben">
              🔒
            </span>
          )}
          <span>{props.invoice.vendor ?? '–'}</span>
        </div>
        <div className="mobile-card-amount">
          {props.invoice.amount_source === 'manual' && (
            <span className="override-lock" title="Manuell angepasst – wird beim Sync nicht überschrieben">
              🔒
            </span>
          )}
          <span>{props.amountLabel}</span>
        </div>
      </div>

      <div className="mobile-card-text">{props.invoice.title ?? '–'}</div>

      <div className="mobile-card-meta">
        <span>{props.dateLabel}</span>
        <span>{Math.round(props.invoice.confidence * 100)}%</span>
        <span className={reviewClass}>{reviewLabel}</span>
      </div>

      <div className="mobile-card-submeta">
        <span>Doc ID {props.invoice.paperless_doc_id}</span>
      </div>

      <div className="mobile-card-actions">
        <button className="table-button" onClick={() => props.onEdit(props.invoice)}>
          Bearbeiten
        </button>
        {props.paperlessHref && (
          <a className="secondary-button" href={props.paperlessHref} target="_blank" rel="noreferrer">
            In Paperless öffnen
          </a>
        )}
      </div>
    </article>
  )
}

export default InvoiceCard
