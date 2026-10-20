"""Read-only XLSX registration; no row deletion, imputation or source edits."""
import argparse, collections, gzip, hashlib, json, math
from datetime import datetime,timedelta
from pathlib import Path
import openpyxl
from .config import ROOT,DATA
from .store import Store,now
from .engine import KST,overlap_minutes
START=datetime(2025,1,1,tzinfo=KST); END=datetime(2026,1,1,tzinfo=KST)
def parse_date(v):
    if isinstance(v,datetime): return v.replace(tzinfo=KST)
    return datetime.fromisoformat(str(v)).replace(tzinfo=KST)
def inspect(path,store):
    digest=hashlib.sha256(path.read_bytes()).hexdigest(); book=openpyxl.load_workbook(path,read_only=True,data_only=True)
    session='시간별' in path.name; reports=[]; demands=collections.defaultdict(lambda:dict(annual_kwh=0.,monthly_kwh=[0.]*12,months=set(),row_count=0))
    sensitivity={'original_fast_kwh':0.,'distinct_row_fast_kwh':0.}; sensitivity_seen=set()
    sessions=collections.defaultdict(list); records=[]; counts=collections.Counter(); dates=[]; names=set(); fast=set(); hourly=[[0.]*24 for _ in range(7)]
    for sheet in book:
        header=None; seen=collections.Counter(); flags=collections.Counter(); row_count=0; zeros=0; negative=0; missing=0; start_dates=[]; end_dates=[]
        for rownum,row in enumerate(sheet.values,1):
            if header is None:
                if '충전소명' in row and ('충전시작시간' in row or '날짜' in row): header=list(row); header_row=rownum
                continue
            if all(v is None for v in row): continue
            raw=dict(zip(header,row)); row_count+=1; seen[tuple(str(v) for v in row)]+=1
            issue=[]
            if any(v is None or v=='' for v in row): missing+=1; issue.append('missing')
            name=raw.get('충전소명'); names.add(name)
            try:
                value=float(row[-1])
                if not math.isfinite(value): raise ValueError()
                if value<0: negative+=1; issue.append('negative_energy')
                if value==0: zeros+=1
            except (TypeError,ValueError): value=None; issue.append('invalid_energy')
            try:
                if session:
                    a=parse_date(raw['충전시작시간']); b=parse_date(raw['충전종료시간']); start_dates.append(a.isoformat()); end_dates.append(b.isoformat())
                    if b<=a: issue.append('nonpositive_session')
                    if b-a>timedelta(hours=24): issue.append('session_over_24h')
                    if not issue:
                        sessions[name].append([a.isoformat(),b.isoformat(),rownum,digest,sheet.title])
                        x=max(a,START); stop=min(b,END)
                        while x<stop:
                            y=min(stop,x.replace(minute=0,second=0,microsecond=0)+timedelta(hours=1))
                            hourly[x.weekday()][x.hour]+=(y-x).total_seconds()/60; x=y
                else:
                    d=parse_date(raw['날짜']); dates.append(d.isoformat()); typ=raw['충전기 유형']
                    if typ=='급속':
                        fast.add(name)
                        if value is not None and value>=0 and START<=d<END:
                            sensitivity['original_fast_kwh']+=value
                            signature=tuple(str(v) for v in row)
                            if signature not in sensitivity_seen: sensitivity['distinct_row_fast_kwh']+=value
                            sensitivity_seen.add(signature)
                            agg=demands[name]; agg['annual_kwh']+=value; agg['monthly_kwh'][d.month-1]+=value; agg['months'].add(d.month); agg['row_count']+=1
            except (ValueError,TypeError,KeyError): issue.append('date_parse_error')
            flags.update(issue)
            records.append(dict(sheet=sheet.title,row=rownum,values=list(row),quality_flags=issue))
        reports.append(dict(sheet=sheet.title,header=header,header_row=locals().get('header_row'),rows=row_count,missing_rows=missing,negative_rows=negative,zero_rows=zeros,duplicate_excess_rows=sum(n-1 for n in seen.values()),duplicate_group_rows=sum(n for n in seen.values() if n>1),quality_flags=dict(flags),start_min=min(start_dates) if start_dates else None,start_max=max(start_dates) if start_dates else None,end_max=max(end_dates) if end_dates else None))
    book.close()
    raw_dir=ROOT/'data'/'raw'; raw_dir.mkdir(parents=True,exist_ok=True)
    with gzip.open(raw_dir/f'{digest}.json.gz','wt',encoding='utf-8') as f: json.dump(records,f,ensure_ascii=False,default=str)
    asset=dict(file=path.name,sha256=digest,registered_at=now(),type='sessions' if session else 'demand',sheets=reports,unique_station_names=len(names),fast_station_names=len(fast) if not session else None,date_min=min(dates) if dates else None,date_max=max(dates) if dates else None,unit_warning='원본 충전량(kW) 표기: 에너지 단위 확인 필요' if session else None,duplicate_sensitivity=sensitivity if not session else None,cleaning_version='quality-v0.1',analysis_period=['2025-01-01','2025-12-31'])
    store.put('assets',asset,digest)
    if not session:
        out={k:dict(v,months=sorted(v['months']),sha256=digest) for k,v in demands.items()}
        (DATA/'demand.json').write_text(json.dumps(out,ensure_ascii=False),encoding='utf-8')
    else:
        with gzip.open(DATA/'sessions.json.gz','wt',encoding='utf-8') as f: json.dump(sessions,f,ensure_ascii=False)
        (DATA/'hourly.json').write_text(json.dumps(dict(values=hourly,unit='세션·분',coverage_verified=False,period=asset['analysis_period'])),encoding='utf-8')
    return asset

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('files',nargs='*'); args=parser.parse_args(); store=Store()
    paths=[Path(p) for p in args.files] if args.files else sorted(ROOT.glob('*.xlsx'))
    reports=[inspect(p,store) for p in paths]
    directory=ROOT/'reports'; directory.mkdir(exist_ok=True)
    (directory/'source-quality.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 원자료 품질 검사','',f'검사시각: {now()}','원본은 변경하지 않았으며 동일 행을 모두 보존했습니다.','']
    for a in reports:
        lines += [f"## {a['file']}",f"SHA-256: `{a['sha256']}`",f"고유 시설명: {a['unique_station_names']} / 급속 시설명: {a['fast_station_names']}"]
        for s in a['sheets']: lines += [f"- {s['rows']:,}행, 결측 {s['missing_rows']}행, 음수 {s['negative_rows']}행, 0값 {s['zero_rows']}행",f"- 동일 행: 초과 {s['duplicate_excess_rows']}행 / 그룹 전체 {s['duplicate_group_rows']}행",f"- 품질 플래그: {s['quality_flags']}",f"- 세션 시작 {s['start_min']} ~ {s['start_max']}, 최종 종료 {s['end_max']}"]
        if a['duplicate_sensitivity']: lines.append('동일 행 민감도(급속 kWh): '+str(a['duplicate_sensitivity'])+' · 원본 유지 결과가 기본값')
        if a['unit_warning']: lines.append(a['unit_warning'])
        lines.append('')
    lines += ['## 분석 제한','정비 기준기간은 첨부 시간별 파일에 맞춰 2025년입니다. 2026년 종료 세션은 2025년과 겹치는 구간만 반영합니다.','급속 전용 이력과 일별 커버리지 근거가 없으므로 자동 정비 추천을 보류합니다.','실제 주소·설비 매칭 전까지 충전실적을 API 시설에 자동 연결하지 않습니다.']
    (directory/'source-quality.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps([dict(file=a['file'],rows=sum(s['rows'] for s in a['sheets']),names=a['unique_station_names']) for a in reports],ensure_ascii=False))
if __name__=='__main__': main()
