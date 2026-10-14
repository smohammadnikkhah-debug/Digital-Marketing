"""V4.0: reliable portfolio-vs-SPY research baseline; NO live orders."""
import argparse
from pathlib import Path
import pandas as pd
import numpy as np
from engine import universe,load,select_all,simulate_portfolio,benchmarks,annual,today_rows
from report import write_report

def main():
    p=argparse.ArgumentParser(description='Adaptive Trading V4.0 research-only baseline')
    p.add_argument('--universe',default='Stock_Universe.xlsx')
    p.add_argument('--start',default='2016-01-01')
    p.add_argument('--end',default=None,help='Exclusive date; defaults to tomorrow')
    p.add_argument('--train-years',type=int,default=5)
    p.add_argument('--min-training-buys',type=int,default=2)
    p.add_argument('--fee-bps',type=float,default=10)
    p.add_argument('--capital',type=float,default=100000)
    p.add_argument('--max-positions',type=int,default=5)
    p.add_argument('--cache',default='price_cache')
    p.add_argument('--refresh',action='store_true',help='Refresh Yahoo adjusted price cache')
    p.add_argument('--output',default='results_v40')
    a=p.parse_args()
    if a.capital<=0 or a.max_positions<1 or a.train_years<2 or a.fee_bps<0:raise SystemExit('Invalid parameters')
    end=a.end or (pd.Timestamp.today().normalize()+pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    begin=(pd.Timestamp(a.start)-pd.DateOffset(years=a.train_years+2)).strftime('%Y-%m-%d')
    rows=universe(a.universe)
    tickers=list(dict.fromkeys([r['Ticker'] for r in rows if r['Ticker']!='SPY']))
    data={};errors=[]
    for t in ['SPY']+tickers:
        try:
            data[t]=load(t,begin,end,a.cache,a.refresh)
            print('Loaded',t,len(data[t]),'sessions',flush=True)
        except Exception as e:
            errors.append([t,'download',str(e)]);print('ERROR',t,str(e),flush=True)
    if 'SPY' not in data:raise SystemExit('SPY unavailable; cannot produce valid benchmark')
    stocks={k:v for k,v in data.items() if k!='SPY'}
    print('Price downloads finished. Starting strategy selection...',flush=True)
    selections,selection_rows,training_rows=select_all(stocks,a.start,end,a.train_years,a.fee_bps,a.min_training_buys)
    print('Strategy selection finished. Simulating portfolio...',flush=True)
    eq,trades,events,positions=simulate_portfolio(stocks,selections,a.start,end,a.capital,a.fee_bps,a.max_positions,data['SPY'])
    eq=benchmarks(eq,data['SPY'],a.capital)
    years=annual(eq,a.capital)
    start_val=float(eq.Portfolio.iloc[0]);last_val=float(eq.Portfolio.iloc[-1]);spy_last=float(eq.SPY.iloc[-1])
    n_years=max((eq.Date.iloc[-1]-eq.Date.iloc[0]).days/365.25,1/365.25)
    p_cagr=(last_val/a.capital)**(1/n_years)-1;s_cagr=(spy_last/a.capital)**(1/n_years)-1
    summary=[['Initial capital',a.capital],['Portfolio ending value',round(last_val,2)],['SPY ending value',round(spy_last,2)],['Portfolio total return %',round((last_val/a.capital-1)*100,3)],['SPY total return %',round((spy_last/a.capital-1)*100,3)],['Portfolio CAGR %',round(p_cagr*100,3)],['SPY CAGR %',round(s_cagr*100,3)],['Portfolio max drawdown %',round(float(eq['Portfolio DD %'].min()),3)],['SPY max drawdown %',round(float(eq['SPY DD %'].min()),3)],['Years beating SPY',sum(x[5]>0 for x in years)],['Years compared',len(years)],['Completed trades',len(trades)],['Cash-only','Yes'],['HT approved','No - research only']]
    today=today_rows(stocks,selections,end,positions,rows,a.fee_bps,a.train_years,a.min_training_buys)
    tables={
        'BenchmarkDashboard':(['Metric','Value'],summary),
        'TodayTrade':(['Ticker','As of','Close','MA30','MA50','MA250','Entry rule','Exit rule','Signal','HT status','Explanation'],today),
        'AnnualVsSPY':(['Year','From','Through','Portfolio return %','SPY return %','Excess pp','Portfolio end $','SPY end $','Portfolio max DD %','SPY max DD %'],years),
        'PortfolioEquity':(['Date','Portfolio $','Cash $','Positions','SPY $','Portfolio DD %','SPY DD %'],[[str(r[0].date()),*[round(float(v),4) for v in r[1:]]] for r in eq.itertuples(index=False,name=None)]),
        'StrategySelection':(['Ticker','Year','Entry','Exit','Train score','Training buys'],selection_rows),
        'TrainingScores':(['Ticker','Year','Entry','Exit','Train CAGR %','Train DD %','Exits per year','Score'],training_rows),
        'Trades':(['Ticker','Entry date','Exit date','Entry rule','Exit rule','Trade return %','Trade PnL $'],trades),
        'Events':(['Date','Ticker','Action','Execution price'],events),
        'Errors':(['Ticker','Stage','Error'],errors),
        'Guide':(['Topic','Explanation'],[
            ['Purpose','Research-only, no broker orders. SPY is a total-return proxy via Yahoo adjusted prices.'],
            ['Strategy weights','40% annualised return, 40% drawdown protection, 20% low trade frequency; these are not return targets.'],
            ['Universe','Edit Stock_Universe.xlsx > Stocks > Ticker and Enabled=Yes, then rerun.'],
            ['Benchmark','Same $100,000 starting cash, same dates; SPY fractional buy at first available adjusted open.'],
            ['Execution','Signals observed at previous close; trades at next session adjusted open; 10bps per side default.'],
            ['Selection','Each Jan 1 uses prior training years only; no future test-year data in training.'],
            ['Allocation','Shared cash, up to max_positions; equal target slots, no borrowing.'],
            ['Exit','Each open position retains its entry-time exit rule even when January strategy changes.'],
            ['TodayTrade','HOLD and EXIT reflect simulated positions, not your brokerage holdings.'],
            ['HT','Unverified HT labels are informational only; no actionable approval.'],
            ['Limitations','No tax, borrow costs, spread or slippage beyond fees; fixed stock universe has survivorship bias.'],
            ['Data','Adjusted OHLC; cached CSVs allow deterministic reruns; --refresh updates cache.'],
            ['Partial years','First/last calendar years are partial; annual returns are for the actual covered period.'],
            ['Pending improvements','Stock-specific drawdown analysis, relative-strength ranking, regimes, out-of-sample holdout.'],
        ])
    }
    output=Path(a.output);output.mkdir(parents=True,exist_ok=True)
    path=output/'Adaptive_Trading_Research_V40.xlsx'
    print('Portfolio complete. Writing Excel report...',flush=True)
    write_report(path,tables)
    print('Saved',path,'|',len(stocks),'stocks |',len(trades),'completed trades |',len(errors),'data errors',flush=True)
if __name__=='__main__':main()
