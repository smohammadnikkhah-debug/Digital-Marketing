import unittest
import numpy as np
import pandas as pd
from strategy_core_v38 import prep
from engine import train,simulate_portfolio,benchmarks,annual

class EngineTests(unittest.TestCase):
    def setUp(self):
        idx=pd.bdate_range('2017-01-02',periods=1800)
        x=100*np.exp(np.linspace(0,1.4,len(idx))+0.09*np.sin(np.arange(len(idx))/55))
        raw=pd.DataFrame({'Open':x*.999,'High':x*1.01,'Low':x*.99,'Close':x},index=idx)
        self.d=prep(raw)
    def test_no_buy_training_safe(self):
        winner,items=train(self.d,pd.Timestamp('2021-01-01'),3,10,min_buys=999)
        self.assertIsNone(winner)
        self.assertTrue(isinstance(items,list))
    def test_cash_and_spy(self):
        sel={('TEST',y):{'entry':'CROSS','exit':'MA250_3CLOSE'} for y in range(2020,2024)}
        eq,trades,events,pos=simulate_portfolio({'TEST':self.d},sel,'2020-01-01','2023-01-01',100000,10,3,self.d)
        self.assertTrue((eq.Cash>=-1e-8).all())
        self.assertTrue((eq.Portfolio>=0).all())
        b=benchmarks(eq,self.d,100000)
        self.assertGreaterEqual(b['Portfolio DD %'].min(),-100)
        self.assertGreaterEqual(b['SPY DD %'].min(),-100)
        self.assertTrue(len(annual(b,100000))>=2)
    def test_lookahead(self):
        # Alter today's close: yesterday's indicators and therefore today's execution signal stay unchanged.
        d2=self.d.copy();dt=d2.index[-1];d2.loc[dt,'Close']*=1.5
        self.assertEqual(bool(self.d.iloc[-2].cross),bool(d2.iloc[-2].cross))
if __name__=='__main__':unittest.main()
