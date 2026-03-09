import asyncio
import aiohttp
from loguru import logger
from .config import Config
from .db_manager import DBManager
from .providers.birdeye import BirdeyeProvider
from .providers.dexscreener import DexScreenerProvider
from .providers.tushare import TushareProvider

class DataManager:
    def __init__(self):
        self.db = DBManager()
        self.birdeye = BirdeyeProvider()
        self.dexscreener = DexScreenerProvider()
        self.tushare = TushareProvider()
        self.current_provider = None
        
    async def initialize(self):
        await self.db.connect()
        await self.db.init_schema()

    async def close(self):
        await self.db.close()

    async def pipeline_sync_daily(self):
        # 根据配置选择数据源
        if Config.USE_TUSHARE:
            self.current_provider = self.tushare
            market = "a_stock"
            logger.info("Using Tushare provider for A stock data...")
        else:
            self.current_provider = self.birdeye
            market = "crypto"
            logger.info("Using Birdeye provider for crypto data...")

        logger.info("Step 1: Discovering trending tokens...")
        
        # 设置不同市场的默认限制
        if market == "a_stock":
            limit = 200  # 增加 A 股股票数量
        else:
            limit = 500 if Config.BIRDEYE_IS_PAID else 100
        
        candidates = await self.current_provider.get_trending_tokens(limit=limit)
        
        logger.info(f"Raw candidates found: {len(candidates)}")

        selected_tokens = []
        for t in candidates:
            # 根据市场类型应用不同的过滤逻辑
            if market == "a_stock":
                # A 股过滤逻辑
                # 这里可以根据需要添加 A 股特有的过滤条件
                # 例如：行业、市值、成交量等
                selected_tokens.append(t)
            else:
                # 加密货币过滤逻辑
                liq = t.get('liquidity', 0)
                fdv = t.get('fdv', 0)
                
                if liq < Config.MIN_LIQUIDITY_USD: continue
                if fdv < Config.MIN_FDV: continue
                if fdv > Config.MAX_FDV: continue # 剔除像 WIF/BONK 这种巨无霸，专注于早期高成长
                
                selected_tokens.append(t)
            
        logger.info(f"Tokens selected after filtering: {len(selected_tokens)}")
        
        if not selected_tokens:
            logger.warning("No tokens passed the filter. Relax constraints in Config.")
            return

        # 根据市场类型准备数据库插入数据
        if market == "a_stock":
            db_tokens = [(t['address'], t['symbol'], t['name'], t['decimals'], "a_stock") for t in selected_tokens]
        else:
            db_tokens = [(t['address'], t['symbol'], t['name'], t['decimals'], Config.CHAIN) for t in selected_tokens]
        
        await self.db.upsert_tokens(db_tokens)

        logger.info(f"Step 4: Fetching OHLCV for {len(selected_tokens)} tokens...")
        
        # 使用不同的会话处理逻辑
        if market == "a_stock":
            # Tushare 不需要 aiohttp session
            tasks = []
            for t in selected_tokens:
                tasks.append(self.current_provider.get_token_history(None, t['address']))
            
            batch_size = 20
            total_candles = 0
            
            for i in range(0, len(tasks), batch_size):
                batch = tasks[i:i+batch_size]
                results = await asyncio.gather(*batch)
                
                records = [item for sublist in results if sublist for item in sublist]
                
                # 批量写入
                await self.db.batch_insert_ohlcv(records)
                total_candles += len(records)
                logger.info(f"Processed batch {i}/{len(tasks)}. Inserted {len(records)} candles.")
        else:
            # 加密货币使用 aiohttp session
            async with aiohttp.ClientSession(headers=self.current_provider.headers) as session:
                tasks = []
                for t in selected_tokens:
                    tasks.append(self.current_provider.get_token_history(session, t['address']))
                
                batch_size = 20
                total_candles = 0
                
                for i in range(0, len(tasks), batch_size):
                    batch = tasks[i:i+batch_size]
                    results = await asyncio.gather(*batch)
                    
                    records = [item for sublist in results if sublist for item in sublist]
                    
                    # 批量写入
                    await self.db.batch_insert_ohlcv(records)
                    total_candles += len(records)
                    logger.info(f"Processed batch {i}/{len(tasks)}. Inserted {len(records)} candles.")
                
        logger.success(f"Pipeline complete. Total candles stored: {total_candles}")