import os
from dotenv import load_dotenv

load_dotenv()

class ExecutionConfig:
    # A股交易配置
    BROKER_API_URL = os.getenv("BROKER_API_URL", "填入券商API地址")
    BROKER_API_KEY = os.getenv("BROKER_API_KEY", "填入券商API密钥")
    BROKER_SECRET_KEY = os.getenv("BROKER_SECRET_KEY", "填入券商API密钥")
    ACCOUNT_ID = os.getenv("ACCOUNT_ID", "填入账户ID")

    # 交易参数
    DEFAULT_SLIPPAGE = 0.001 # 0.1%
    ORDER_TIMEOUT = 30 # 订单超时时间（秒）
