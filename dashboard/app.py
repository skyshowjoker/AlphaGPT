import streamlit as st
import pandas as pd
import time
from data_service import DashboardService
from visualizer import plot_pnl_distribution, plot_market_scatter

st.set_page_config(
    page_title="AlphaGPT A股策略",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .metric-card {
        background-color: #1E1E1E;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #333;
    }
    .stDataFrame { border: none; }
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def get_service():
    return DashboardService()

svc = get_service()

st.sidebar.title("AlphaGPT A股策略")
st.sidebar.markdown("---")

with st.sidebar:
    st.subheader("账户状态")
    bal = svc.get_wallet_balance()
    st.metric("账户余额", f"{bal:.2f} 元")
    
    st.markdown("---")
    st.subheader("控制面板")
    if st.button("刷新数据"):
        st.rerun()
        
    if st.button("紧急停止", type="primary"):
        with open("STOP_SIGNAL", "w") as f:
            f.write("STOP")
        st.error("已发送停止信号，程序将在下一个周期终止。")

col1, col2, col3, col4 = st.columns(4)
portfolio_df = svc.load_portfolio()
market_df = svc.get_market_overview()
strategy_data = svc.load_strategy_info()

open_positions = len(portfolio_df)
total_invested = portfolio_df['initial_cost_sol'].sum() if not portfolio_df.empty else 0.0

with col1:
    st.metric("持仓数量", f"{open_positions} / 5")
with col2:
    st.metric("总投资额", f"{total_invested:.2f} 元")
with col3:
    if not portfolio_df.empty:
        current_val = (portfolio_df['amount_held'] * portfolio_df['highest_price']).sum()
        pnl_cny = current_val - total_invested
        st.metric("未实现盈亏(估算)", f"{pnl_cny:+.2f} 元", delta_color="normal")
    else:
        st.metric("未实现盈亏", "0.00 元")
with col4:
    st.metric("当前策略", "AlphaGPT-A股", help=str(strategy_data))

tab1, tab2, tab3 = st.tabs(["当前持仓", "市场扫描", "系统日志"])

with tab1:
    st.subheader("当前持仓")
    if not portfolio_df.empty:
        # Display Table
        display_cols = ['symbol', 'entry_price', 'highest_price', 'amount_held', 'pnl_pct', 'is_moonbag']
        
        # Format for display
        show_df = portfolio_df[display_cols].copy()
        show_df['pnl_pct'] = show_df['pnl_pct'].apply(lambda x: f"{x:.2%}")
        show_df['entry_price'] = show_df['entry_price'].apply(lambda x: f"{x:.2f}")
        show_df['highest_price'] = show_df['highest_price'].apply(lambda x: f"{x:.2f}")
        
        st.dataframe(show_df, use_container_width=True, hide_index=True)
        
        # Display Chart
        st.plotly_chart(plot_pnl_distribution(portfolio_df), use_container_width=True)
    else:
        st.info("当前无持仓，策略正在扫描...")

with tab2:
    st.subheader("市场扫描结果")
    if not market_df.empty:
        st.plotly_chart(plot_market_scatter(market_df), use_container_width=True)
        st.dataframe(market_df, use_container_width=True)
    else:
        st.warning("数据库中未找到市场数据，数据管道是否正在运行？")

with tab3:
    st.subheader("系统日志 (最近20条)")
    logs = svc.get_recent_logs(20)
    if logs:
        st.code("".join(logs), language="text")
    else:
        st.caption("未找到日志或日志文件路径不正确。")

time.sleep(1) 
if st.checkbox("自动刷新 (30秒)", value=True):
    time.sleep(30)
    st.rerun()