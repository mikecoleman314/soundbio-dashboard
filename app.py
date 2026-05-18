import streamlit as st
import pandas as pd
import io
from datetime import datetime, date

# --- CONFIGURATION ---
SHEET_ID = "1PS01WSaHwVLh5_lH2MkkJYKFk_Rov7r0wyF-QZo6QNg"

# Set to True when running locally with the sheet shared publicly (anyone with link).
# Set to False for deployment using a service account.
LOCAL_MODE = False

# Tab GIDs - only used in LOCAL_MODE.
# To find a GID: open the sheet, click the tab, read the number after 'gid=' in the URL.
TAB_GIDS = {
    "inventory":      "1270663502",
    "workshop_needs": "448913701",
    "equipment":      "1658838534",
    "maintenance":    "600761903",
    "members":        "1247344170",
    "projects":       "1706407869",
}

# Service account credentials file - only used when LOCAL_MODE = False.
SERVICE_ACCOUNT_FILE = "service_account.json"

SECTION_ORDER = [
    "inventory",
    "workshop_needs",
    "equipment",
    "preventative_maintenance",
    "projects",
    "members",
]

# Filter columns per section.
# List the exact column names to show as multi-select filters.
# Use an empty list [] for no filters. Use None to auto-detect (columns with <= 10 unique values).
SECTION_FILTERS = {
    "inventory":                ["Item Name","Owner" ],
    "workshop_needs":           [],
    "equipment":                ["number_down", "percent_redundancy_par_met"],
    "preventative_maintenance": [],
    "projects":                 [],
    "members":                  [],
}

# Technique columns used in the projects section.
TECHNIQUE_COLS = [
    "PCR", "Microscopy", "Western Blot", "Cell Culture", "Gel Electrophoresis",
    "Spectroscopy", "FTIR", "ELISA", "Autoclave", "Centrifugation",
    "Sequencing", "CRISPR", "Cloning", "Chromatography", "NanoDrop",
    "DNA Extraction", "Serial Dilution", "Staining", "Flow Cytometry",
    "Filtration", "Transformation",
]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300)
def load_tab(tab_name):
    """Load a single tab from the Google Sheet."""
    try:
        if LOCAL_MODE:
            gid = TAB_GIDS[tab_name]
            url = (
                f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
                f"/export?format=csv&gid={gid}"
            )
            return pd.read_csv(url)
        else:
            import gspread
            from google.oauth2.service_account import Credentials

            scopes = [
                "https://www.googleapis.com/auth/spreadsheets.readonly",
                "https://www.googleapis.com/auth/drive.readonly",
            ]
            try:
                creds_info = st.secrets["gcp_service_account"]
                creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
            except Exception:
                creds = Credentials.from_service_account_file(
                    SERVICE_ACCOUNT_FILE, scopes=scopes
                )
            gc = gspread.authorize(creds)
            sh = gc.open_by_key(SHEET_ID)
            worksheet = sh.worksheet(tab_name)
            return pd.DataFrame(worksheet.get_all_records())
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Searchable / filterable table helper
# ---------------------------------------------------------------------------
def searchable_table(df, key_prefix, styler_fn=None, filter_columns=None):
    """Render a dataframe with a search box and multi-select filters.

    filter_columns: list of column names to use as filters, [] for none,
                    or None to auto-detect (columns with <= 10 unique values).
    """
    filtered = df.copy()

    search = st.text_input("Search", key=f"{key_prefix}_search")
    if search:
        mask = pd.Series(False, index=filtered.index)
        for col in filtered.select_dtypes(include="object").columns:
            mask |= filtered[col].astype(str).str.contains(search, case=False, na=False)
        filtered = filtered[mask]

    # Determine filter columns
    if filter_columns is None:
        # Auto-detect: columns with <= 10 unique non-null values
        filter_cols = [
            c for c in filtered.columns
            if filtered[c].nunique(dropna=True) <= 10
            and filtered[c].nunique(dropna=True) > 0
        ]
    else:
        filter_cols = [c for c in filter_columns if c in filtered.columns]

    if filter_cols:
        cols = st.columns(len(filter_cols))
        for i, col_name in enumerate(filter_cols):
            with cols[i]:
                unique_vals = sorted(filtered[col_name].dropna().unique(), key=str)
                chosen = st.multiselect(
                    col_name,
                    options=unique_vals,
                    key=f"{key_prefix}_filter_{col_name}",
                )
                if chosen:
                    filtered = filtered[filtered[col_name].isin(chosen)]

    if styler_fn is not None and not filtered.empty:
        styled = filtered.style.apply(styler_fn, axis=1)
        st.dataframe(styled, use_container_width=True)
    else:
        st.dataframe(filtered, use_container_width=True)

    return filtered


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------
def _drop_unnamed(df):
    """Drop columns whose header is None or starts with 'Unnamed'."""
    to_drop = [
        c for c in df.columns
        if c is None or str(c).startswith("Unnamed")
    ]
    return df.drop(columns=to_drop)


