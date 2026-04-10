import pandas as pd
import numpy as np
import streamlit as st
import matplotlib.pyplot as plt

st.set_page_config(page_title="Sell Through Analysis", layout="wide")

st.title("Sell-Through Analysis")
st.caption("Interactive sell-through, stock, weeks cover, and transfer dashboard")


@st.cache_data
def load_data(uploaded_file):
    if uploaded_file is None:
        return None
    if uploaded_file.name.lower().endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)
    df.columns = df.columns.str.strip()
    return df


def latest_soh_total(df):
    all_weeks = df["Week no"].dropna().unique()
    if len(all_weeks) == 0:
        return 0.0
    latest_week = max(all_weeks)
    latest_df = df[df["Week no"] == latest_week].copy()
    return latest_df["SOH"].sum()


def apply_filters(df, store_class, region, buyer, vendor_name, price_bucket, state, mh_segment, mh_family, store_name):
    temp = df.copy()

    def _filter(col, vals):
        nonlocal temp
        if vals:
            temp = temp[temp[col].isin(vals)]

    _filter("Store Classification", store_class)
    _filter("Region", region)
    _filter("PURCHASER NAME", buyer)
    _filter("Vendor Name", vendor_name)
    _filter("MRP Bucket", price_bucket)
    _filter("State", state)
    _filter("MH Segment", mh_segment)
    _filter("MH Family", mh_family)
    _filter("Store Name", store_name)

    return temp


def add_base_metrics(df):
    temp = df.copy()
    temp = temp[temp["SOH"].fillna(0) >= 0]
    temp["Sale"] = pd.to_numeric(temp["Sale"], errors="coerce").fillna(0)
    temp["SOH"] = pd.to_numeric(temp["SOH"], errors="coerce").fillna(0)
    return temp


def weekly_sellthrough(df):
    w = df.groupby("Week no", dropna=False)[["Sale", "SOH"]].sum().reset_index()
    w["Sell_Through"] = np.where(w["SOH"] > 0, w["Sale"] / w["SOH"] * 100, np.nan)
    return w.sort_values("Week no")


def grouped_sellthrough(df, dim):
    sales_part = df.groupby(dim, dropna=False).agg(Sale=("Sale", "sum")).reset_index()

    all_weeks = df["Week no"].dropna().unique()
    latest_week = max(all_weeks) if len(all_weeks) else None
    latest_df = df[df["Week no"] == latest_week].copy() if latest_week is not None else df.copy()
    soh_part = latest_df.groupby(dim, dropna=False).agg(SOH=("SOH", "sum")).reset_index()

    week_level = df.groupby([dim, "Week no"], dropna=False)[["Sale", "SOH"]].sum().reset_index()
    week_level["Week_ST"] = np.where(week_level["SOH"] > 0, week_level["Sale"] / week_level["SOH"] * 100, np.nan)
    st_part = week_level.groupby(dim, dropna=False).agg(Sell_Through=("Week_ST", "mean")).reset_index()

    g = sales_part.merge(soh_part, on=dim, how="outer").merge(st_part, on=dim, how="outer")
    g["Sale"] = g["Sale"].fillna(0)
    g["SOH"] = g["SOH"].fillna(0)
    return g.sort_values("Sell_Through", ascending=False)


def heatmap_pivot(df, dim):
    g = df.groupby([dim, "Week no"], dropna=False)[["Sale", "SOH"]].sum().reset_index()
    g["Sell_Through"] = np.where(g["SOH"] > 0, g["Sale"] / g["SOH"] * 100, np.nan)
    pivot = g.pivot(index=dim, columns="Week no", values="Sell_Through").fillna(0)
    pivot = pivot.reindex(sorted(pivot.columns), axis=1)
    return pivot


