#!/usr/bin/env python3
import argparse
import json
import math
from pathlib import Path

TARGET = "READ_PENDING_RESULTS"
C1_ID = "orchestration-results-consumed-v1"
C2_ID = "orchestration-results-consumed-delex-v1"


def load_rows(path):
    rows=[json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    by_id={row['id']:row for row in rows}
    if set(by_id) != {C1_ID, C2_ID}:
        raise ValueError(f"unexpected row ids: {sorted(by_id)}")
    return by_id


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
    ap.add_argument('--repository-sha', required=True)
    ap.add_argument('--out', required=True)
    args=ap.parse_args()

    rows=load_rows(args.raw)
    c1=metrics(rows[C1_ID]); c2=metrics(rows[C2_ID])
    if c1['model'] != c2['model']:
        raise ValueError('model identity differs across pair')
    if set(c1['probabilities']) != set(c2['probabilities']):
        raise ValueError('option identity differs across pair')

    keys=sorted(c1['probabilities'])
    l1=c1['option_logits'][TARGET]; l2=c2['option_logits'][TARGET]
    p1=c1['probabilities'][TARGET]; p2=c2['probabilities'][TARGET]
    tv=0.5*math.fsum(abs(c1['probabilities'][k]-c2['probabilities'][k]) for k in keys)

    receipt={
      'schema':'theseus.semif-4b-lexical-overlap.v1',
      'claim_scope':'STANDALONE_LEXICAL_OVERLAP_PROBE_ONLY',
      'repository_sha':args.repository_sha,
      'c1_id':C1_ID,
      'c2_id':C2_ID,
      'target':TARGET,
      'primary_expectation':f'logit_C2({TARGET}) < logit_C1({TARGET})',
      'raw_logit_direction_pass':l2 < l1,
      'target_logit':{'c1':l1,'c2':l2,'delta':l2-l1},
      'target_probability':{'c1':p1,'c2':p2,'delta':p2-p1},
      'total_variation':tv,
      'c1':c1,
      'c2':c2,
      'acceptance_authority':False,
      'permission_authority':False,
      'verification_authority':False,
      'promotion_authority':False,
    }
    Path(args.out).write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")
    print(json.dumps({
      'raw_logit_direction_pass':receipt['raw_logit_direction_pass'],
      'target_logit':receipt['target_logit'],
      'target_probability':receipt['target_probability'],
      'total_variation':receipt['total_variation'],
    },sort_keys=True))

if __name__=='__main__':
    main()