def render_inventory():
    st.header("Inventory")
    df = load_tab("inventory")
    if df is None:
        st.error("Could not load inventory data")
        return
    filtered = searchable_table(df, "inventory", filter_columns=SECTION_FILTERS.get("inventory"))
    st.caption(f"{len(filtered)} items")


def render_workshop_needs():
    st.header("Workshop Needs")
    df = load_tab("workshop_needs")
    if df is None:
        st.error("Could not load workshop_needs data")
        return
    df = _drop_unnamed(df)

    has_qty_min = "Quantity" in df.columns and "Min Level" in df.columns
    has_par = "par_percent" in df.columns

    if has_qty_min:
        qty = pd.to_numeric(df["Quantity"], errors="coerce")
        minl = pd.to_numeric(df["Min Level"], errors="coerce")
        n = int((qty < minl).sum())
        st.metric("Items below min level", n)
    elif has_par:
        par_vals = pd.to_numeric(df["par_percent"], errors="coerce")
        n = int((par_vals < 100).sum())
        st.metric("Items below par", n)

    def _highlight(row):
        if has_qty_min:
            q = pd.to_numeric(row.get("Quantity"), errors="coerce")
            m = pd.to_numeric(row.get("Min Level"), errors="coerce")
            if pd.notna(q) and pd.notna(m) and q < m:
                return ["background-color: yellow; color: black"] * len(row)
        elif has_par:
            val = pd.to_numeric(row.get("par_percent"), errors="coerce")
            if pd.notna(val) and val < 100:
                return ["background-color: yellow; color: black"] * len(row)
        return [""] * len(row)

    searchable_table(df, "workshop_needs", styler_fn=_highlight, filter_columns=SECTION_FILTERS.get("workshop_needs"))


def render_equipment():
    st.header("Equipment")
    df = load_tab("equipment")
    if df is None:
        st.error("Could not load equipment data")
        return
    # Rename unnamed first column
    first_col = df.columns[0]
    if first_col is None or str(first_col).startswith("Unnamed") or first_col == "":
        df = df.rename(columns={first_col: "Equipment"})
    df = _drop_unnamed(df)

    if "percent_redundancy_par_met" in df.columns:
        vals = pd.to_numeric(df["percent_redundancy_par_met"], errors="coerce")
        n = int((vals < 100).sum())
        st.metric("Equipment below redundancy par", n)

    def _highlight(row):
        val = pd.to_numeric(row.get("percent_redundancy_par_met"), errors="coerce")
        if pd.notna(val) and val < 100:
            return ["background-color: yellow; color: black"] * len(row)
        return [""] * len(row)

    searchable_table(df, "equipment", styler_fn=_highlight, filter_columns=SECTION_FILTERS.get("equipment"))


