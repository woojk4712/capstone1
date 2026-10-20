"""Prepare actual local D1 and candidate links; never calls external APIs."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.app.research import ResearchService as AnalysisService
from backend.app.core import ExternalService

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--confirm-name');parser.add_argument('--stat-id');parser.add_argument('--evidence')
    parser.add_argument('--all',action='store_true',help='Prepare actual D1, official bridge and D2, without external API requests')
    args=parser.parse_args()
    service=AnalysisService(ExternalService())
    if args.confirm_name:
        if not args.stat_id or not args.evidence:parser.error('--stat-id and --evidence are required for manual confirmation')
        service.review(args.confirm_name,args.stat_id,'confirm',args.evidence)
    else:
        print(json.dumps(service.prepare_all(),ensure_ascii=False))
    result=service.stations()
    print(json.dumps({key:result[key] for key in ('total','d1Available','stationMatchingReady','classificationVerified')},ensure_ascii=False))
