"""V3.8 research-only walk-forward adaptive MA250 signals. No broker access."""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from defensive_exits import exit_trigger, exit_reason, HYBRID

TICKERS='SPY,QQQ,AMZN,NVDA,GOOGL,META,AMD,MA,ELF,IONQ,NOW'
ENTRIES=('CROSS','MA50_AT_CROSS','DELAYED_MA50','ROC20_AT_CROSS','DELAYED_STACK')
EXITS=('MA250_3CLOSE','MA250_ATR3')
STRATEGIES=tuple((e,x) for e in ENTRIES for x in EXITS)


def prep(raw):
    d=raw[['Open','High','Low','Close']].dropna().sort_index().copy()
    for n in (30,50,250):d[f'MA{n}']=d.Close.rolling(n,min_periods=n).mean()
    d['ROC20']=d.Close.pct_change(20)
    prev=d.Close.shift(1)
    tr=pd.concat([d.High-d.Low,(d.High-prev).abs(),(d.Low-prev).abs()],axis=1).max(axis=1)
    d['ATR14']=tr.rolling(14,min_periods=14).mean()
    d['cross']=(d.Close>d.MA250)&(d.Close.shift(1)<=d.MA250.shift(1))
    d['above3']=(d.Close>d.MA250).rolling(3).sum().eq(3)
    d['below3']=(d.Close<d.MA250).rolling(3).sum().eq(3)
    d['belowatr3']=(d.Close<d.MA250-.5*d.ATR14).rolling(3).sum().eq(3)
    d['below50_3']=(d.Close<d.MA50).rolling(3).sum().eq(3)
    d['ma50_falling']=d.MA50<d.MA50.shift(5)
    d['defensive_ma50']=d.below50_3 & (d.ROC20<0) & d.ma50_falling
    d['bull50']=d.MA50>d.MA250
    d['stack']=(d.MA30>d.MA50)&d.bull50
    return d


def decision(row,entry,pending):
    if entry=='CROSS':return bool(row.cross)
    if entry=='MA50_AT_CROSS':return bool(row.cross and row.bull50)
    if entry=='ROC20_AT_CROSS':return bool(row.cross and row.ROC20>0)
    if entry=='DELAYED_MA50':return bool(pending and row.above3 and row.bull50)
    if entry=='DELAYED_STACK':return bool(pending and row.above3 and row.stack)
    return False