def render_preventative_maintenance():
    st.header("Preventative Maintenance")
    df = load_tab("maintenance")
    if df is None:
        st.error("Could not load preventative_maintenance data")
        return

    today = pd.Timestamp(date.today())
    has_pm_due = "PM_due" in df.columns
    has_pm_due_days = "PM_due_days" in df.columns

    if has_pm_due:
        dates = pd.to_datetime(df["PM_due"], errors="coerce")
        n = int((dates < today).sum())
        st.metric("PMs past due", n)
    elif has_pm_due_days:
        vals = pd.to_numeric(df["PM_due_days"], errors="coerce")
        n = int((vals < 0).sum())
        st.metric("PMs past due", n)

    def _highlight(row):
        if has_pm_due:
            val = pd.to_datetime(row.get("PM_due"), errors="coerce")
            if pd.notna(val) and val < today:
                return ["background-color: yellow; color: black"] * len(row)
        elif has_pm_due_days:
            val = pd.to_numeric(row.get("PM_due_days"), errors="coerce")
            if pd.notna(val) and val < 0:
                return ["background-color: yellow; color: black"] * len(row)
        return [""] * len(row)

    searchable_table(df, "maintenance", styler_fn=_highlight, filter_columns=SECTION_FILTERS.get("preventative_maintenance"))


