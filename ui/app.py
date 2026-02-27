from __future__ import annotations

import json
import os
from io import StringIO
from time import perf_counter

import pandas as pd
import requests
import streamlit as st

os.environ.setdefault('STREAMLIT_BROWSER_GATHER_USAGE_STATS', 'false')

API_BASE_URL = os.getenv('API_BASE_URL', 'http://api:8000').rstrip('/')
FONT_STACK = '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, Helvetica, Arial, sans-serif'
CONNECT_TIMEOUT = 1.5
READ_TIMEOUT = 4.0


def _perf_enabled() -> bool:
    return bool(st.session_state.get('perf_debug', False))


def _perf_reset() -> None:
    st.session_state['perf_lines'] = []


def _perf_add(label: str, ms: float, hint: str = '') -> None:
    if not _perf_enabled():
        return
    suffix = f' ({hint})' if hint else ''
    st.session_state.setdefault('perf_lines', []).append(f'{label}: {ms:.1f}ms{suffix}')


@st.cache_resource
def get_http_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({'Accept': 'application/json'})
    return session


def format_api_error(resp_json) -> str:
    field_map = {
        'vendor': 'Unternehmen',
        'amount': 'Betrag',
        'date': 'Datum',
        'category': 'Kategorie',
        'note': 'Notiz',
    }

    if isinstance(resp_json, dict):
        detail = resp_json.get('detail', resp_json)
    else:
        detail = resp_json

    if isinstance(detail, str):
        return detail

    if isinstance(detail, list):
        messages: list[str] = []
        for item in detail:
            if not isinstance(item, dict):
                continue
            loc = item.get('loc') or []
            field = next((str(p) for p in reversed(loc) if isinstance(p, str) and p not in {'body', 'query', 'path'}), None)
            field_label = field_map.get(field or '', field or 'Feld')
            err_type = str(item.get('type') or '')

            if field == 'vendor' and ('string_too_short' in err_type or 'missing' in err_type):
                messages.append('Unternehmen ist Pflicht.')
                continue
            if field == 'amount' and ('missing' in err_type):
                messages.append('Betrag ist Pflicht.')
                continue
            if field == 'amount' and ('greater_than' in err_type or 'greater_than_equal' in err_type):
                messages.append('Betrag muss größer als 0 sein.')
                continue

            raw_msg = str(item.get('msg') or 'Ungültiger Wert')
            messages.append(f'{field_label}: {raw_msg}')

        if messages:
            unique = list(dict.fromkeys(messages))
            return 'Bitte prüfen: ' + ' '.join(unique)

    if isinstance(detail, dict):
        return str(detail.get('message') or detail)

    return str(detail)


def _raise_with_detail(resp: requests.Response) -> None:
    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:
        detail = None
        try:
            payload = resp.json()
            if isinstance(payload, dict):
                detail = format_api_error(payload)
        except Exception:
            detail = None
        if detail:
            raise requests.HTTPError(str(detail), response=resp, request=resp.request) from exc
        raise


def _request(method: str, path: str, *, params: dict | None = None, payload: dict | None = None):
    session = get_http_session()
    start = perf_counter()
    resp = session.request(
        method=method,
        url=f'{API_BASE_URL}{path}',
        params=params,
        json=payload,
        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
    )
    _raise_with_detail(resp)
    elapsed = (perf_counter() - start) * 1000
    _perf_add(f'{method} {path}', elapsed, 'network')
    return resp


@st.cache_data(ttl=30, show_spinner=False)
def get_config_cached():
    return _request('GET', '/config').json()


@st.cache_data(ttl=30, show_spinner=False)
def get_summary_cached():
    return _request('GET', '/summary').json()


@st.cache_data(ttl=30, show_spinner=False)
def get_invoices_cached(needs_review: str, search: str, sort: str):
    params = {'sort': sort}
    if needs_review == 'Ja':
        params['needs_review'] = 'true'
    elif needs_review == 'Nein':
        params['needs_review'] = 'false'
    if search.strip():
        params['search'] = search.strip()
    return _request('GET', '/invoices', params=params).json()


@st.cache_data(ttl=30, show_spinner=False)
def get_manual_costs_cached():
    return _request('GET', '/manual-costs').json()


def get_export_csv():
    start = perf_counter()
    resp = _request('GET', '/export.csv')
    text = resp.text
    _perf_add('render/export payload', (perf_counter() - start) * 1000, 'text')
    return text