def weeks_cover_summary(df, dim="MH Family", recent_weeks=4):
    all_weeks = sorted(df["Week no"].dropna().unique())
    recent = all_weeks[-recent_weeks:] if len(all_weeks) >= recent_weeks else all_weeks
    temp = df[df["Week no"].isin(recent)].copy()

    sales_part = temp.groupby(dim, dropna=False).agg(
        Total_Sale=("Sale", "sum"),
        Weeks_Present=("Week no", "nunique")
    ).reset_index()

    latest_week = max(all_weeks) if all_weeks else None
    latest_df = df[df["Week no"] == latest_week].copy() if latest_week is not None else df.copy()
    soh_part = latest_df.groupby(dim, dropna=False).agg(
        Current_SOH=("SOH", "sum")
    ).reset_index()

    s = sales_part.merge(soh_part, on=dim, how="outer")
    s["Total_Sale"] = s["Total_Sale"].fillna(0)
    s["Weeks_Present"] = s["Weeks_Present"].fillna(0)
    s["Current_SOH"] = s["Current_SOH"].fillna(0)

    s["Avg_Weekly_Sales"] = np.where(s["Weeks_Present"] > 0, s["Total_Sale"] / s["Weeks_Present"], np.nan)
    s["Weeks_Cover"] = np.where(s["Avg_Weekly_Sales"] > 0, s["Current_SOH"] / s["Avg_Weekly_Sales"], np.nan)
    s["Avg_ST"] = np.where((s["Current_SOH"] > 0) & (s["Weeks_Present"] > 0),
                           s["Total_Sale"] / (s["Current_SOH"] * s["Weeks_Present"]) * 100,
                           np.nan)
    s["Role"] = np.where(s["Weeks_Cover"] < 3, "Receiver",
                          np.where(s["Weeks_Cover"] > 8, "Donor", "Balanced"))
    return s.sort_values("Weeks_Cover", ascending=False)


def transfer_engine(df, item_col="GENERIC", min_wc=3, max_wc=8, recent_weeks=4):
    data = df.copy()
    all_weeks = sorted(data["Week no"].dropna().unique())
    recent = all_weeks[-recent_weeks:] if len(all_weeks) >= recent_weeks else all_weeks

    sales_df = data[data["Week no"].isin(recent)].copy()
    sales_grp = sales_df.groupby([item_col, "Site", "Store Name"], dropna=False).agg(
        Sale=("Sale", "sum")
    ).reset_index()

    latest_week = max(all_weeks) if all_weeks else None
    latest_df = data[data["Week no"] == latest_week].copy() if latest_week is not None else data.copy()
    soh_grp = latest_df.groupby([item_col, "Site", "Store Name"], dropna=False).agg(
        Current_SOH=("SOH", "sum")
    ).reset_index()

    grp = sales_grp.merge(soh_grp, on=[item_col, "Site", "Store Name"], how="outer")
    grp["Sale"] = grp["Sale"].fillna(0)
    grp["Current_SOH"] = grp["Current_SOH"].fillna(0)

    denom = max(len(recent), 1)
    grp["Avg_Weekly_Sales"] = grp["Sale"] / denom
    grp["Weeks_Cover"] = np.where(grp["Avg_Weekly_Sales"] > 0, grp["Current_SOH"] / grp["Avg_Weekly_Sales"], np.nan)
    grp["Role"] = np.where(grp["Weeks_Cover"] < min_wc, "Receiver",
                            np.where(grp["Weeks_Cover"] > max_wc, "Donor", "Balanced"))

    transfers = []

    for item, sub in grp.groupby(item_col, dropna=False):
        donors = sub[sub["Role"] == "Donor"].copy().sort_values("Weeks_Cover", ascending=False)
        receivers = sub[sub["Role"] == "Receiver"].copy().sort_values("Weeks_Cover", ascending=True)

        if donors.empty or receivers.empty:
            continue

        for _, r in receivers.iterrows():
            target_stock = r["Avg_Weekly_Sales"] * min_wc
            needed_qty = target_stock - r["Current_SOH"]
            if needed_qty <= 0 or pd.isna(needed_qty):
                continue

            for i, d in donors.iterrows():
                donor_target = d["Avg_Weekly_Sales"] * max_wc
                excess = d["Current_SOH"] - donor_target
                if excess <= 0 or pd.isna(excess):
                    continue

                transfer_qty = min(excess, needed_qty)
                if transfer_qty <= 0:
                    continue

                transfers.append({
                    item_col: item,
                    "From_Store": d["Site"],
                    "From_Store_Name": d["Store Name"],
                    "To_Store": r["Site"],
                    "To_Store_Name": r["Store Name"],
                    "Transfer_Qty": int(round(transfer_qty)),
                    "Donor_WC": round(d["Weeks_Cover"], 2) if pd.notna(d["Weeks_Cover"]) else np.nan,
                    "Receiver_WC": round(r["Weeks_Cover"], 2) if pd.notna(r["Weeks_Cover"]) else np.nan,
                })

                donors.loc[i, "Current_SOH"] -= transfer_qty
                needed_qty -= transfer_qty
                if needed_qty <= 0:
                    break

    transfer_df = pd.DataFrame(transfers)
    return grp, transfer_df


