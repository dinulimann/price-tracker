"""Streamlit dashboard: streamlit run dashboard/app.py"""

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import psycopg
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tracker.config import settings  # noqa: E402

st.set_page_config(page_title="Price Tracker", page_icon="📉", layout="wide")


@st.cache_data(ttl=60)
def query(sql: str, params: tuple = ()) -> pd.DataFrame:
    with psycopg.connect(settings.database_url) as conn:
        cur = conn.execute(sql, params)
        return pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])


latest = query(
    """
    WITH last AS (SELECT DISTINCT ON (upc) upc, price, stock, run_id
                  FROM price_snapshots ORDER BY upc, run_id DESC),
         first AS (SELECT DISTINCT ON (upc) upc, price AS first_price
                   FROM price_snapshots ORDER BY upc, run_id)
    SELECT p.upc, p.title, p.category, p.rating, last.price::float AS price, last.stock,
           first.first_price::float AS first_price, p.url
    FROM products p JOIN last USING (upc) JOIN first USING (upc)
    """
)
runs = query("SELECT * FROM scrape_runs ORDER BY id DESC LIMIT 20")

st.title("📉 Price Tracker")
if latest.empty:
    st.info("No data yet. Run `python -m tracker scrape` first.")
    st.stop()

last_run = runs.iloc[0]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Products tracked", f"{len(latest):,}")
c2.metric("Categories", latest["category"].nunique())
c3.metric("Out of stock", int((latest["stock"] == 0).sum()))
c4.metric("Alerts in last run", int(last_run["alerts"] or 0))
st.caption(f"Last scrape: {pd.to_datetime(last_run['started_at']):%d %b %Y %H:%M} UTC · "
           f"{len(runs)} run(s) recorded")

# Filters
with st.sidebar:
    st.header("Filters")
    cats = st.multiselect("Category", sorted(latest["category"].unique()))
    pmin, pmax = float(latest["price"].min()), float(latest["price"].max())
    price_range = st.slider("Price (£)", pmin, pmax, (pmin, pmax))
    min_rating = st.slider("Minimum rating", 0, 5, 0)
    search = st.text_input("Search title")

view = latest[latest["price"].between(*price_range) & (latest["rating"] >= min_rating)]
if cats:
    view = view[view["category"].isin(cats)]
if search:
    view = view[view["title"].str.contains(search, case=False)]

left, right = st.columns([3, 2])
with left:
    st.subheader(f"Products ({len(view):,})")
    view = view.assign(change_pct=((view["price"] - view["first_price"]) / view["first_price"] * 100).round(1))
    st.dataframe(
        view[["title", "category", "rating", "price", "change_pct", "stock", "url"]],
        hide_index=True, use_container_width=True,
        column_config={
            "price": st.column_config.NumberColumn("Price", format="£%.2f"),
            "change_pct": st.column_config.NumberColumn("Change since first seen", format="%.1f%%"),
            "url": st.column_config.LinkColumn("Link", display_text="open"),
        },
    )
with right:
    st.subheader("Average price by category")
    by_cat = (view.groupby("category", as_index=False)["price"].mean()
              .sort_values("price", ascending=False).head(15))
    st.plotly_chart(px.bar(by_cat, x="price", y="category", orientation="h")
                    .update_layout(yaxis={"categoryorder": "total ascending"}, height=420,
                                   margin=dict(l=0, r=0, t=10, b=0)),
                    use_container_width=True)

if len(runs) < 2:
    st.subheader("Price distribution")
    st.caption("Price history appears once there are at least two scrape runs.")
    st.plotly_chart(px.histogram(view, x="price", nbins=40)
                    .update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0)), use_container_width=True)
else:
    st.subheader("Price history")
    pick = st.selectbox("Product", view["title"].sort_values().tolist() or latest["title"].tolist())
    upc = latest.loc[latest["title"] == pick, "upc"].iloc[0]
    hist = query(
        """SELECT r.started_at, s.price::float AS price, s.stock
           FROM price_snapshots s JOIN scrape_runs r ON r.id = s.run_id
           WHERE s.upc = %s ORDER BY r.started_at""",
        (upc,),
    )
    st.plotly_chart(px.line(hist, x="started_at", y="price", markers=True)
                    .update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0)), use_container_width=True)

st.subheader("Recent alerts")
alerts = query(
    """SELECT a.created_at, a.kind, p.title, a.old_value::float AS old, a.new_value::float AS new, p.url
       FROM alerts a JOIN products p USING (upc) ORDER BY a.id DESC LIMIT 100"""
)
if alerts.empty:
    st.caption("No alerts yet. Alerts appear after a later run sees a price or stock change.")
else:
    st.dataframe(alerts, hide_index=True, use_container_width=True,
                 column_config={"url": st.column_config.LinkColumn("Link", display_text="open")})

with st.expander("Scrape runs"):
    st.dataframe(runs, hide_index=True, use_container_width=True)
