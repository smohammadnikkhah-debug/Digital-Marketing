import unittest
from types import SimpleNamespace
from defensive_exits import exit_trigger, exit_reason
from strategy_core_v38 import prep
import pandas as pd
import numpy as np

class DefensiveExitTests(unittest.TestCase):
    def test_hybrid_early_exit(self):
        p=SimpleNamespace(below3=False,belowatr3=False,defensive_ma50=True)
        self.assertTrue(exit_trigger(p,'HYBRID_D'))
        self.assertFalse(exit_trigger(p,'MA250_3CLOSE'))
        self.assertIn('MA50',exit_reason(p,'HYBRID_D'))
    def test_fallback(self):
        p=SimpleNamespace(below3=True,belowatr3=False,defensive_ma50=False)
        self.assertTrue(exit_trigger(p,'HYBRID_D'))
    def test_no_trigger(self):
        p=SimpleNamespace(below3=False,belowatr3=False,defensive_ma50=False)
        self.assertFalse(exit_trigger(p,'HYBRID_D'))
    def test_preparation_columns(self):
        dates=pd.bdate_range('2020-01-01',periods=310)
        x=np.linspace(100,80,len(dates))
        d=prep(pd.DataFrame({'Open':x,'High':x*1.01,'Low':x*.99,'Close':x},index=dates))
        self.assertIn('defensive_ma50',d.columns)
        self.assertFalse(bool(d.iloc[0].defensive_ma50))
if __name__=='__main__':unittest.main()
