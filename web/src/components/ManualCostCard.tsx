import type { ManualCost } from '../types'

interface ManualCostCardProps {
  item: ManualCost
  amountLabel: string
  dateLabel: string
  isBusy: boolean
  onEdit: (item: ManualCost) => void
  onArchiveToggle: (item: ManualCost) => void
}

function ManualCostCard(props: ManualCostCardProps) {
  return (
    <article className="mobile-card">
      <div className="mobile-card-header">
        <div className="mobile-card-title">
          <span>{props.item.vendor}</span>
        </div>
        <div className="mobile-card-amount">
          <span>{props.amountLabel}</span>
        </div>
      </div>

      <div className="mobile-card-meta">
        <span>{props.dateLabel}</span>
        <span className="category-badge">{props.item.category ?? 'Unkategorisiert'}</span>
        {props.item.is_archived && <span className="status-badge archived">Archiviert</span>}
      </div>

      {props.item.note && <div className="mobile-card-text">{props.item.note}</div>}

      <div className="mobile-card-actions">
        <button className="table-button" onClick={() => props.onEdit(props.item)}>
          Bearbeiten
        </button>
        <button
          className="table-button danger"
          onClick={() => props.onArchiveToggle(props.item)}
          disabled={props.isBusy}
        >
          {props.isBusy ? 'Speichert…' : props.item.is_archived ? 'Wiederherstellen' : 'Archivieren'}
        </button>
      </div>
    </article>
  )
}

export default ManualCostCard