def show_bar(df, x, y, title, horizontal=False):
    fig, ax = plt.subplots(figsize=(10, 5))
    plot_df = df.copy()
    if horizontal:
        ax.barh(plot_df[x].astype(str), plot_df[y])
        ax.set_ylabel(x)
        ax.set_xlabel(y)
    else:
        ax.bar(plot_df[x].astype(str), plot_df[y])
        ax.set_xlabel(x)
        ax.set_ylabel(y)
        ax.tick_params(axis='x', rotation=60)
    ax.set_title(title)
    st.pyplot(fig)


def show_line(df, x, y, title, color_by=None):
    fig, ax = plt.subplots(figsize=(10, 5))
    if color_by is None:
        ax.plot(df[x], df[y], marker="o")
    else:
        for key, sub in df.groupby(color_by):
            ax.plot(sub[x], sub[y], marker="o", label=str(key))
        ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left")
    ax.set_title(title)
    ax.set_xlabel(x)
    ax.set_ylabel(y)
    st.pyplot(fig)


def show_heatmap(pivot, title):
    fig, ax = plt.subplots(figsize=(12, max(5, len(pivot) * 0.35)))
    im = ax.imshow(pivot.values, aspect="auto")
    ax.set_title(title)
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns, rotation=45)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index.astype(str))
    fig.colorbar(im, ax=ax, label="Sell Through %")
    st.pyplot(fig)


def show_scatter(df, x, y, title, label_col=None):
    fig, ax = plt.subplots(figsize=(8, 5))
    plot_df = df.copy()
    plot_df["x"] = pd.to_numeric(plot_df[x], errors="coerce")
    plot_df["y"] = pd.to_numeric(plot_df[y], errors="coerce")
    valid = plot_df.dropna(subset=["x", "y"])

    ax.scatter(valid["x"], valid["y"], alpha=0.7, label="Data")

    if label_col is not None and label_col in valid.columns:
        for _, row in valid.iterrows():
            ax.annotate(str(row[label_col]), (row["x"], row["y"]), textcoords="offset points", xytext=(4, 4), fontsize=8)

    if len(valid) >= 2:
        degree = 2 if len(valid) >= 3 else 1
        coeffs = np.polyfit(valid["x"], valid["y"], degree)
        poly = np.poly1d(coeffs)
        x_curve = np.linspace(valid["x"].min(), valid["x"].max(), 150)
        y_curve = poly(x_curve)
        label = "Quadratic Fit" if degree == 2 else "Linear Fit"
        ax.plot(x_curve, y_curve, color="crimson", linewidth=2, label=label)

    ax.set_xlabel(x)
    ax.set_ylabel(y)
    ax.set_title(title)
    ax.legend()
    st.pyplot(fig)


uploaded_file = st.sidebar.file_uploader("Upload Excel or CSV", type=["xlsx", "xls", "csv"])
df = load_data(uploaded_file)

if df is None:
    st.info("Upload your retail file to start.")
    st.stop()

