import pandas as pd
import torch
from .config import ModelConfig
from .factors import FeatureEngineer

class CryptoDataLoader:
    def __init__(self):
        self.feat_tensor = None
        self.raw_data_cache = None
        self.target_ret = None
        
    def load_data(self, limit_tokens=50):
        print("Generating mock data...")
        # Generate mock data for testing
        num_tokens = limit_tokens
        num_time_steps = 100
        
        # Create mock tensors
        device = ModelConfig.DEVICE
        
        # Generate random prices
        base_prices = torch.randn(num_tokens, num_time_steps, device=device) * 0.01 + 1.0
        base_prices = torch.cumprod(base_prices, dim=1)
        base_prices = base_prices * 100  # Scale to realistic prices
        
        # Generate OHLCV data
        open_ = base_prices
        high = base_prices * (1 + torch.randn(num_tokens, num_time_steps, device=device) * 0.01)
        low = base_prices * (1 - torch.randn(num_tokens, num_time_steps, device=device) * 0.01)
        close = base_prices * (1 + torch.randn(num_tokens, num_time_steps, device=device) * 0.005)
        volume = torch.randn(num_tokens, num_time_steps, device=device) * 1000 + 5000
        volume = torch.relu(volume)
        
        # Generate liquidity and FDV
        liquidity = torch.randn(num_tokens, num_time_steps, device=device) * 1e6 + 5e6
        liquidity = torch.relu(liquidity)
        fdv = torch.randn(num_tokens, num_time_steps, device=device) * 10e6 + 50e6
        fdv = torch.relu(fdv)
        
        self.raw_data_cache = {
            'open': open_,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume,
            'liquidity': liquidity,
            'fdv': fdv
        }
        
        self.feat_tensor = FeatureEngineer.compute_features(self.raw_data_cache)
        op = self.raw_data_cache['open']
        t1 = torch.roll(op, -1, dims=1)
        t2 = torch.roll(op, -2, dims=1)
        self.target_ret = torch.log(t2 / (t1 + 1e-9))
        self.target_ret[:, -2:] = 0.0
        
        print(f"Mock data ready. Shape: {self.feat_tensor.shape}")
