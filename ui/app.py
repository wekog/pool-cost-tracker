from __future__ import annotations

import base64
import json
import os
from io import StringIO
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

API_BASE_URL = os.getenv('API_BASE_URL', 'http://api:8000').rstrip('/')
ASSET_BG = Path(__file__).parent / 'assets' / 'pool_bg.jpg'
FONT_STACK = '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, Helvetica, Arial, sans-serif'


@st.cache_data(ttl=5)
def api_get(path: str, params: dict | None = None):
    resp = requests.get(f'{API_BASE_URL}{path}', params=params, timeout=30)
    resp.raise_for_status()
    if path.endswith('.csv'):
        return resp.text
    return resp.json()


def api_post(path: str, payload=None):
    resp = requests.post(f'{API_BASE_URL}{path}', json=payload, timeout=120)
    _raise_with_detail(resp)
    return resp.json() if resp.content else None


def api_put(path: str, payload: dict):
    resp = requests.put(f'{API_BASE_URL}{path}', json=payload, timeout=30)
    _raise_with_detail(resp)
    return resp.json()


def api_delete(path: str):
    resp = requests.delete(f'{API_BASE_URL}{path}', timeout=30)
    _raise_with_detail(resp)
    return resp.json()


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


def clear_cache():
    api_get.clear()


def _date_input_de(label: str, value, key: str | None = None):
    try:
        selected = st.date_input(label, value=value, format='DD.MM.YYYY', key=key)
    except TypeError:
        selected = st.date_input(label, value=value, key=key)
    st.caption(f"Anzeige (DE): {selected.strftime('%d.%m.%Y')}")
    return selected