def simulate(d,start,end,entry,exit_rule,capital=10000.,fee_bps=10,initial_state=None,collect=True):
    """Signal from prior close, fill at next open. Initial state permits seamless walk-forward."""
    fee=fee_bps/10000
    if initial_state is None:state=dict(cash=float(capital),shares=0,entry_date=None,basis=0.,pending=False,crossover=None)
    else:state=dict(initial_state)
    rows=[];trades=[];signals=[];buy_count=0;exits=0;cash_days=0
    idx=np.flatnonzero((d.index>=pd.Timestamp(start))&(d.index<pd.Timestamp(end)))
    for i in idx:
        if i==0:continue
        dt=d.index[i];prior=d.iloc[i-1];r=d.iloc[i];op=float(r.Open);cl=float(r.Close)
        if not np.isfinite(op) or op<=0:continue
        exited=False
        reason=exit_reason(prior,exit_rule)
        if state['shares'] and reason:
            proceeds=state['shares']*op*(1-fee)
            state['cash']+=proceeds
            trades.append([str(state['entry_date'].date()),str(dt.date()),entry,exit_rule,round((proceeds/state['basis']-1)*100,3),round(proceeds-state['basis'],2),reason])
            state.update(shares=0,entry_date=None,basis=0.,pending=False,crossover=None)
            exited=True;exits+=1
        if not state['shares'] and not exited:
            if bool(prior.cross):state['pending']=True;state['crossover']=d.index[i-1]
            if not bool(prior.Close>prior.MA250):state['pending']=False;state['crossover']=None
            if decision(prior,entry,state['pending']):
                qty=int(state['cash']//(op*(1+fee)))
                if qty>0:
                    cost=qty*op*(1+fee)
                    state['cash']-=cost
                    state.update(shares=qty,basis=cost,entry_date=dt,pending=False,crossover=None)
                    buy_count+=1
                    signals.append([str(d.index[i-1].date()),str(dt.date()),entry,exit_rule,round(float(prior.Close/prior.MA250-1)*100,2),bool(prior.bull50),bool(prior.stack),round(float(prior.ROC20)*100,2)])
        value=state['cash']+state['shares']*cl
        cash_days+=int(state['shares']==0)
        if collect:rows.append([str(dt.date()),float(value),int(state['shares']==0)])
        else:rows.append((str(dt.date()),float(value),int(state['shares']==0)))
    if not rows:return None
    values=np.array([r[1] for r in rows]);start_value=capital
    years=max((pd.Timestamp(rows[-1][0])-pd.Timestamp(rows[0][0])).days/365.25,1/252)
    dd=(values/np.maximum.accumulate(np.r_[start_value,values])[1:]-1).min()*100
    cagr=((values[-1]/start_value)**(1/years)-1)*100 if values[-1]>0 else -100
    metrics=dict(cagr=float(cagr),drawdown=float(dd),trades_year=float(exits/years),return_pct=float((values[-1]/start_value-1)*100),buys=buy_count,exits=exits,cash_pct=float(cash_days/len(rows)*100),ending=float(values[-1]),years=float(years))
    return metrics,state,rows,trades,signals


def rank_candidates(items):
    """Percentile ranks across candidates, not raw incomparable metrics."""
    # penalise never trading: cannot earn a high score simply by staying in cash
    c=pd.DataFrame(items)
    c['valid']=(c['buys']>=1)&(c['cagr'].notna())&(c['drawdown'].notna())
    if not c.valid.any():return None,c
    good=c.loc[c.valid].copy()
    good['ret_score']=good.cagr.rank(pct=True,method='average')
    good['risk_score']=good.drawdown.rank(pct=True,method='average') # less negative is better
    good['freq_score']=(-good.trades_year).rank(pct=True,method='average')
    good['score']=.4*good.ret_score+.4*good.risk_score+.2*good.freq_score
    # Deterministic tie breaker: simpler rules first.
    good=good.sort_values(['score','cagr','strategy'],ascending=[False,False,True])
    return good.iloc[0].to_dict(),good


def walkforward(d,ticker,start,end,train_years=5,test_years=1,fee_bps=10):
    """Annual fixed training windows. Independent flat test starts; no training positions leak."""
    # Walk-forward tests use calendar time, enough warmup preceding first eligible start.
    first=max(pd.Timestamp(start)+pd.DateOffset(years=train_years),d.index[250]+pd.DateOffset(years=train_years))
    last=min(pd.Timestamp(end),d.index[-1]+pd.Timedelta(days=1))
    cursor=first
    selections=[];oos=[];trade_rows=[];equity_rows=[];signal_rows=[];train_rows=[]
    while cursor<last:
        te=min(cursor+pd.DateOffset(years=test_years),last)
        tr=cursor-pd.DateOffset(years=train_years)
        candidates=[]
        for entry,exit_rule in STRATEGIES:
            r=simulate(d,tr,cursor,entry,exit_rule,fee_bps=fee_bps,collect=False)
            if r is None:continue
            m=r[0]
            candidates.append(dict(strategy=entry+' / '+exit_rule,entry=entry,exit=exit_rule,**m))
        winner,ranked=rank_candidates(candidates)
        if winner is None:
            selections.append([ticker,str(tr.date()),str(cursor.date()),str(te.date()),'NO SELECTION','',None,None,None,None,None,'No candidate completed a buy in training'])
            cursor=te;continue
        for _,c in ranked.iterrows():train_rows.append([ticker,str(tr.date()),str(cursor.date()),c.entry,c['exit'],round(c.cagr,3),round(c.drawdown,3),round(c.trades_year,3),round(c.score,4),int(c.buys),int(c.exits)])
        ent=winner['entry'];ex=winner['exit']
        # An isolated test portfolio begins in cash at each OOS window. This is deliberately NOT
        # a continuous compounding portfolio; compare test-window returns, not chained equity.
        result=simulate(d,cursor,te,ent,ex,fee_bps=fee_bps)
        if result is None:cursor=te;continue
        m,state,eq,trades,signals=result
        selections.append([ticker,str(tr.date()),str(cursor.date()),str(te.date()),ent,ex,round(winner['score'],4),round(winner['cagr'],2),round(winner['drawdown'],2),round(winner['trades_year'],2),int(winner['buys']),'Research only'])
        oos.append([ticker,str(cursor.date()),str(te.date()),ent,ex,round(m['return_pct'],3),round(m['cagr'],3),round(m['drawdown'],3),round(m['trades_year'],3),int(m['buys']),int(m['exits']),round(m['cash_pct'],2)])
        for x in eq:equity_rows.append([ticker,str(cursor.date()),ent,ex,*x])
        for x in trades:trade_rows.append([ticker,str(cursor.date()),*x])
        for x in signals:signal_rows.append([ticker,str(cursor.date()),*x])
        cursor=te
    return selections,oos,trade_rows,equity_rows,signal_rows,train_rows


def today(d,ticker,winner):
    if len(d)<251:return [ticker,str(d.index[-1].date()) if len(d) else '',None,None,None,None,None,'INSUFFICIENT HISTORY','UNKNOWN','No MA250 signal']
    r=d.iloc[-1];close=float(r.Close);ma=float(r.MA250)
    if not np.isfinite(ma):return [ticker,str(d.index[-1].date()),round(close,2),None,None,None,None,'INSUFFICIENT HISTORY','UNKNOWN','No MA250 signal']
    ent=winner['entry'] if winner else 'NO VALIDATED STRATEGY'
    status='FRESH CROSS' if bool(r.cross) else 'ABOVE MA250' if close>ma else 'BELOW MA250'
    if status=='FRESH CROSS' and ent=='MA50_AT_CROSS' and not r.bull50:status='WAIT MA50'
    if status=='FRESH CROSS' and ent=='ROC20_AT_CROSS' and not r.ROC20>0:status='WAIT ROC20'
    if status=='FRESH CROSS' and ent in ('DELAYED_MA50','DELAYED_STACK'):status='WAIT CONFIRMATION'
    if status=='ABOVE MA250' and ent=='DELAYED_MA50' and r.above3 and r.bull50:status='ALIGNED - CHECK CROSS HISTORY'
    if status=='ABOVE MA250' and ent=='DELAYED_STACK' and r.above3 and r.stack:status='ALIGNED - CHECK CROSS HISTORY'
    return [ticker,str(d.index[-1].date()),round(close,2),round(ma,2),round((close/ma-1)*100,2),round(float(r.MA50),2),round(float(r.ROC20)*100,2),status,ent,'UNKNOWN - HT NOT VERIFIED']


def main():
    p=argparse.ArgumentParser(description='V3.8 walk-forward adaptive MA250 research, no trading')
    p.add_argument('--tickers',default=TICKERS)
    p.add_argument('--start',default='2000-01-03')
    p.add_argument('--end',default='2026-10-12',help='Exclusive end date')
    p.add_argument('--train-years',type=int,default=5)
    p.add_argument('--test-years',type=int,default=1)
    p.add_argument('--fee-bps',type=float,default=10.)
    p.add_argument('--output',default='results_v38')
    a=p.parse_args()
    if a.train_years<2 or a.test_years<1:raise SystemExit('train-years >=2 and test-years >=1 required')
    import yfinance as yf
    from openpyxl import Workbook
    from openpyxl.chart import BarChart,Reference
    from openpyxl.styles import Font,PatternFill,Alignment
    from openpyxl.utils import get_column_letter
    output=Path(a.output);output.mkdir(parents=True,exist_ok=True)
    headers={
        'TodayTrade':['Ticker','Last data date','Close USD','MA250','Distance %','MA50','ROC20 %','Technical detail','Selected entry','HT status','Trade signal'],
        'StrategySelection':['Ticker','Training start','Training end','Test end','Selected entry','Selected exit','Score','Train CAGR %','Train drawdown %','Train exits/year','Train buys','Notes'],
        'OutOfSample':['Ticker','Test start','Test end','Entry','Exit','Test return %','Test CAGR %','Test max drawdown %','Test exits/year','Test buys','Test exits','Cash %'],
        'TrainingScores':['Ticker','Training start','Training end','Entry','Exit','Train CAGR %','Train max drawdown %','Train exits/year','Weighted score','Buys','Exits'],
        'Trades':['Ticker','Test start','Entry date','Exit date','Entry','Exit rule','Trade return %','Trade PnL USD','Exit reason'],
        'Signals':['Ticker','Test start','Signal date','Fill date','Entry','Exit rule','Distance above MA250 %','MA50 bullish','MA30 aligned','ROC20 %'],
        'Equity':['Ticker','Test start','Entry','Exit','Date','Portfolio USD','In cash'],
        'Annual':['Ticker','Test start','Year','Start USD','End USD','Return %'],
        'Errors':['Ticker','Stage','Error'],
        'Guide':['Topic','Explanation']}
    wb=Workbook();wb.remove(wb.active)
    ws={name:wb.create_sheet(name) for name in headers}
    for name,h in headers.items():ws[name].append(h)
    ws['Guide'].append(['Model','Long only, cash when flat; research only; no HT approval or broker orders'])
    ws['Guide'].append(['Weights','CAGR rank 40%; drawdown rank 40%; low exits/year rank 20%'])
    ws['Guide'].append(['Walk forward','Rolling five calendar years training, next one calendar year out-of-sample by default'])
    ws['Guide'].append(['Out-of-sample caveat','Each test window starts with $10,000 cash; windows do NOT compound or carry positions'])
    ws['Guide'].append(['Execution','Signals after close; next session open; 10 bps per side default'])
    ws['Guide'].append(['TodayTrade','Research-only latest-close signals; BUY CANDIDATE is not permission to trade. HT remains unverified'])
    ws['Guide'].append(['Colour legend','BUY CANDIDATE green; WATCH yellow; HOLD grey; EXIT red; AVOID dark red'])
    ws['Guide'].append(['HOLD limitation','HOLD requires position state. This scanner does not know your actual holdings; it does not label positions HOLD'])
    ws['Guide'].append(['Selection caveat','Ranking among 10 candidates on one stock; zero-entry candidates excluded; no minimum significance guarantee'])
    ws['Guide'].append(['Data','Yahoo adjusted OHLC, end date exclusive; dividends adjustment and corporate actions can affect results'])
    for ticker in [t.strip().upper() for t in a.tickers.split(',') if t.strip()]:
        try:
            # Download extra historical warmup; dates before IPO naturally absent.
            begin=(pd.Timestamp(a.start)-pd.DateOffset(years=2)).strftime('%Y-%m-%d')
            raw=yf.download(ticker,start=begin,end=a.end,auto_adjust=True,progress=False,multi_level_index=False)
            if raw is None or raw.empty:raise ValueError('No Yahoo data returned')
            d=prep(raw)
            selections,oos,trades,equity,signals,scores=walkforward(d,ticker,a.start,a.end,a.train_years,a.test_years,a.fee_bps)
            for name,data in [('StrategySelection',selections),('OutOfSample',oos),('Trades',trades),('Equity',equity),('Signals',signals),('TrainingScores',scores)]:
                for row in data:ws[name].append(row)
            if not oos:ws['Errors'].append([ticker,'walk-forward','No complete eligible training/test windows'])
            # Latest selection is trained on data ending at its test start; it is historical,
            # NOT retrained on the latest date. Avoid implying it is a live selected strategy.
            current=None
            if selections:
                last=selections[-1]
                if last[4]!='NO SELECTION':current={'entry':last[4],'exit':last[5]}
            snapshot=today(d,ticker,current)
            detail=snapshot[7]
            ent=current['entry'] if current else None
            r=d.iloc[-1]
            if ent is None or not np.isfinite(float(r.MA250)):
                label='AVOID'
            elif bool(r.below3):
                label='EXIT'
            elif bool(decision(r,ent, bool(r.cross))):
                # Delayed confirmations require a previously recorded pending crossover.
                # Do not infer that state from current alignment alone.
                label='BUY CANDIDATE' if ent not in ('DELAYED_MA50','DELAYED_STACK') else 'WATCH'
            elif float(r.Close)>float(r.MA250):
                label='WATCH'
            else:
                label='AVOID'
            ws['TodayTrade'].append(snapshot+[label])
            df=pd.DataFrame(equity,columns=['Ticker','Test start','Entry','Exit','Date','Portfolio USD','In cash']) if equity else pd.DataFrame()
            if not df.empty:
                df['Year']=pd.to_datetime(df.Date).dt.year
                for (test,year),g in df.groupby(['Test start','Year'],sort=True):
                    startval=10000. if int(year)==pd.Timestamp(test).year else float(df[(df['Test start']==test)&(df['Year']==year-1)]['Portfolio USD'].iloc[-1]) if not df[(df['Test start']==test)&(df['Year']==year-1)].empty else 10000.
                    endval=float(g['Portfolio USD'].iloc[-1]);ws['Annual'].append([ticker,test,int(year),round(startval,2),round(endval,2),round((endval/startval-1)*100,3)])
            print(ticker,':',len(oos),'out-of-sample windows',flush=True)
        except Exception as e:
            ws['Errors'].append([ticker,'download or processing',str(e)]);print(ticker,'ERROR',str(e),flush=True)
    ch=wb.create_sheet('Charts',1);ch.append(['Out-of-sample annual return by test window (first ticker)']);ch.append(['Test start','Return %'])
    outdata=list(ws['OutOfSample'].values)
    if len(outdata)>1:
        first=outdata[1][0]
        for r in outdata[1:]:
            if r[0]==first:ch.append([r[1],r[5]])
        if ch.max_row>2:
            chart=BarChart();chart.title=f'{first} walk-forward test returns';chart.y_axis.title='Return %';chart.add_data(Reference(ch,min_col=2,min_row=2,max_row=ch.max_row),titles_from_data=True);chart.set_categories(Reference(ch,min_col=1,min_row=3,max_row=ch.max_row));chart.width=22;chart.height=12;ch.add_chart(chart,'D3')
    for sh in wb:
        sh.freeze_panes='A2';sh.auto_filter.ref=sh.dimensions
        for c in sh[1]:c.fill=PatternFill('solid',fgColor='17324D');c.font=Font(color='FFFFFF',bold=True);c.alignment=Alignment(wrap_text=True)
        sh.row_dimensions[1].height=29
        for i,h in enumerate(headers.get(sh.title,['Test start','Return %']),1):sh.column_dimensions[get_column_letter(i)].width=min(38,max(15,len(h)+3))
    # Consistent visual status treatment: highlight the ticker and trade-signal cells.
    signal_palette={
        'BUY CANDIDATE':('C6EFCE','006100'),
        'WATCH':('FFF2CC','7F6000'),
        'HOLD':('D9E1E8','404040'),
        'EXIT':('FF9999','9C0006'),
        'AVOID':('8B0000','FFFFFF'),
    }
    today_sheet=ws['TodayTrade']
    for row in today_sheet.iter_rows(min_row=2):
        signal=row[10].value
        if signal in signal_palette:
            bg,fg=signal_palette[signal]
            for cell in (row[0],row[10]):
                cell.fill=PatternFill('solid',fgColor=bg)
                cell.font=Font(color=fg,bold=True)
    today_sheet.column_dimensions['H'].width=35
    today_sheet.column_dimensions['I'].width=27
    today_sheet.column_dimensions['J'].width=27
    today_sheet.column_dimensions['K'].width=23
    file=output/'Adaptive_Trading_Research_V38.xlsx';wb.save(file)
    print('Saved',file,'| RESEARCH ONLY | HT UNKNOWN | NO ORDERS')

if __name__=='__main__':main()
