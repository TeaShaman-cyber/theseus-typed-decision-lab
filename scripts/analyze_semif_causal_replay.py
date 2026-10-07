#!/usr/bin/env python3
import argparse
import json
import math
from pathlib import Path

TARGET = "READ_PENDING_RESULTS"
BASE_ID = "orchestration-pending-results-v1"
CAUSAL_ID = "orchestration-results-consumed-v1"


def load_json(path):
    return json.loads(Path(path).read_text())


def load_rows(path):
    rows=[json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    by_id={row['id']:row for row in rows}
    if set(by_id) != {BASE_ID, CAUSAL_ID}:
        raise ValueError(f"unexpected row ids: {sorted(by_id)}")
    return by_id


def parse_timing(path):
    result={}
    for line in Path(path).read_text().splitlines():
        if 'Maximum resident set size (kbytes):' in line:
            result['max_rss_kib']=int(line.rsplit(':',1)[1].strip())
        elif 'Elapsed (wall clock) time' in line:
            result['elapsed_wall']=line.split('):',1)[1].strip()
    if 'max_rss_kib' not in result:
        raise ValueError('GNU time max RSS missing')
    return result


def metrics(row):
    ids=row['option_ids']
    probs=[float(x) for x in row['probabilities']]
    logits=[float(x) for x in row['option_logits']]
    if not (len(ids)==len(probs)==len(logits)) or TARGET not in ids:
        raise ValueError('invalid option/logit layout')
    return {
        'probabilities':dict(zip(ids,probs)),
        'option_logits':dict(zip(ids,logits)),
        'prompt_sha256':row['prompt_sha256'],
        'input_tokens':row['input_tokens'],
        'model':row['model'],
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--raw', required=True)
    ap.add_argument('--timing', required=True)
    ap.add_argument('--model-meta', required=True)
    ap.add_argument('--runner-meta', required=True)
    ap.add_argument('--repository-sha', required=True)
    ap.add_argument('--out', required=True)
    args=ap.parse_args()

    rows=load_rows(args.raw)
    base=metrics(rows[BASE_ID]); causal=metrics(rows[CAUSAL_ID])
    if base['model'] != causal['model']:
        raise ValueError('model identity differs across pair')
    if set(base['probabilities']) != set(causal['probabilities']):
        raise ValueError('option identity differs across pair')
    p0=base['probabilities'][TARGET]; p1=causal['probabilities'][TARGET]
    keys=sorted(base['probabilities'])
    tv=0.5*math.fsum(abs(base['probabilities'][k]-causal['probabilities'][k]) for k in keys)
    receipt={
      'schema':'theseus.semif-4b-causal-replay.v1',
      'claim_scope':'STANDALONE_CAUSAL_REPLAY_ONLY',
      'repository_sha':args.repository_sha,
      'baseline_id':BASE_ID,
      'causal_id':CAUSAL_ID,
      'target':TARGET,
      'directional_expectation':f'P_causal({TARGET}) < P_baseline({TARGET})',
      'directional_pass':p1 < p0,
      'target_probability':{'baseline':p0,'causal':p1,'delta':p1-p0},
      'target_logit':{
        'baseline':base['option_logits'][TARGET],
        'causal':causal['option_logits'][TARGET],
        'delta':causal['option_logits'][TARGET]-base['option_logits'][TARGET],
      },
      'total_variation':tv,
      'baseline':base,
      'causal':causal,
      'timing':parse_timing(args.timing),
      'model_artifact':load_json(args.model_meta),
      'runner':load_json(args.runner_meta),
      'acceptance_authority':False,
      'permission_authority':False,
      'verification_authority':False,
      'promotion_authority':False,
    }
    Path(args.out).write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")
    print(json.dumps({
      'directional_pass':receipt['directional_pass'],
      'target_probability':receipt['target_probability'],
      'target_logit':receipt['target_logit'],
      'total_variation':receipt['total_variation'],
      'max_rss_kib':receipt['timing']['max_rss_kib'],
    },sort_keys=True))

if __name__=='__main__':
    main()