def render_projects():
    import plotly.express as px
    import plotly.graph_objects as go

    st.header("Projects")
    df = load_tab("projects")
    if df is None:
        st.error("Could not load projects data")
        return

    # Filter out rejected projects
    if "Status" in df.columns:
        df = df[df["Status"] != "Rejected"].copy()

    total_projects = len(df)

    # A. Domain and Status Summary
    st.subheader("Projects by Domain and Status")
    if "Domain" in df.columns and "Status" in df.columns:
        pivot = df.pivot_table(index="Domain", columns="Status", aggfunc="size", fill_value=0)
        pivot = pivot.astype(int)
        st.dataframe(pivot, use_container_width=True)

    # B. Technique Usage Bar Chart
    st.subheader("Technique Usage")
    tech_present = [c for c in TECHNIQUE_COLS if c in df.columns]
    if tech_present and total_projects > 0:
        pcts = {}
        for c in tech_present:
            pcts[c] = (pd.to_numeric(df[c], errors="coerce").sum() / total_projects) * 100
        tech_df = (
            pd.DataFrame({"Technique": list(pcts.keys()), "% of Projects": list(pcts.values())})
            .sort_values("% of Projects", ascending=False)
        )
        fig = px.bar(
            tech_df, x="Technique", y="% of Projects",
            title="Technique Usage (% of Non-Rejected Projects)",
        )
        st.plotly_chart(fig, use_container_width=True)

    # C. Projects per Month
    st.subheader("Projects Submitted per Month")
    if "Timestamp" in df.columns:
        df_ts = df.copy()
        df_ts["Timestamp"] = pd.to_datetime(df_ts["Timestamp"], errors="coerce")
        df_ts = df_ts.dropna(subset=["Timestamp"])
        if not df_ts.empty:
            df_ts["month"] = df_ts["Timestamp"].dt.to_period("M")
            monthly = df_ts.groupby("month").size()
            all_months = pd.period_range(
                start=monthly.index.min(), end=monthly.index.max(), freq="M"
            )
            monthly = monthly.reindex(all_months, fill_value=0)
            month_df = pd.DataFrame({
                "Month": [str(m) for m in monthly.index],
                "Count": monthly.values,
            })
            fig = px.bar(
                month_df, x="Month", y="Count",
                title="Projects Submitted per Month",
            )
            st.plotly_chart(fig, use_container_width=True)

    # D. MCA — two separate plots
    st.subheader("Multiple Correspondence Analysis (MCA)")
    try:
        import prince

        # Identify a project-ID column (try common names, fall back to row index)
        _id_candidates = ["Project Id", "Project ID", "project_id", "ProjectID", "ID", "id",
                          "Project Name", "project_name", "Title", "title", "Name"]
        _id_col = next((c for c in _id_candidates if c in df.columns), None)

        tech_for_mca = [c for c in TECHNIQUE_COLS if c in df.columns]
        mca_df = df[tech_for_mca].copy()
        # Drop columns where all values are identical
        mca_df = mca_df.loc[:, mca_df.nunique() > 1]
        # Convert to string for MCA
        mca_df = mca_df.astype(str)

        if mca_df.shape[1] >= 2 and len(mca_df) >= 2:
            mca = prince.MCA(n_components=2, random_state=42)
            mca = mca.fit(mca_df)

            row_coords = mca.row_coordinates(mca_df)
            col_coords = mca.column_coordinates(mca_df)
            inertia = mca.percentage_of_variance_

            # --- D1. Individuals plot ---
            st.markdown("**Individuals (Projects)**")

            if "Domain" in df.columns:
                domains = df.loc[mca_df.index, "Domain"].astype(str).fillna("Unknown")
            else:
                domains = pd.Series(["Unknown"] * len(mca_df), index=mca_df.index)

            if _id_col:
                labels = df.loc[mca_df.index, _id_col].astype(str).tolist()
            else:
                labels = [str(i) for i in mca_df.index]

            fig_ind = go.Figure()
            for domain in sorted(domains.unique()):
                mask = domains == domain
                fig_ind.add_trace(go.Scatter(
                    x=row_coords.loc[mask, 0],
                    y=row_coords.loc[mask, 1],
                    mode="markers+text",
                    name=domain,
                    text=[labels[i] for i, m in enumerate(mask) if m],
                    textposition="top center",
                    textfont=dict(size=8),
                    marker=dict(size=8),
                    hovertemplate=(
                        "<b>%{text}</b><br>"
                        f"Domain: {domain}<br>"
                        "Dim 1: %{x:.3f}<br>"
                        "Dim 2: %{y:.3f}<extra></extra>"
                    ),
                ))
            fig_ind.update_layout(
                title="MCA — Individuals Plot",
                xaxis_title=f"Dimension 1 ({inertia[0]:.1f}%)",
                yaxis_title=f"Dimension 2 ({inertia[1]:.1f}%)",
                hovermode="closest",
                height=600,
            )
            st.plotly_chart(fig_ind, use_container_width=True)

            # --- D2. Variables plot ---
            st.markdown("**Variables (Techniques)**")

            fig_var = go.Figure()
            for idx, row_data in col_coords.iterrows():
                x_end, y_end = row_data[0], row_data[1]
                # Arrow line from origin to variable point
                fig_var.add_trace(go.Scatter(
                    x=[0, x_end], y=[0, y_end],
                    mode="lines",
                    line=dict(color="steelblue", width=1.5),
                    showlegend=False,
                    hoverinfo="skip",
                ))
                fig_var.add_annotation(
                    x=x_end, y=y_end, ax=0, ay=0,
                    xref="x", yref="y", axref="x", ayref="y",
                    showarrow=True, arrowhead=2, arrowsize=1,
                    arrowwidth=1.5, arrowcolor="steelblue",
                )
                scale = 1.15
                xanchor = "left" if x_end >= 0 else "right"
                yanchor = "bottom" if y_end >= 0 else "top"
                fig_var.add_annotation(
                    x=x_end * scale, y=y_end * scale, text=str(idx),
                    showarrow=False,
                    font=dict(size=9, color="steelblue"),
                    xanchor=xanchor, yanchor=yanchor,
                )
            # Variable points
            fig_var.add_trace(go.Scatter(
                x=col_coords[0],
                y=col_coords[1],
                mode="markers",
                marker=dict(size=7, color="steelblue"),
                text=col_coords.index.astype(str),
                hovertemplate="<b>%{text}</b><br>Dim 1: %{x:.3f}<br>Dim 2: %{y:.3f}<extra></extra>",
                showlegend=False,
            ))
            fig_var.update_layout(
                title="MCA — Variables Plot",
                xaxis_title=f"Dimension 1 ({inertia[0]:.1f}%)",
                yaxis_title=f"Dimension 2 ({inertia[1]:.1f}%)",
                hovermode="closest",
                height=550,
            )
            st.plotly_chart(fig_var, use_container_width=True)

            # --- Downloads ---
            st.subheader("Download Multiple Correspondence Analysis (MCA) Data")
            d1, d2, d3 = st.columns(3)
            with d1:
                buf = io.BytesIO()
                row_coords.to_csv(buf, index=True)
                st.download_button(
                    "Download Embeddings (CSV)",
                    data=buf.getvalue(),
                    file_name="mca_embeddings.csv",
                    mime="text/csv",
                )
            with d2:
                buf = io.BytesIO()
                col_coords.to_csv(buf, index=True)
                st.download_button(
                    "Download Loadings (CSV)",
                    data=buf.getvalue(),
                    file_name="mca_loadings.csv",
                    mime="text/csv",
                )
            with d3:
                buf = io.BytesIO()
                mca_df.to_csv(buf, index=False)
                st.download_button(
                    "Download Raw Data (CSV)",
                    data=buf.getvalue(),
                    file_name="mca_raw_data.csv",
                    mime="text/csv",
                )
        else:
            st.warning("MCA could not be computed.")
    except Exception:
        st.warning("MCA could not be computed.")

    # E. Full project data table
    st.subheader("Project Data")
    searchable_table(df, "projects_table", filter_columns=SECTION_FILTERS.get("projects"))


