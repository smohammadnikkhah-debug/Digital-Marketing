"""V4.0 reliability baseline. Offline-compatible after Yahoo cache is populated."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from strategy_core_v38 import prep, simulate, STRATEGIES, decision

PALETTE={'BUY CANDIDATE':('#C6EFCE','#006100'),'WATCH':('#FFF2CC','#7F6000'),'HOLD':('#D9E1E8','#404040'),'EXIT':('#FF9999','#9C0006'),'AVOID':('#8B0000','#FFFFFF')}

def universe(path):
    df=pd.read_excel(path,sheet_name='Stocks',dtype=str).fillna('')
    df.columns=df.columns.str.strip()
    if not {'Ticker','Enabled'}.issubset(df.columns):raise ValueError('Stocks sheet must contain Ticker and Enabled')
    df['Ticker']=df.Ticker.str.strip().str.upper()
    return df[df.Enabled.str.strip().str.lower().isin(('yes','y','1','true')) & df.Ticker.ne('')].drop_duplicates('Ticker').to_dict('records')

def load(ticker,begin,end,cache,refresh=False):
    cache=Path(cache);cache.mkdir(parents=True,exist_ok=True)
    path=cache/f'{ticker.replace("^", "IDX_").replace("/", "_")}.csv'
    if refresh or not path.exists():
        import yfinance as yf
        d=yf.download(ticker,start=begin,end=end,auto_adjust=True,progress=False,multi_level_index=False)
        if d is None or d.empty:raise ValueError('Yahoo returned no prices')
        d[['Open','High','Low','Close']].to_csv(path,index_label='Date')
    d=pd.read_csv(path,index_col='Date',parse_dates=True).sort_index()
    d=d[~d.index.duplicated(keep='last')]
    d=d.loc[(d.index>=pd.Timestamp(begin)) & (d.index<pd.Timestamp(end))]
    if d.empty:raise ValueError('Cached data does not cover requested dates; run --refresh')
    if (d[['Open','High','Low','Close']]<=0).any().any():raise ValueError('Nonpositive OHLC price')
    return prep(d)

def train(d,asof,years,fee,min_buys=2):
    begin=asof-pd.DateOffset(years=years)
    items=[]
    for ent,ex in STRATEGIES:
        result=simulate(d,begin,asof,ent,ex,fee_bps=fee,collect=False)
        if result:
            m=result[0]
            items.append(dict(entry=ent,exit=ex,strategy=f'{ent}/{ex}',**m))
    valid=[x for x in items if x['buys']>=min_buys and np.isfinite(x['cagr']) and np.isfinite(x['drawdown'])]
    if not valid:return None,items
    tab=pd.DataFrame(valid)
    for field,key,ascending in [('cagr','return_score',True),('drawdown','risk_score',True),('trades_year','frequency_score',False)]:
        tab[key]=tab[field].rank(pct=True,ascending=ascending)
    tab['score']=.4*tab.return_score+.4*tab.risk_score+.2*tab.frequency_score
    tab=tab.sort_values(['score','cagr','strategy'],ascending=[False,False,True])
    return tab.iloc[0].to_dict(),tab.to_dict('records')

def select_all(data,start,end,train_years,fee,min_buys):
    years=range(pd.Timestamp(start).year,pd.Timestamp(end).year+1)
    selections={};rows=[];scores=[]
    total=len(data)
    for stock_number,(ticker,d) in enumerate(data.items(),1):
        print(f'[Strategy selection {stock_number}/{total}] {ticker} — starting',flush=True)
        for year in years:
            asof=pd.Timestamp(f'{year}-01-01')
            if asof < d.index[0]+pd.DateOffset(years=train_years):
                selections[ticker,year]=None
                rows.append([ticker,year,'NONE','',None,0])
                continue
            win,ranked=train(d,asof,train_years,fee,min_buys)
            selections[ticker,year]=win
            rows.append([ticker,year,win['entry'] if win else 'NONE',win['exit'] if win else '',round(win['score'],4) if win else None,int(win['buys']) if win else 0])
            for c in ranked:
                scores.append([ticker,year,c['entry'],c['exit'],round(c['cagr'],3),round(c['drawdown'],3),round(c['trades_year'],3),round(c.get('score',0),4)])
        print(f'[Strategy selection {stock_number}/{total}] {ticker} — completed',flush=True)
    return selections,rows,scores

def simulate_portfolio(data,selections,start,end,capital,fee_bps,max_positions,spy):
    """Shared cash; equal target position slots; signals use previous close; no leverage.
    Calendar intersection uses SPY sessions; missing stock sessions retain last close.
    Rules are selected as of Jan 1. Portfolio starts in cash. No forced annual liquidation.
    """
    fee=fee_bps/10000
    dates=spy.index[(spy.index>=pd.Timestamp(start))&(spy.index<pd.Timestamp(end))]
    if len(dates)<2:raise ValueError('Insufficient SPY benchmark sessions')
    cash=float(capital);positions={};pending={t:False for t in data};last_rule={};last_close={}
    equity=[];trades=[];events=[];year_stats={}
    for dt in dates:
        eligible=[];sell_list=[]
        for t,d in data.items():
            i=d.index.searchsorted(dt)
            if i<len(d) and d.index[i]==dt:
                bar=d.iloc[i];last_close[t]=float(bar.Close)
                if i<1:continue
                prev=d.iloc[i-1];win=selections.get((t,dt.year))
                if win is None:continue
                rule=(win['entry'],win['exit'])
                if last_rule.get(t)!=rule:pending[t]=False;last_rule[t]=rule
                if t in positions:
                    ex=positions[t]['exit'] # Exit rule fixed at entry; annual retraining does not silently alter an open trade
                    if (ex=='MA250_3CLOSE' and bool(prev.below3)) or (ex=='MA250_ATR3' and bool(prev.belowatr3)):
                        sell_list.append((t,float(bar.Open)))
                else:
                    if bool(prev.cross):pending[t]=True
                    if not bool(prev.Close>prev.MA250):pending[t]=False
                    if decision(prev,win['entry'],pending[t]):
                        strength=float(prev.Close/prev.MA250-1) if pd.notna(prev.MA250) and prev.MA250>0 else -999
                        eligible.append((t,float(bar.Open),win,strength))
        for t,op in sell_list:
            p=positions.pop(t);proceeds=p['qty']*op*(1-fee);cash+=proceeds
            trades.append([t,str(p['date'].date()),str(dt.date()),p['entry'],p['exit'],round((proceeds/p['basis']-1)*100,3),round(proceeds-p['basis'],2)])
            events.append([str(dt.date()),t,'EXIT',round(op,4)])
            pending[t]=False
        eligible.sort(key=lambda x:(-x[3],x[0]))
        for t,op,win,_ in eligible:
            if len(positions)>=max_positions:break
            if t in positions:continue
            # Allocate at most one equal slot of *current* marked-to-market portfolio value.
            marked=cash+sum(p['qty']*last_close.get(k,p['open']) for k,p in positions.items())
            budget=min(cash,marked/max_positions)
            qty=int(budget//(op*(1+fee)))
            if qty<1:continue
            basis=qty*op*(1+fee);cash-=basis
            positions[t]=dict(qty=qty,basis=basis,date=dt,entry=win['entry'],exit=win['exit'],open=op)
            pending[t]=False;events.append([str(dt.date()),t,'BUY',round(op,4)])
        value=cash+sum(p['qty']*last_close.get(t,p['open']) for t,p in positions.items())
        if cash< -1e-6 or value< -1e-6:raise AssertionError('Negative cash/equity')
        equity.append([dt,float(value),float(cash),len(positions)])
    return pd.DataFrame(equity,columns=['Date','Portfolio','Cash','Positions']),trades,events,positions

def benchmarks(eq,spy,capital):
    dates=eq.Date
    s=spy.reindex(dates)
    if s.Close.isna().any():raise ValueError('SPY dates missing')
    # Consistent first-session open entry for benchmark and portfolio; adjusted OHLC.
    shares=capital/float(s.Open.iloc[0]);benchmark=shares*s.Close.to_numpy()
    result=eq.copy();result['SPY']=benchmark
    result['Portfolio DD %']=(result.Portfolio/result.Portfolio.cummax().clip(lower=capital)-1)*100
    result['SPY DD %']=(result.SPY/np.maximum.accumulate(np.r_[capital,benchmark])[1:]-1)*100
    return result

def annual(eq,capital):
    out=[];p_prev=capital;b_prev=capital
    for y,g in eq.groupby(eq.Date.dt.year,sort=True):
        p=float(g.Portfolio.iloc[-1]);b=float(g.SPY.iloc[-1]);pr=(p/p_prev-1)*100;br=(b/b_prev-1)*100
        out.append([int(y),str(g.Date.iloc[0].date()),str(g.Date.iloc[-1].date()),round(pr,3),round(br,3),round(pr-br,3),round(p,2),round(b,2),round(float(g['Portfolio DD %'].min()),2),round(float(g['SPY DD %'].min()),2)])
        p_prev=p;b_prev=b
    return out

def today_rows(data,selections,end,positions,universe_rows,fee,train_years,min_buys):
    ht={r['Ticker']:r.get('HT Status','UNKNOWN') or 'UNKNOWN' for r in universe_rows}
    out=[]
    for t,d in data.items():
        if t=='SPY':continue
        win,_=train(d,pd.Timestamp(end),train_years,fee,min_buys)
        r=d.iloc[-1];prev=d.iloc[-2] if len(d)>1 else r
        if win is None or not np.isfinite(r.MA250):status='AVOID';why='Insufficient validated history or qualifying trades'
        elif t in positions:
            ex=positions[t]['exit'];exit_now=bool(r.below3) if ex=='MA250_3CLOSE' else bool(r.belowatr3)
            status='EXIT' if exit_now else 'HOLD';why='Simulated portfolio position; exit rule evaluated on latest close'
        elif bool(r.cross) and decision(r,win['entry'],bool(r.cross)) and win['entry'] not in ('DELAYED_MA50','DELAYED_STACK'):
            status='BUY CANDIDATE';why='New close signal; hypothetical next-session open, HT not verified'
        elif r.Close>r.MA250:status='WATCH';why='Above MA250; monitor for stock-specific entry confirmation'
        else:status='AVOID';why='Below MA250; no current entry'
        out.append([t,str(d.index[-1].date()),round(float(r.Close),2),round(float(r.MA30),2) if pd.notna(r.MA30) else None,round(float(r.MA50),2) if pd.notna(r.MA50) else None,round(float(r.MA250),2) if pd.notna(r.MA250) else None,win['entry'] if win else '',win['exit'] if win else '',status,ht.get(t,'UNKNOWN'),why])
    return out
