"""Fail-closed evidence policy; validates supplied evidence, not its truth.

Only trusted collectors/reviewed source evidence should build the case. This is
not a probabilistic model, profitability claim, order or broker integration.
All sessions are ISO Gregorian dates. Three calendar days is a conservative
freshness cap, NOT an Iranian trading calendar; longer holidays stay unknown.
"""
from datetime import date
import math

REQUIRED=('identity','tradable','liquidity','trend','demand','fundamentals',
          'market','sector','disclosures','entry')


def evaluate(case, *, as_of):
    unknown=[];negative=[]
    result={'symbol':case.get('symbol'), 'verdict':'unknown','blockers':unknown,
            'failed_checks':negative, 'reward_risk':None, 'order_authorized':False}
    try:
        now=date.fromisoformat(as_of)
        ref=date.fromisoformat(case.get('reference_session',''))
        if not 0 <= (now-ref).days <= 3:unknown.append('reference_not_recent')
        for key in ['quote_session','history_session','flow_session']:
            if date.fromisoformat(case.get(key,'')) != ref:unknown.append(key+'_mismatch')
    except (ValueError, TypeError):
        unknown.append('invalid_session_dates');ref=None
    if case.get('reference_verified') is not True or not case.get('session_source'):
        unknown.append('reference_unverified')
    if case.get('completed_session') is not True:unknown.append('partial_or_unknown_session')
    checks=case.get('checks',{})
    if not isinstance(checks,dict):checks={}
    for key in REQUIRED:
        check=checks.get(key,{})
        if not isinstance(check,dict) or type(check.get('passed')) is not bool or not check.get('source'):
            unknown.append(key+'_missing_evidence');continue
        try:
            day=date.fromisoformat(check.get('as_of',''))
            if ref is None or day > ref:raise ValueError('future')
            # as_of is verification date, not the fiscal period end date.
            if day != ref:raise ValueError('stale verification')
        except (ValueError,TypeError):
            unknown.append(key+'_invalid_evidence_date');continue
        if check['passed'] is False:negative.append(key)
    values=[case.get(k) for k in ['entry','stop','target','cost']]
    if (not all(type(v) in (int,float) and math.isfinite(v) for v in values)
        or not case.get('cost_basis') or not case.get('levels_source')):
        unknown.append('risk_plan_unverified')
    else:
        entry,stop,target,cost=values
        if not target>entry>stop>0 or cost<0:
            unknown.append('invalid_risk_plan')
        else:
            rr=(target-entry-cost)/(entry-stop+cost)
            result['reward_risk']=rr
            if rr<2:negative.append('reward_risk_below_2')
    if not unknown:result['verdict']='wait' if negative else 'buy_candidate'
    return result