def render_members():
    st.header("Members")
    df = load_tab("members")
    if df is None:
        st.error("Could not load members data")
        return
    df = _drop_unnamed(df)
    keep = ["Type", "All time members", "Current members", "Total paying (count)"]
    keep = [c for c in keep if c in df.columns]
    df = df[keep]
    st.dataframe(df, use_container_width=True)


# Map section names to renderers
SECTION_RENDERERS = {
    "inventory": render_inventory,
    "workshop_needs": render_workshop_needs,
    "equipment": render_equipment,
    "preventative_maintenance": render_preventative_maintenance,
    "projects": render_projects,
    "members": render_members,
}


# ---------------------------------------------------------------------------
# Summary header helpers
# ---------------------------------------------------------------------------
def _count_active_projects():
    df = load_tab("projects")
    if df is None or "Status" not in df.columns:
        return 0
    return int((df["Status"] != "Rejected").sum())


def _count_pms_due():
    df = load_tab("maintenance")
    if df is None:
        return 0
    if "PM_due" in df.columns:
        today = pd.Timestamp(date.today())
        dates = pd.to_datetime(df["PM_due"], errors="coerce")
        return int((dates < today).sum())
    if "PM_due_days" in df.columns:
        vals = pd.to_numeric(df["PM_due_days"], errors="coerce")
        return int((vals < 0).sum())
    return 0


def _count_workshop_below_min():
    df = load_tab("workshop_needs")
    if df is None:
        return 0
    df = _drop_unnamed(df)
    if "Quantity" in df.columns and "Min Level" in df.columns:
        qty = pd.to_numeric(df["Quantity"], errors="coerce")
        minl = pd.to_numeric(df["Min Level"], errors="coerce")
        return int((qty < minl).sum())
    if "par_percent" in df.columns:
        vals = pd.to_numeric(df["par_percent"], errors="coerce")
        return int((vals < 100).sum())
    return 0


def _count_equipment_below_par():
    df = load_tab("equipment")
    if df is None:
        return 0
    if "percent_redundancy_par_met" in df.columns:
        vals = pd.to_numeric(df["percent_redundancy_par_met"], errors="coerce")
        return int((vals < 100).sum())
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
st.set_page_config(page_title="SoundBio Lab Dashboard", layout="wide")
st.title("SoundBio Lab Dashboard")

col1, col2 = st.columns([3, 1])
with col1:
    st.write(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
with col2:
    if st.button("Refresh Data"):
        st.cache_data.clear()
        st.rerun()

# Summary header
s1, s2, s3, s4 = st.columns(4)
s1.metric("Active Projects", _count_active_projects())
s2.metric("PMs Due", _count_pms_due())
s3.metric("Workshop Needs Below Min", _count_workshop_below_min())
s4.metric("Equipment Below Par", _count_equipment_below_par())

for i, section in enumerate(SECTION_ORDER):
    if i > 0:
        st.markdown("---")
    renderer = SECTION_RENDERERS.get(section)
    if renderer:
        renderer()