def apply_theme(theme: str):
    is_dark = theme == 'Dark'
    bg_css = ''
    if (not is_dark) and ASSET_BG.exists():
        encoded = base64.b64encode(ASSET_BG.read_bytes()).decode('ascii')
        bg_css = f'''
        .stApp::before {{
          content: "";
          position: fixed;
          inset: 0;
          background-image: linear-gradient(rgba(255,255,255,.74), rgba(255,255,255,.78)), url("data:image/jpeg;base64,{encoded}");
          background-size: cover;
          background-position: center;
          background-attachment: fixed;
          filter: saturate(0.82) blur(0.5px);
          z-index: -2;
        }}
        '''

    if is_dark:
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
    else:
        theme_vars = """
          :root {
            --bg: #F5F5F7;
            --bg-grad-a: rgba(10,132,255,0.07);
            --bg-grad-b: rgba(255,255,255,0.72);
            --card: rgba(255,255,255,0.92);
            --card-solid: rgba(255,255,255,0.96);
            --surface: #FFFFFF;
            --surface-2: #F1F3F7;
            --text: #111111;
            --muted: rgba(17,17,17,0.60);
            --label: #111111;
            --placeholder: rgba(0,0,0,0.45);
            --border: rgba(0,0,0,0.08);
            --border-soft: rgba(0,0,0,0.06);
            --border-strong: rgba(0,0,0,0.16);
            --input-border: rgba(0,0,0,0.18);
            --input-bg: #FFFFFF;
            --accent: #0A84FF;
            --accent-hover: #0077ED;
            --sidebar-bg: rgba(255,255,255,0.78);
            --sidebar-text: rgba(17,17,17,0.92);
            --shadow: 0 10px 26px rgba(15,23,42,0.08);
            --shadow-soft: 0 4px 14px rgba(15,23,42,0.06);
            --alert-bg: rgba(255,255,255,0.94);
            --success-accent: rgba(10,132,255,0.55);
            --error-accent: rgba(255,80,80,0.85);
            --radius: 16px;
            --glass-blur: 10px;
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
    cfg = api_get('/config')
    summary = api_get('/summary')

    col_sync, col_info = st.columns([1, 2])
    with col_sync:
        if st.button('Sync jetzt', use_container_width=True, type='primary'):
            try:
                with st.spinner('Synchronisierung läuft...'):
                    result = api_post('/sync')
                clear_cache()
                st.success(f"{result['synced']} Dokumente synchronisiert ({result['inserted']} neu, {result['updated']} aktualisiert)")
                summary = api_get('/summary')
                cfg = api_get('/config')
            except requests.HTTPError as exc:
                st.error(f'Sync fehlgeschlagen: {exc}')
    with col_info:
        st.markdown(
            f"<div class='card'><div><b>Scheduler</b>: {'aktiv' if cfg['scheduler_enabled'] else 'inaktiv'}</div>"
            f"<div class='muted'>Intervall: {cfg['scheduler_interval_minutes']} min | Run on startup: {cfg['scheduler_run_on_startup']}</div>"
            f"<div class='muted'>Paperless Base URL: {cfg['paperless_base_url']}</div></div>",
            unsafe_allow_html=True,
        )

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


def invoices_page():
    st.title('Paperless-Rechnungen')
    f1, f2, f3 = st.columns([1, 2, 1])
    with f1:
        needs_review_filter = st.selectbox('Needs Review', ['Alle', 'Ja', 'Nein'])
    with f2:
        search = st.text_input('Unternehmen/Titel suchen', placeholder='z. B. Poolbau')
    with f3:
        sort = st.selectbox('Sortierung', ['date_desc', 'amount_desc', 'vendor_asc'])

    params = {'sort': sort}
    if needs_review_filter == 'Ja':
        params['needs_review'] = 'true'
    elif needs_review_filter == 'Nein':
        params['needs_review'] = 'false'
    if search.strip():
        params['search'] = search.strip()

    invoices = api_get('/invoices', params=params)
    if not invoices:
        st.info('Keine Rechnungen gefunden.')
        return

    df = pd.DataFrame(invoices)
    display_cols = [c for c in ['id', 'paperless_doc_id', 'paperless_created', 'vendor', 'amount', 'currency', 'confidence', 'needs_review', 'title'] if c in df.columns]
    st.dataframe(df[display_cols], use_container_width=True, hide_index=True)

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
        clear_cache()
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
                clear_cache()
                st.success('Manuelle Kostenposition angelegt.')
            except requests.HTTPError as exc:
                st.error(f'Bitte prüfen: {exc}')

    rows = api_get('/manual-costs')
    if not rows:
        st.info('Noch keine manuellen Kosten vorhanden.')
        return

    df = pd.DataFrame(rows)
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
                clear_cache()
                st.success('Eintrag aktualisiert.')
            except requests.HTTPError as exc:
                st.error(f'Bitte prüfen: {exc}')
    if delete:
        try:
            api_delete(f"/manual-costs/{selected['id']}")
            clear_cache()
            st.success('Eintrag gelöscht.')
        except requests.HTTPError as exc:
            st.error(f'Aktion fehlgeschlagen: {exc}')


def export_page():
    st.title('Export')
    csv_text = api_get('/export.csv')
    st.download_button('CSV herunterladen', data=csv_text.encode('utf-8'), file_name='pool_costs_export.csv', mime='text/csv', use_container_width=True)
    if csv_text.strip():
        df = pd.read_csv(StringIO(csv_text))
        st.dataframe(df, use_container_width=True, hide_index=True)


def main():
    st.set_page_config(page_title='pool-cost-tracker', layout='wide')
    if 'theme' not in st.session_state:
        st.session_state['theme'] = 'Dark'

    st.sidebar.markdown('## Poolkosten')
    st.sidebar.caption('Kostenübersicht')
    selected_theme = st.sidebar.radio(
        'Design',
        ['Dark', 'Light'],
        index=0 if st.session_state['theme'] == 'Dark' else 1,
        key='theme_selector',
    )
    st.session_state['theme'] = selected_theme
    apply_theme(st.session_state['theme'])
    st.sidebar.caption(f'API: {API_BASE_URL}')
    page = st.sidebar.radio('Seiten', ['Dashboard', 'Paperless-Rechnungen', 'Manuelle Kosten', 'Export'])

    try:
        if page == 'Dashboard':
            dashboard_page()
        elif page == 'Paperless-Rechnungen':
            invoices_page()
        elif page == 'Manuelle Kosten':
            manual_costs_page()
        else:
            export_page()
    except requests.RequestException as exc:
        st.error(f'API-Fehler: {exc}')


if __name__ == '__main__':
    main()