def api_post(path: str, payload=None):
    resp = _request('POST', path, payload=payload)
    return resp.json() if resp.content else None


def api_put(path: str, payload: dict):
    return _request('PUT', path, payload=payload).json()


def api_delete(path: str):
    return _request('DELETE', path).json()


def clear_read_caches():
    get_config_cached.clear()
    get_summary_cached.clear()
    get_invoices_cached.clear()
    get_manual_costs_cached.clear()


def _date_input_de(label: str, value, key: str | None = None):
    try:
        selected = st.date_input(label, value=value, format='DD.MM.YYYY', key=key)
    except TypeError:
        selected = st.date_input(label, value=value, key=key)
    st.caption(f"Anzeige (DE): {selected.strftime('%d.%m.%Y')}")
    return selected


def apply_theme():
    bg_css = ''
    theme_vars = """
          :root {
            --bg: #0F1115;
            --bg-grad-a: rgba(47,129,247,0.08);
            --bg-grad-b: rgba(255,255,255,0.03);
            --card: rgba(255,255,255,0.06);
            --card-solid: #171A21;
            --surface: rgba(17,20,26,0.75);
            --surface-2: #141821;
            --text: rgba(255,255,255,0.92);
            --muted: rgba(255,255,255,0.6);
            --label: rgba(255,255,255,0.92);
            --placeholder: rgba(255,255,255,0.45);
            --border: rgba(255,255,255,0.10);
            --border-soft: rgba(255,255,255,0.06);
            --border-strong: rgba(255,255,255,0.18);
            --input-border: rgba(255,255,255,0.18);
            --input-bg: rgba(17,20,26,0.75);
            --accent: #2F81F7;
            --accent-hover: #3b89f7;
            --sidebar-bg: rgba(17,20,26,0.72);
            --sidebar-text: rgba(255,255,255,0.92);
            --shadow: 0 10px 30px rgba(0,0,0,0.35);
            --shadow-soft: 0 6px 18px rgba(0,0,0,0.22);
            --alert-bg: rgba(23,26,33,0.84);
            --success-accent: rgba(47,129,247,0.65);
            --error-accent: rgba(255,80,80,0.9);
            --radius: 16px;
            --glass-blur: 18px;
          }
        """

    table_even = 'var(--surface-2)'
    table_odd = 'color-mix(in srgb, var(--card-solid) 92%, transparent)'

    st.markdown(
        f"""
        <style>
          {theme_vars}
          html, body, [class*="css"], .stApp {{
            font-family: {FONT_STACK};
            color: var(--text) !important;
            background: var(--bg) !important;
          }}
          .stApp {{
            background: var(--bg) !important;
            color: var(--text) !important;
            background-image: radial-gradient(circle at 8% 10%, var(--bg-grad-a), transparent 42%), radial-gradient(circle at 90% 0%, var(--bg-grad-b), transparent 48%) !important;
          }}
          {bg_css}
          .block-container {{ padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1280px; }}
          .block-container > div {{ background: transparent !important; }}
          section[data-testid="stSidebar"] {{
            background: var(--sidebar-bg) !important;
            border-right: 1px solid var(--border-soft) !important;
            backdrop-filter: blur(18px);
          }}
          section[data-testid="stSidebar"] * {{ color: var(--sidebar-text) !important; }}
          section[data-testid="stSidebar"] .stRadio label,
          section[data-testid="stSidebar"] .stCaption {{ opacity: 0.95; }}
          .card {{
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            box-shadow: var(--shadow);
            padding: 14px 16px;
            backdrop-filter: blur(var(--glass-blur));
          }}
          div[data-testid="stForm"] {{
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 16px;
            box-shadow: var(--shadow-soft);
            padding: 0.75rem 0.75rem 0.25rem 0.75rem;
            backdrop-filter: blur(var(--glass-blur));
          }}
          .stTextInput label, .stNumberInput label, .stDateInput label, .stTextArea label, .stSelectbox label {{
            color: var(--label) !important;
            opacity: 1 !important;
            font-weight: 600 !important;
          }}
          .kpi-grid {{ display:grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap:12px; margin: 8px 0 14px; }}
          .kpi-item {{ background: var(--card); border:1px solid var(--border); border-radius:16px; box-shadow: var(--shadow-soft); padding: 14px; backdrop-filter: blur(var(--glass-blur)); }}
          .kpi-label {{ color: var(--muted); font-size: 0.82rem; }}
          .kpi-value {{ font-weight: 650; font-size: 1.4rem; letter-spacing: -0.02em; }}
          .muted {{ color: var(--muted); }}
          div[data-testid="stMetric"] {{ background: var(--card); border:1px solid var(--border); border-radius:16px; padding:8px 10px; box-shadow: var(--shadow-soft); backdrop-filter: blur(var(--glass-blur)); }}
          div[data-testid="stDataFrame"] {{ border-radius: 16px; overflow: hidden; border: 1px solid var(--border); background: var(--card) !important; }}
          [data-testid="stTable"], [data-testid="stDataFrameResizable"] {{ background: var(--card) !important; }}
          h1, h2, h3 {{ color: var(--text) !important; }}
          p, li, span, label, div {{ color: inherit; }}
          .stTextInput > div > div, .stTextArea textarea, .stDateInput > div > div, .stNumberInput > div > div, .stSelectbox > div > div {{
            border-radius: 12px !important;
            border: 1px solid var(--input-border) !important;
            background: var(--input-bg) !important;
          }}
          .stTextInput input, .stTextArea textarea, .stNumberInput input, .stDateInput input {{
            color: var(--text) !important;
            background: var(--input-bg) !important;
            border-radius: 12px !important;
            border: 1px solid var(--input-border) !important;
          }}
          .stTextInput input::placeholder, .stTextArea textarea::placeholder, .stNumberInput input::placeholder, .stDateInput input::placeholder {{
            color: var(--placeholder) !important;
            opacity: 1 !important;
          }}
          .stTextInput input:focus, .stTextArea textarea:focus, .stNumberInput input:focus, .stDateInput input:focus {{
            outline: none !important;
            box-shadow: 0 0 0 2px rgba(47,129,247,0.25) !important;
            border-color: var(--accent) !important;
          }}
          .stNumberInput [data-baseweb="input"], .stDateInput [data-baseweb="input"] {{
            border-radius: 12px !important;
            border: 1px solid var(--input-border) !important;
            background: var(--input-bg) !important;
          }}
          .stNumberInput [data-baseweb="input"]:focus-within, .stDateInput [data-baseweb="input"]:focus-within {{
            box-shadow: 0 0 0 2px rgba(47,129,247,0.25) !important;
            border-color: var(--accent) !important;
          }}
          .stSelectbox [data-baseweb="select"] {{
            background: var(--input-bg) !important;
            border: 1px solid var(--input-border) !important;
            border-radius: 12px !important;
          }}
          .stSelectbox [data-baseweb="select"] * {{ color: var(--text) !important; }}
          .stButton button, .stDownloadButton button {{
            border-radius: 12px;
            border: none !important;
            box-shadow: var(--shadow-soft);
            background: var(--accent) !important;
            color: white !important;
            transition: all .14s ease;
          }}
          .stButton button:hover, .stDownloadButton button:hover {{ opacity: 0.92; }}
          div[data-testid="stAlert"] {{
            border-radius: 12px;
            border: 1px solid var(--border);
            box-shadow: var(--shadow-soft);
            background: var(--alert-bg);
            backdrop-filter: blur(calc(var(--glass-blur) - 4px));
          }}
          div[data-testid="stAlert"] > div {{ background: transparent !important; }}
          div[data-testid="stAlert"][kind="error"] {{ border-left: 4px solid var(--error-accent); border-color: rgba(255,80,80,0.18); }}
          div[data-testid="stAlert"][kind="success"] {{ border-left: 4px solid var(--success-accent); border-color: rgba(47,129,247,0.16); }}
          div[data-testid="stAlert"][kind="info"] {{ border-left: 4px solid rgba(47,129,247,0.55); border-color: rgba(47,129,247,0.14); }}
          div[data-testid="stAlert"] * {{ color: var(--text) !important; }}
          a {{ color: var(--accent); }}
          thead tr {{ background: var(--surface) !important; }}
          tbody tr {{ background: {table_odd} !important; }}
          tbody tr:nth-child(even) {{ background: {table_even} !important; }}
          [data-testid="stDataFrame"] table, [data-testid="stDataFrame"] th, [data-testid="stDataFrame"] td {{ color: var(--text) !important; }}
          [data-testid="stToolbar"] {{ background: transparent !important; }}
          [data-testid="stChart"] > div, .vega-embed, .vega-embed > details {{
            background: var(--card) !important;
            border-radius: 14px;
            backdrop-filter: blur(var(--glass-blur));
            color: var(--text) !important;
          }}
          @media (max-width: 900px) {{ .kpi-grid {{ grid-template-columns: 1fr 1fr; }} }}
          @media (max-width: 560px) {{ .kpi-grid {{ grid-template-columns: 1fr; }} }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def fmt_eur(value):
    if value is None:
        return '-'
    return f'{float(value):,.2f} EUR'.replace(',', 'X').replace('.', ',').replace('X', '.')


def section_card(title: str, subtitle: str | None = None):
    subtitle_html = f'<div class="muted">{subtitle}</div>' if subtitle else ''
    st.markdown(f'<div class="card"><h3 style="margin:0 0 4px 0;">{title}</h3>{subtitle_html}</div>', unsafe_allow_html=True)


def dashboard_page():
    st.title('Dashboard')

    col_sync, col_info = st.columns([1, 2])
    with col_sync:
        if st.button('Sync jetzt', use_container_width=True, type='primary'):
            try:
                with st.spinner('Synchronisierung läuft...'):
                    result = api_post('/sync')
                clear_read_caches()
                st.success(f"{result['synced']} Dokumente synchronisiert ({result['inserted']} neu, {result['updated']} aktualisiert)")
            except requests.HTTPError as exc:
                st.error(f'Sync fehlgeschlagen: {exc}')

    with col_info:
        cfg_start = perf_counter()
        cfg = get_config_cached()
        _perf_add('load config', (perf_counter() - cfg_start) * 1000, 'cache ttl 30s')
        st.markdown(
            f"<div class='card'><div><b>Scheduler</b>: {'aktiv' if cfg['scheduler_enabled'] else 'inaktiv'}</div>"
            f"<div class='muted'>Intervall: {cfg['scheduler_interval_minutes']} min | Run on startup: {cfg['scheduler_run_on_startup']}</div>"
            f"<div class='muted'>Paperless Base URL: {cfg['paperless_base_url']}</div></div>",
            unsafe_allow_html=True,
        )

    summary_placeholder = st.container()
    charts_placeholder = st.container()

    summary_start = perf_counter()
    summary = get_summary_cached()
    _perf_add('load summary', (perf_counter() - summary_start) * 1000, 'cache ttl 30s')

    with summary_placeholder:
        st.markdown(
            f"""
            <div class="kpi-grid">
              <div class="kpi-item"><div class="kpi-label">Gesamtsumme</div><div class="kpi-value">{fmt_eur(summary['total_amount'])}</div></div>
              <div class="kpi-item"><div class="kpi-label">Paperless</div><div class="kpi-value">{fmt_eur(summary['paperless_total'])}</div></div>
              <div class="kpi-item"><div class="kpi-label">Manuell</div><div class="kpi-value">{fmt_eur(summary['manual_total'])}</div></div>
              <div class="kpi-item"><div class="kpi-label">Needs Review</div><div class="kpi-value">{summary['needs_review_count']}</div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    render_start = perf_counter()
    with charts_placeholder:
        left, right = st.columns(2)
        with left:
            section_card('Top 10 Unternehmen', 'Summierte Paperless-Kosten nach Unternehmen')
            top_df = pd.DataFrame(summary.get('top_vendors', []))
            if top_df.empty:
                st.info('Noch keine Rechnungen vorhanden.')
            else:
                top_df = top_df.rename(columns={'name': 'Unternehmen', 'amount': 'Betrag'})
                st.dataframe(top_df, use_container_width=True, hide_index=True)
                st.bar_chart(top_df.set_index('Unternehmen')['Betrag'])
        with right:
            section_card('Kosten nach Kategorie', 'Nur manuelle Kostenpositionen')
            cat_df = pd.DataFrame(summary.get('costs_by_category', []))
            if cat_df.empty:
                st.info('Noch keine manuellen Kategorien vorhanden.')
            else:
                cat_df = cat_df.rename(columns={'category': 'Kategorie', 'amount': 'Betrag'})
                st.dataframe(cat_df, use_container_width=True, hide_index=True)
                st.bar_chart(cat_df.set_index('Kategorie')['Betrag'])
    _perf_add('render dashboard', (perf_counter() - render_start) * 1000)


def invoices_page():
    st.title('Paperless-Rechnungen')

    if 'invoices_filters' not in st.session_state:
        st.session_state['invoices_filters'] = {
            'needs_review': 'Alle',
            'search': '',
            'sort': 'date_desc',
            'limit': 200,
        }

    with st.form('invoice_filter_form'):
        f1, f2, f3, f4 = st.columns([1, 2, 1, 1])
        with f1:
            needs_review_filter = st.selectbox('Needs Review', ['Alle', 'Ja', 'Nein'], index=['Alle', 'Ja', 'Nein'].index(st.session_state['invoices_filters']['needs_review']))
        with f2:
            search = st.text_input('Unternehmen/Titel suchen', value=st.session_state['invoices_filters']['search'], placeholder='z. B. Poolbau')
        with f3:
            sort = st.selectbox('Sortierung', ['date_desc', 'amount_desc', 'vendor_asc'], index=['date_desc', 'amount_desc', 'vendor_asc'].index(st.session_state['invoices_filters']['sort']))
        with f4:
            limit = st.selectbox('Max Zeilen', [50, 100, 200, 500], index=[50, 100, 200, 500].index(st.session_state['invoices_filters']['limit']))
        apply_filters = st.form_submit_button('Anwenden')

    if apply_filters:
        st.session_state['invoices_filters'] = {
            'needs_review': needs_review_filter,
            'search': search,
            'sort': sort,
            'limit': limit,
        }

    filters = st.session_state['invoices_filters']
    data_start = perf_counter()
    invoices = get_invoices_cached(filters['needs_review'], filters['search'], filters['sort'])
    _perf_add('load invoices', (perf_counter() - data_start) * 1000, 'cache ttl 30s')

    if not invoices:
        st.info('Keine Rechnungen gefunden.')
        return

    shown = invoices[: filters['limit']]
    df = pd.DataFrame(shown)
    display_cols = [c for c in ['id', 'paperless_doc_id', 'paperless_created', 'vendor', 'amount', 'currency', 'confidence', 'needs_review', 'title'] if c in df.columns]

    render_start = perf_counter()
    st.dataframe(df[display_cols], use_container_width=True, hide_index=True)
    _perf_add('render invoices table', (perf_counter() - render_start) * 1000)

    st.subheader('Rechnung prüfen / korrigieren')
    options = {f"#{row['id']} | {row.get('vendor') or '-'} | {row.get('title') or '-'}": row for row in invoices}
    selected_label = st.selectbox('Auswahl', list(options.keys()))
    selected = options[selected_label]

    snippet = selected.get('ocr_snippet') or ''
    debug_json = selected.get('debug_json')
    if debug_json:
        try:
            dbg = json.loads(debug_json)
            snippet = dbg.get('context_snippet') or snippet
        except json.JSONDecodeError:
            pass

    with st.form('invoice_edit_form'):
        vendor = st.text_input('Unternehmen', value=selected.get('vendor') or '')
        amount = st.number_input('Betrag (EUR)', min_value=0.0, step=0.01, value=float(selected.get('amount') or 0.0))
        needs_review = st.checkbox('Needs Review', value=bool(selected.get('needs_review', True)))
        st.text_area('OCR Kontextsnippet', value=snippet, height=120, disabled=True)
        save = st.form_submit_button('Speichern')
    if save:
        api_put(f"/invoices/{selected['id']}", {'vendor': vendor or None, 'amount': float(amount), 'needs_review': needs_review})
        clear_read_caches()
        st.success('Rechnung aktualisiert.')


def manual_costs_page():
    st.title('Manuelle Kosten')
    st.subheader('Neue Position')
    with st.form('manual_create'):
        c1, c2 = st.columns(2)
        with c1:
            m_date = _date_input_de('Datum', value=pd.Timestamp.today().date(), key='manual_create_date')
            vendor = st.text_input('Unternehmen *', placeholder='z. B. Poolbau Müller GmbH')
            amount = st.number_input('Betrag (EUR) *', min_value=0.0, step=0.01, help='z. B. 1299,00')
        with c2:
            category = st.text_input('Kategorie', placeholder='z. B. Material / Dienstleistung / Technik')
            note = st.text_area('Notiz', height=110, placeholder='Optional…')
        submit = st.form_submit_button('Anlegen')
    if submit:
        if not vendor.strip():
            st.error('Unternehmen ist ein Pflichtfeld.')
        elif float(amount) <= 0:
            st.error('Betrag muss größer als 0 sein.')
        else:
            try:
                api_post('/manual-costs', {
                    'date': m_date.isoformat(),
                    'vendor': vendor.strip(),
                    'amount': float(amount),
                    'category': category or None,
                    'note': note or None,
                    'currency': 'EUR',
                })
                clear_read_caches()
                st.success('Manuelle Kostenposition angelegt.')
            except requests.HTTPError as exc:
                st.error(f'Bitte prüfen: {exc}')

    data_start = perf_counter()
    rows = get_manual_costs_cached()
    _perf_add('load manual_costs', (perf_counter() - data_start) * 1000, 'cache ttl 30s')

    if not rows:
        st.info('Noch keine manuellen Kosten vorhanden.')
        return

    display_limit = st.selectbox('Max Zeilen', [50, 100, 200, 500], index=2, key='manual_limit')
    shown = rows[:display_limit]

    df = pd.DataFrame(shown)
    st.dataframe(df[['id', 'date', 'vendor', 'amount', 'currency', 'category', 'note']], use_container_width=True, hide_index=True)

    st.subheader('Bearbeiten / Löschen')
    options = {f"#{r['id']} | {r['vendor']} | {r['amount']} {r['currency']}": r for r in rows}
    selected_label = st.selectbox('Eintrag', list(options.keys()))
    selected = options[selected_label]
    with st.form('manual_edit'):
        e_date = _date_input_de('Datum', value=pd.to_datetime(selected['date']).date(), key='manual_edit_date')
        e_vendor = st.text_input('Unternehmen', value=selected['vendor'])
        e_amount = st.number_input('Betrag (EUR)', min_value=0.01, step=0.01, value=float(selected['amount']))
        e_category = st.text_input('Kategorie', value=selected.get('category') or '')
        e_note = st.text_area('Notiz', value=selected.get('note') or '', height=100)
        col_a, col_b = st.columns(2)
        save = col_a.form_submit_button('Speichern')
        delete = col_b.form_submit_button('Löschen')
    if save:
        if not e_vendor.strip():
            st.error('Unternehmen ist ein Pflichtfeld.')
        elif float(e_amount) <= 0:
            st.error('Betrag muss größer als 0 sein.')
        else:
            try:
                api_put(f"/manual-costs/{selected['id']}", {
                    'date': e_date.isoformat(),
                    'vendor': e_vendor.strip(),
                    'amount': float(e_amount),
                    'category': e_category or None,
                    'note': e_note or None,
                    'currency': selected.get('currency', 'EUR'),
                })
                clear_read_caches()
                st.success('Eintrag aktualisiert.')
            except requests.HTTPError as exc:
                st.error(f'Bitte prüfen: {exc}')
    if delete:
        try:
            api_delete(f"/manual-costs/{selected['id']}")
            clear_read_caches()
            st.success('Eintrag gelöscht.')
        except requests.HTTPError as exc:
            st.error(f'Aktion fehlgeschlagen: {exc}')


def export_page():
    st.title('Export')
    csv_text = get_export_csv()
    st.download_button('CSV herunterladen', data=csv_text.encode('utf-8'), file_name='pool_costs_export.csv', mime='text/csv', use_container_width=True)
    if csv_text.strip():
        df = pd.read_csv(StringIO(csv_text))
        st.dataframe(df.head(200), use_container_width=True, hide_index=True)


def _render_perf_debug():
    if not _perf_enabled():
        return
    lines = st.session_state.get('perf_lines', [])
    with st.sidebar.expander('Performance Debug', expanded=True):
        if not lines:
            st.caption('Keine Messwerte in diesem Run.')
        else:
            st.code('\n'.join(lines), language='text')


def main():
    st.set_page_config(page_title='pool-cost-tracker', layout='wide')
    _perf_reset()

    st.sidebar.markdown('## Poolkosten')
    st.sidebar.caption('Kostenübersicht')
    st.session_state['perf_debug'] = st.sidebar.checkbox('Debug Performance', value=st.session_state.get('perf_debug', False))
    st.sidebar.caption(f'API: {API_BASE_URL}')

    apply_theme()

    page = st.sidebar.radio('Seiten', ['Dashboard', 'Paperless-Rechnungen', 'Manuelle Kosten', 'Export'])

    try:
        render_start = perf_counter()
        if page == 'Dashboard':
            dashboard_page()
        elif page == 'Paperless-Rechnungen':
            invoices_page()
        elif page == 'Manuelle Kosten':
            manual_costs_page()
        else:
            export_page()
        _perf_add(f'render page {page}', (perf_counter() - render_start) * 1000)
    except requests.RequestException as exc:
        st.error(f'API-Fehler: {exc}')

    _render_perf_debug()


if __name__ == '__main__':
    main()
