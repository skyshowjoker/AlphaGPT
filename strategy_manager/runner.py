import asyncio
import torch
import json
import time
from loguru import logger
import pandas as pd

from data_pipeline.data_manager import DataManager
from data_pipeline.config import Config
from model_core.vm import StackVM
from model_core.a_stock_data_loader import AStockDataLoader
from execution.trader_factory import TraderFactory
from .config import StrategyConfig
from .portfolio import PortfolioManager
from .risk import RiskEngine

class StrategyRunner:
    def __init__(self):
        self.data_mgr = DataManager()
        self.portfolio = PortfolioManager()
        self.risk = RiskEngine()
        self.trader_factory = TraderFactory()
        self.trader = self.trader_factory.get_trader("simulated")
        self.vm = StackVM()
        
        self.loader = AStockDataLoader(db_dsn=Config.DB_DSN)
        self.stock_map = {} # {stock_code: tensor_index} 用于快速查找特征
        self.last_scan_time = 0
        
        try:
            with open("best_meme_strategy.json", "r") as f:
                # 兼容早期版本
                data = json.load(f)
                self.formula = data if isinstance(data, list) else data.get("formula")
            logger.success(f"Loaded Strategy: {self.formula}")
        except FileNotFoundError:
            logger.critical("Strategy file not found! Please train model first.")
            exit(1)

    async def initialize(self):
        await self.data_mgr.initialize()
        await self.trader.initialize()
        bal = await self.trader.get_balance()
        logger.info(f"Bot Initialized. Account Balance: {bal:.2f} CNY")

    async def run_loop(self):
        logger.info(">_< | Strategy Runner Started (Live Mode)")
        
        while True:
            try:
                loop_start = time.time()
                
                if time.time() - self.last_scan_time > 3600: # 60 min for A-shares
                    logger.info("o.O | Syncing Data Pipeline...")
                    await self.data_mgr.pipeline_sync_daily()
                    self.last_scan_time = time.time()

                await self.loader.load_data(limit_stocks=100)
                await self._build_stock_mapping()

                await self.monitor_positions()
                
                if self.portfolio.get_open_count() < StrategyConfig.MAX_OPEN_POSITIONS:
                    await self.scan_for_entries()
                else:
                    logger.info("=-= | Max positions reached. Scanning skipped.")
                
                elapsed = time.time() - loop_start
                sleep_time = max(10, 60 - elapsed)
                logger.info(f"Cycle finished in {elapsed:.2f}s. Sleeping {sleep_time:.2f}s...")
                await asyncio.sleep(sleep_time)
                
            except Exception as e:
                logger.exception(f"Global Loop Error: {e}")
                await asyncio.sleep(30)

    async def _build_stock_mapping(self):
        query = f"""
        SELECT stock_code, count(*) as cnt 
        FROM ohlcv 
        GROUP BY stock_code 
        ORDER BY cnt DESC 
        LIMIT 100
        """
        df = pd.read_sql(query, self.loader.engine)
        stock_codes = df['stock_code'].tolist()
        
        self.stock_map = {code: idx for idx, code in enumerate(stock_codes)}
        logger.info(f"Mapped {len(self.stock_map)} stocks for inference.")

    async def monitor_positions(self):
        if not self.portfolio.positions: return

        logger.info(f"o.O | Monitoring {len(self.portfolio.positions)} positions...")
        
        for stock_code, pos in list(self.portfolio.positions.items()):
            current_price = await self._fetch_live_price_astock(stock_code)
            if current_price <= 0:
                logger.warning(f"Could not fetch price for {pos.symbol}, skipping.")
                continue

            self.portfolio.update_price(stock_code, current_price)
            
            pnl_pct = (current_price - pos.entry_price) / pos.entry_price
            
            if pnl_pct <= StrategyConfig.STOP_LOSS_PCT:
                logger.warning(f"!!! | STOP LOSS: {pos.symbol} PnL: {pnl_pct:.2%}")
                await self._execute_sell(stock_code, 1.0, "StopLoss")
                continue

            if not pos.is_moonbag and pnl_pct >= StrategyConfig.TAKE_PROFIT_Target1:
                logger.success(f"😄 | MOONBAG TP: {pos.symbol} PnL: {pnl_pct:.2%}")
                await self._execute_sell(stock_code, StrategyConfig.TP_Target1_Ratio, "Moonbag")
                pos.is_moonbag = True
                self.portfolio.save_state()
                continue

            max_gain = (pos.highest_price - pos.entry_price) / pos.entry_price
            drawdown = (pos.highest_price - current_price) / pos.highest_price
            
            if max_gain > StrategyConfig.TRAILING_ACTIVATION and drawdown > StrategyConfig.TRAILING_DROP:
                logger.warning(f"😠 | TRAILING STOP: {pos.symbol} Max: {max_gain:.2%} DD: {drawdown:.2%}")
                await self._execute_sell(stock_code, 1.0, "TrailingStop")
                continue

            if not pos.is_moonbag:
                ai_score = await self._run_inference(stock_code)
                if ai_score != -1 and ai_score < StrategyConfig.SELL_THRESHOLD:
                    logger.info(f"🤖 | AI EXIT: {pos.symbol} Score: {ai_score:.2f}")
                    await self._execute_sell(stock_code, 1.0, "AI_Signal")

    async def scan_for_entries(self):
        raw_signals = self.vm.execute(self.formula, self.loader.feat_tensor)
        
        if raw_signals is None: return

        latest_signals = raw_signals[:, -1]
        scores = torch.sigmoid(latest_signals).cpu().numpy() # 转为概率 0~1
        
        # 翻转排序，从高分到低分处理
        sorted_indices = scores.argsort()[::-1]
        
        # 反向查表：Index -> Stock Code
        # (效率较低，但 Top 100 没关系)
        idx_to_code = {v: k for k, v in self.stock_map.items()}
        
        for idx in sorted_indices:
            score = float(scores[idx])
            
            if score < StrategyConfig.BUY_THRESHOLD:
                break # 后面的都不够分，不用看了
                
            stock_code = idx_to_code.get(idx)
            if not stock_code: continue
            
            # 过滤已持仓
            if stock_code in self.portfolio.positions: continue
            
            # 从 loader 缓存获取该股票的最新成交额
            # raw_data_cache['amount']: [Stocks, Time]
            amount_cny = self.loader.raw_data_cache['amount'][idx, -1].item()
            
            logger.info(f"🔍 | Inspecting {stock_code} | Score: {score:.2f} | Amount: ¥{amount_cny:.0f}")
            
            is_safe = await self.risk.check_safety(stock_code, amount_cny)
            if is_safe:
                await self._execute_buy(stock_code, score)
                
                # 检查仓位上限
                if self.portfolio.get_open_count() >= StrategyConfig.MAX_OPEN_POSITIONS:
                    break

    async def _execute_buy(self, stock_code, score):
        balance = await self.trader.get_balance()
        amount_cny = self.risk.calculate_position_size(balance)
        
        if amount_cny <= 0:
            logger.warning("Insufficient balance for new entry.")
            return

        logger.info(f"🎉 | EXECUTING BUY: {stock_code} | Amt: {amount_cny} CNY")
        
        # 获取股票价格
        market_data = await self.trader.get_market_data(stock_code)
        price = market_data['price']
        
        # 计算购买数量（A股最小单位为100股）
        shares = int(amount_cny // price // 100) * 100
        if shares <= 0:
            logger.warning("Insufficient amount to buy at least 100 shares.")
            return
        
        actual_amount = shares * price
        
        success = await self.trader.buy(stock_code, actual_amount, price)
        
        if success:
            # 更新 Portfolio
            self.portfolio.add_position(
                token=stock_code,
                symbol=stock_code, # 使用股票代码作为符号
                price=price,
                amount=shares,
                cost_sol=actual_amount
            )
            logger.success(f"+ | Position Added: {shares} shares @ {price:.2f} CNY")

    async def _execute_sell(self, stock_code, ratio, reason):
        pos = self.portfolio.positions.get(stock_code)
        if not pos: return

        logger.info(f"- | EXECUTING SELL: {stock_code} | Ratio: {ratio:.0%} | Reason: {reason}")
        
        # 获取股票价格
        market_data = await self.trader.get_market_data(stock_code)
        price = market_data['price']
        
        success = await self.trader.sell(stock_code, ratio, price)
        
        if success:
            new_amount = pos.amount_held * (1.0 - ratio)
            
            # A股最小交易单位为100股
            if ratio > 0.98 or new_amount < 100:
                self.portfolio.close_position(stock_code)
            else:
                # 确保剩余数量为100的整数倍
                new_amount = int(new_amount // 100) * 100
                self.portfolio.update_holding(stock_code, new_amount)
                
            logger.success(f"o.O | Trade Completed: {reason}")

    async def _run_inference(self, stock_code):
        idx = self.stock_map.get(stock_code)
        if idx is None:
            return -1

        features = self.loader.feat_tensor[idx] # 此时是 2D Tensor
        
        features_batch = features.unsqueeze(0) # [1, F, T]
        
        res = self.vm.execute(self.formula, features_batch) # -> [1, Time]
        
        if res is None: return -1
        
        latest_logit = res[0, -1]
        score = torch.sigmoid(latest_logit).item()
        return score

    async def _fetch_live_price_astock(self, stock_code):
        try:
            # 获取股票实时价格
            market_data = await self.trader.get_market_data(stock_code)
            return market_data['price']
        except Exception as e:
            logger.warning(f"Price fetch failed for {stock_code}: {e}")
        
        return 0.0

    async def shutdown(self):
        logger.info("O.o | Shutting down strategy runner...")
        await self.data_mgr.close()
        await self.trader.close()
        await self.trader_factory.close_all()
        await self.loader.close_db()
        await self.risk.close()

if __name__ == "__main__":
    runner = StrategyRunner()
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(runner.initialize())
        loop.run_until_complete(runner.run_loop())
    except KeyboardInterrupt:
        loop.run_until_complete(runner.shutdown())