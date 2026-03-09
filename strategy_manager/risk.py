from .config import StrategyConfig
from loguru import logger

class RiskEngine:
    def __init__(self):
        self.config = StrategyConfig()

    async def check_safety(self, stock_code, amount_cny):
        if amount_cny < 1000000:
            logger.warning(f"[x] Risk: Trading volume too low (¥{amount_cny})")
            return False
        
        # A股风险检查逻辑
        # 这里可以添加更多的风险检查，比如ST股票、停牌股票等
        
        return True

    def calculate_position_size(self, account_balance_cny):
        size = self.config.ENTRY_AMOUNT_CNY
        
        if account_balance_cny < size:
            return 0.0
            
        return size

    async def close(self):
        # A股交易不需要特殊关闭操作
        pass