required_cols = [
    "Week no", "Store Classification", "Region", "PURCHASER NAME", "MRP Bucket",
    "State", "MH Segment", "MH Family", "MH Class", "MH Brick", "Site", "Store Name",
    "GENERIC", "Sale", "SOH"
]
missing = [c for c in required_cols if c not in df.columns]
if missing:
    st.error(f"Missing required columns: {missing}")
    st.stop()

df = add_base_metrics(df)

st.sidebar.header("Filters")
store_class = st.sidebar.multiselect("Store Classification", sorted(df["Store Classification"].dropna().astype(str).unique()))
region = st.sidebar.multiselect("Region", sorted(df["Region"].dropna().astype(str).unique()))
buyer = st.sidebar.multiselect("Buyer", sorted(df["PURCHASER NAME"].dropna().astype(str).unique()))
vendor_name = st.sidebar.multiselect("Vendor Name", sorted(df["Vendor Name"].dropna().astype(str).unique())) if "Vendor Name" in df.columns else []
price_bucket = st.sidebar.multiselect("Price Bucket", sorted(df["MRP Bucket"].dropna().astype(str).unique()))
state = st.sidebar.multiselect("State", sorted(df["State"].dropna().astype(str).unique()))
mh_segment = st.sidebar.multiselect("MH Segment", sorted(df["MH Segment"].dropna().astype(str).unique()))
mh_family = st.sidebar.multiselect("MH Family", sorted(df["MH Family"].dropna().astype(str).unique()))
store_name = st.sidebar.multiselect("Store Name", sorted(df["Store Name"].dropna().astype(str).unique()))

analysis_dim = st.sidebar.selectbox(
    "Analysis Dimension",
    ["MH Family", "MH Segment", "MH Class", "MH Brick", "PURCHASER NAME", "Vendor Name", "Region", "MRP Bucket", "Store Classification", "Store Name"]
)
recent_weeks = st.sidebar.slider("Recent weeks for Weeks Cover / Transfers", 2, 12, 4)
transfer_item = st.sidebar.selectbox("Transfer item level", ["GENERIC", "MH Brick", "MH Class", "MH Family"])

filtered = apply_filters(df, store_class, region, buyer, vendor_name, price_bucket, state, mh_segment, mh_family, store_name)

if filtered.empty:
    st.warning("No data after applying filters.")
    st.stop()

weekly = weekly_sellthrough(filtered)
total_sales = filtered["Sale"].sum()
total_soh = latest_soh_total(filtered)
overall_st = weekly["Sell_Through"].mean(skipna=True)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Sales", f"{total_sales:,.0f}")
c2.metric("Total SOH (Latest Snapshot)", f"{total_soh:,.0f}")
c3.metric("Overall Sell Through %", f"{overall_st:.2f}" if pd.notna(overall_st) else "NA")
c4.metric("Weeks in Data", f"{filtered['Week no'].nunique()}")

summary_tab, trend_tab, compare_tab, heatmap_tab, inventory_tab, transfer_tab, data_tab = st.tabs([
    "Summary", "Trends", "Comparisons", "Heatmap", "Inventory", "Transfers", "Data"
])

with summary_tab:
    st.subheader("Business Summary")
    st.dataframe(filtered.head(20), use_container_width=True)

    st.subheader(f"Top {analysis_dim} by Sell Through")
    g = grouped_sellthrough(filtered, analysis_dim).head(20)
    st.dataframe(g, use_container_width=True)
    show_bar(g.head(15), analysis_dim, "Sell_Through", f"Top {analysis_dim} by Sell Through")

