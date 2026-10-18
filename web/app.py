import streamlit as st
from components import (
    render_catalog_table,
    render_control_bar,
    render_metrics_row,
    render_styles,
)

from services import (
    fetch_catalog_data, 
    fetch_system_info, 
    fetch_dashboard_metrics
)


st.set_page_config(
    page_title="Yoru-Agent Security Dashboard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

render_styles()

st.markdown("### 🛡️ Yoru-Agent Dashboard — Infrastructure Hardening Control Plane")
st.markdown("---")

if "page_num" not in st.session_state:
  st.session_state.page_num = 1

sys_info = fetch_system_info()
catalog_list, total_items = fetch_catalog_data(
    page=st.session_state.page_num, per_page=10
)
dashboard_metrics = fetch_dashboard_metrics()

render_metrics_row(sys_info, dashboard_metrics)

render_control_bar()

render_catalog_table(catalog_list, total_items)