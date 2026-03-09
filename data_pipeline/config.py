import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "crypto_quant")
    DB_DSN = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    CHAIN = "a_stock"
    MARKET = "a_stock"  # 新增：市场类型，支持 "crypto" 和 "a_stock"
    TIMEFRAME = "1d" # A 股使用日线数据
    MIN_LIQUIDITY_USD = 10000000.0  # A 股流动性阈值
    MIN_FDV = 100000000.0  # A 股市值阈值          
    MAX_FDV = float('inf') 
    BIRDEYE_API_KEY = os.getenv("BIRDEYE_API_KEY", "")
    BIRDEYE_IS_PAID = True
    USE_DEXSCREENER = False
    TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN", "")  # 新增：Tushare API Token
    USE_TUSHARE = True  # 新增：是否使用 Tushare 获取 A 股数据
    CONCURRENCY = 30  # 增加并发数
    HISTORY_DAYS = 30  # 增加历史数据长度