with trend_tab:
    st.subheader("Weekly Trends")
    st.dataframe(weekly, use_container_width=True)
    show_line(weekly, "Week no", "Sale", "Weekly Sales")
    show_line(weekly, "Week no", "Sell_Through", "Weekly Sell Through %")

    st.subheader("Weekly Sell Through by Store Classification")
    sc_week = filtered.groupby(["Week no", "Store Classification"], dropna=False)[["Sale", "SOH"]].sum().reset_index()
    sc_week["Sell_Through"] = np.where(sc_week["SOH"] > 0, sc_week["Sale"] / sc_week["SOH"] * 100, np.nan)
    st.dataframe(sc_week, use_container_width=True)
    show_line(sc_week.sort_values("Week no"), "Week no", "Sell_Through", "Weekly Sell Through by Store Classification", color_by="Store Classification")

with compare_tab:
    st.subheader(f"{analysis_dim} Comparison")
    comp = grouped_sellthrough(filtered, analysis_dim)
    st.dataframe(comp, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        show_bar(comp.head(15), analysis_dim, "Sale", f"Top {analysis_dim} by Sale")
    with col2:
        show_bar(comp.head(15), analysis_dim, "Sell_Through", f"Top {analysis_dim} by Sell Through")

    st.subheader("Store Classification Comparison")
    sc = filtered.groupby("Store Classification", dropna=False)[["Sale", "SOH"]].sum().reset_index()
    sc["Sell_Through"] = np.where(sc["SOH"] > 0, sc["Sale"] / sc["SOH"] * 100, np.nan)
    st.dataframe(sc, use_container_width=True)
    show_bar(sc, "Store Classification", "Sell_Through", "Sell Through by Store Classification")

with heatmap_tab:
    st.subheader(f"Heatmap: {analysis_dim} vs Week")
    pivot = heatmap_pivot(filtered, analysis_dim)
    st.dataframe(pivot, use_container_width=True)
    show_heatmap(pivot, f"{analysis_dim} vs Week Sell Through %")

with inventory_tab:
    st.subheader("Inventory Health")
    inv = weeks_cover_summary(filtered, analysis_dim, recent_weeks=recent_weeks)
    st.dataframe(inv, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        show_bar(inv.head(20), analysis_dim, "Weeks_Cover", f"Weeks Cover by {analysis_dim}")
    with col2:
        role_counts = inv["Role"].value_counts().reset_index()
        role_counts.columns = ["Role", "Count"]
        show_bar(role_counts, "Role", "Count", "Receiver / Balanced / Donor")

    scatter_df = inv[[analysis_dim, "Avg_Weekly_Sales", "Weeks_Cover"]].dropna()
    if not scatter_df.empty:
        st.subheader("Sales Speed vs Weeks Cover")
        show_scatter(scatter_df, "Avg_Weekly_Sales", "Weeks_Cover", "Avg Weekly Sales vs Weeks Cover", label_col=analysis_dim)

with transfer_tab:
    st.subheader("Store to Store Transfer Engine")
    base_table, transfer_plan = transfer_engine(filtered, item_col=transfer_item, recent_weeks=recent_weeks)

    st.markdown("**Base Table**")
    st.dataframe(base_table, use_container_width=True)

    st.markdown("**Transfer Plan**")
    if transfer_plan.empty:
        st.info("No transfer opportunities found with the current filters and thresholds.")
    else:
        st.dataframe(transfer_plan, use_container_width=True)
        tp = transfer_plan.groupby("From_Store", dropna=False)["Transfer_Qty"].sum().reset_index()
        show_bar(tp.head(20), "From_Store", "Transfer_Qty", "Outgoing Transfer Qty by Store")

with data_tab:
    st.subheader("Filtered Data")
    st.dataframe(filtered, use_container_width=True)

    csv = filtered.to_csv(index=False).encode("utf-8")
    st.download_button("Download Filtered Data", csv, file_name="filtered_retail_data.csv", mime="text/csv")

    inv_csv = weeks_cover_summary(filtered, analysis_dim, recent_weeks=recent_weeks).to_csv(index=False).encode("utf-8")
    st.download_button("Download Inventory Summary", inv_csv, file_name="inventory_summary.csv", mime="text/csv")

st.sidebar.markdown("---")
st.sidebar.caption("Tip: start with no filters, then narrow by P1/P2/P3, Region, Buyer, and Price Bucket.")
