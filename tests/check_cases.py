#!/usr/bin/env python3
"""Own tests for Assignment 3 (semantic checking of non-unique answers).

Run from the repository root:

    python tests/check_cases.py                 # all checks
    python tests/check_cases.py --write-files   # also (re)write my_cases.jsonl,
                                                # expected_outputs.jsonl, actual_outputs.jsonl

The program under test is started through tools/run.py (same build, same
JSON-lines interface). Expected answers come from hand calculation (see
tests/CASES.md) and from independent brute-force oracles written in this file.
Non-unique answers are checked by properties, never by exact equality.
"""
import argparse
import itertools
import json
import pathlib
import random
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import run as launcher  # noqa: E402  (tools/run.py: build())

HERE = pathlib.Path(__file__).resolve().parent


# ----------------------------------------------------------------------------
# Independent oracles (deliberately naive, different from the Java code)
# ----------------------------------------------------------------------------

def oracle_dsu(n, ops):
    label = list(range(n))
    states = []
    for u, v in ops:
        a, b = label[u], label[v]
        if a != b:
            label = [a if x == b else x for x in label]
        counts = {}
        for x in label:
            counts[x] = counts.get(x, 0) + 1
        states.append([len(counts), max(counts.values()) if counts else 0])
    return states


def oracle_mst(n, edges):
    """Naive relabelling Kruskal: returns (cost, components)."""
    label = list(range(n))
    cost = 0
    for u, v, w in sorted(edges, key=lambda e: e[2]):
        a, b = label[u], label[v]
        if a != b:
            label = [a if x == b else x for x in label]
            cost += w
    return cost, len(set(label))


def reach_closure(n, edges):
    """reach[i] = bitmask of vertices reachable from i by >= 1 edge."""
    reach = [0] * n
    for u, v in edges:
        reach[u] |= 1 << v
    for k in range(n):
        for i in range(n):
            if reach[i] >> k & 1:
                reach[i] |= reach[k]
    return reach


def oracle_scc(n, edges):
    reach = reach_closure(n, edges)
    return [[(i == j) or (reach[i] >> j & 1 and reach[j] >> i & 1) for j in range(n)] for i in range(n)]


def oracle_cyclic(n, edges):
    reach = reach_closure(n, edges)
    return any(reach[i] >> i & 1 for i in range(n))


def oracle_dag(n, edges, source):
    """Bellman-Ford (valid on DAGs): list of distances, None = unreachable."""
    dist = [None] * n
    dist[source] = 0
    for _ in range(n):
        changed = False
        for u, v, w in edges:
            if dist[u] is not None and (dist[v] is None or dist[u] + w < dist[v]):
                dist[v] = dist[u] + w
                changed = True
        if not changed:
            break
    return dist


class Dsu:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a == b:
            return False
        self.p[a] = b
        return True


# ----------------------------------------------------------------------------
# Semantic validators: return None if the answer is valid, else a reason string
# ----------------------------------------------------------------------------

def is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)


def check_dsu(req, ans, states=None):
    expected = states if states is not None else oracle_dsu(req['n'], req['operations'])
    return None if ans.get('states') == expected else 'states differ from oracle'


def check_forest(req, ans, optimum=None):
    n, edges = req['n'], req['edges']
    cost_opt, comps_opt = optimum if optimum else oracle_mst(n, edges)
    ids = ans.get('edge_ids')
    if not isinstance(ids, list) or not all(is_int(i) and 0 <= i < len(edges) for i in ids):
        return 'edge_ids malformed'
    if len(set(ids)) != len(ids):
        return 'repeated edge id'
    d = Dsu(n)
    total = 0
    for i in ids:
        u, v, w = edges[i]
        if u == v:
            return 'self-loop selected'
        if not d.union(u, v):
            return 'selected edges contain a cycle'
        total += w
    if ans.get('components') != comps_opt:
        return 'wrong component count'
    if len(ids) != n - comps_opt:
        return 'not a spanning forest (wrong edge count)'
    if ans.get('cost') != total:
        return 'cost is not the sum of selected edges'
    if total != cost_opt:
        return 'forest is feasible but not optimal'
    return None


def check_scc(req, ans, same=None):
    n, edges = req['n'], req['edges']
    comp, cond = ans.get('component'), ans.get('condensation')
    if not isinstance(comp, list) or len(comp) != n or not all(is_int(c) and c >= 0 for c in comp):
        return 'component malformed'
    if same is None:
        same = oracle_scc(n, edges)
    for i in range(n):
        for j in range(n):
            if (comp[i] == comp[j]) != bool(same[i][j]):
                return f'vertices {i},{j} wrongly grouped'
    want = {(comp[u], comp[v]) for u, v in edges if comp[u] != comp[v]}
    if not isinstance(cond, list) or not all(isinstance(p, list) and len(p) == 2 for p in cond):
        return 'condensation malformed'
    got = [tuple(p) for p in cond]
    if len(set(got)) != len(got):
        return 'duplicate condensation pair'
    if set(got) != want:
        return 'condensation differs from the exact set of cross-component pairs'
    return None


def check_topo(req, ans, cyclic=None):
    n, edges = req['n'], req['edges']
    if cyclic is None:
        cyclic = oracle_cyclic(n, edges)
    if cyclic:
        return None if ans.get('acyclic') is False and ans.get('order') == [] else 'cycle not reported'
    order = ans.get('order')
    if ans.get('acyclic') is not True:
        return 'acyclic graph reported as cyclic'
    if not isinstance(order, list) or sorted(order) != list(range(n)):
        return 'order is not a permutation of all vertices'
    pos = {v: i for i, v in enumerate(order)}
    for u, v in edges:
        if pos[u] >= pos[v]:
            return f'edge {u}->{v} goes backwards'
    return None


def check_dag(req, ans, dist=None, cyclic=None):
    n, edges, s = req['n'], req['edges'], req['source']
    plain = [(u, v) for u, v, _ in edges]
    if cyclic is None:
        cyclic = oracle_cyclic(n, plain)
    if cyclic:
        ok = ans.get('acyclic') is False and ans.get('distance') == [] and ans.get('parent_edge') == []
        return None if ok else 'cycle not reported correctly'
    if ans.get('acyclic') is not True:
        return 'acyclic graph reported as cyclic'
    if dist is None:
        dist = oracle_dag(n, edges, s)
    if ans.get('distance') != dist:
        return 'distances differ from Bellman-Ford oracle'
    par = ans.get('parent_edge')
    if not isinstance(par, list) or len(par) != n:
        return 'parent_edge malformed'
    for v in range(n):
        if v == s or dist[v] is None:
            if par[v] != -1:
                return f'vertex {v} must have parent_edge -1'
            continue
        e = par[v]
        if not is_int(e) or not 0 <= e < len(edges) or edges[e][1] != v:
            return f'parent edge of {v} does not end at {v}'
        if dist[edges[e][0]] is None or dist[edges[e][0]] + edges[e][2] != dist[v]:
            return f'parent edge of {v} is not on a shortest path'
    # Following parent edges must reach the source (linear time, memoised).
    state = [0] * n  # 0 unknown, 1 on current walk, 2 reaches the source
    state[s] = 2
    for v in range(n):
        if dist[v] is None:
            continue  # unreachable vertices have no route to check
        walk, x = [], v
        while state[x] == 0:
            state[x] = 1
            walk.append(x)
            x = edges[par[x]][0]
        if state[x] != 2:
            return f'parent chain of {v} does not reach the source'
        for y in walk:
            state[y] = 2
    return None


VALIDATORS = {'dsu': check_dsu, 'kruskal': check_forest, 'prim': check_forest,
              'scc': check_scc, 'topo': check_topo, 'dag': check_dag}


def validate(req, ans):
    return VALIDATORS[req['task']](req, ans)


# ----------------------------------------------------------------------------
# Running the program under test
# ----------------------------------------------------------------------------

_COMMAND = None


def command():
    global _COMMAND
    if _COMMAND is None:
        _COMMAND = launcher.build('Java')
    return _COMMAND


def run_program(requests, timeout=180):
    data = ''.join(json.dumps(r, separators=(',', ':')) + '\n' for r in requests)
    res = subprocess.run(command(), input=data, capture_output=True, text=True,
                         encoding='utf-8', timeout=timeout)
    if res.returncode:
        raise RuntimeError(f'program exited with {res.returncode}: {res.stderr[:2000]}')
    lines = res.stdout.splitlines()
    if len(lines) != len(requests):
        raise RuntimeError(f'expected {len(requests)} lines, got {len(lines)}')
    out = [json.loads(line) for line in lines]
    for a in out:
        if 'error' in a:
            raise RuntimeError(f'program reported: {a["error"]}')
    return out


# ----------------------------------------------------------------------------
# Hand-made cases. `expect` lists only fields that are unique by the contract.
# Justifications are in tests/CASES.md (same names).
# ----------------------------------------------------------------------------

def canon_scc(comp, cond):
    """Relabel SCCs by first appearance so labels can be compared exactly."""
    relabel = {}
    out = []
    for c in comp:
        out.append(relabel.setdefault(c, len(relabel)))
    pairs = sorted({(relabel[a], relabel[b]) for a, b in cond})
    return out, [list(p) for p in pairs]


HAND = [
    ('dsu_repeat_and_self', {'task': 'dsu', 'n': 4, 'operations': [[0, 1], [1, 2], [0, 2], [3, 3]]},
     {'states': [[3, 2], [2, 3], [2, 3], [2, 3]]}),
    ('dsu_empty_graph', {'task': 'dsu', 'n': 0, 'operations': []}, {'states': []}),
    ('dsu_no_operations', {'task': 'dsu', 'n': 3, 'operations': []}, {'states': []}),
    ('dsu_chain_merges', {'task': 'dsu', 'n': 5, 'operations': [[0, 1], [2, 3], [1, 2], [4, 4], [3, 4]]},
     {'states': [[4, 2], [3, 2], [2, 4], [2, 4], [1, 5]]}),
    ('kruskal_disconnected_isolate', {'task': 'kruskal', 'n': 4, 'edges': [[0, 1, 4], [1, 2, 2], [0, 2, 3]]},
     {'cost': 5, 'components': 2}),
    ('kruskal_negative_loop_parallel',
     {'task': 'kruskal', 'n': 3, 'edges': [[0, 0, -9], [0, 1, 5], [0, 1, -2], [1, 2, 0], [1, 2, 7]]},
     {'cost': -2, 'components': 1}),
    ('kruskal_total_beyond_32_bit',
     {'task': 'kruskal', 'n': 4, 'edges': [[0, 1, 1000000000], [1, 2, 1000000000], [2, 3, 1000000000]]},
     {'cost': 3000000000, 'components': 1}),
    ('kruskal_empty', {'task': 'kruskal', 'n': 0, 'edges': []}, {'cost': 0, 'components': 0}),
    ('prim_disconnected_isolate', {'task': 'prim', 'n': 4, 'edges': [[0, 1, 4], [1, 2, 2], [0, 2, 3]]},
     {'cost': 5, 'components': 2}),
    ('prim_two_components_restart',
     {'task': 'prim', 'n': 6, 'edges': [[0, 1, 1], [1, 2, 1], [3, 4, -5], [4, 5, 2], [3, 5, 2]]},
     {'cost': -1, 'components': 2}),
    ('prim_total_beyond_32_bit',
     {'task': 'prim', 'n': 3, 'edges': [[0, 1, -1000000000], [1, 2, -1000000000], [0, 2, -1000000000]]},
     {'cost': -2000000000, 'components': 1}),
    ('prim_ties_everywhere', {'task': 'prim', 'n': 4, 'edges': [[0, 1, 1], [1, 2, 1], [2, 3, 1], [3, 0, 1], [0, 2, 1]]},
     {'cost': 3, 'components': 1}),
    ('scc_two_cycle_plus_tail', {'task': 'scc', 'n': 4, 'edges': [[0, 1], [1, 0], [1, 2], [0, 2], [2, 3]]},
     {'component': [0, 0, 1, 2], 'condensation': [[0, 1], [1, 2]]}),
    ('scc_isolated_and_loop', {'task': 'scc', 'n': 3, 'edges': [[1, 1], [1, 1]]},
     {'component': [0, 1, 2], 'condensation': []}),
    ('scc_duplicate_cross_edges', {'task': 'scc', 'n': 4, 'edges': [[0, 1], [0, 1], [1, 0], [1, 2], [1, 2], [3, 2], [2, 3]]},
     {'component': [0, 0, 1, 1], 'condensation': [[0, 1]]}),
    ('scc_empty', {'task': 'scc', 'n': 0, 'edges': []}, {'component': [], 'condensation': []}),
    ('topo_simple', {'task': 'topo', 'n': 4, 'edges': [[0, 2], [1, 2], [2, 3]]}, {'acyclic': True}),
    ('topo_diamond_duplicates', {'task': 'topo', 'n': 4, 'edges': [[0, 1], [0, 2], [1, 3], [2, 3], [0, 3], [0, 3]]},
     {'acyclic': True}),
    ('topo_self_loop', {'task': 'topo', 'n': 2, 'edges': [[1, 1]]}, {'acyclic': False}),
    ('topo_cycle_in_second_component', {'task': 'topo', 'n': 5, 'edges': [[0, 1], [2, 3], [3, 4], [4, 2]]},
     {'acyclic': False}),
    ('topo_empty', {'task': 'topo', 'n': 0, 'edges': []}, {'acyclic': True}),
    ('dag_spec_example', {'task': 'dag', 'n': 5, 'source': 0, 'edges': [[0, 1, 3], [0, 2, 8], [1, 2, -7], [2, 3, 4]]},
     {'acyclic': True, 'distance': [0, 3, -4, 0, None]}),
    ('dag_negative_one_is_a_distance', {'task': 'dag', 'n': 3, 'source': 0, 'edges': [[0, 1, -1]]},
     {'acyclic': True, 'distance': [0, -1, None]}),
    ('dag_tied_and_parallel', {'task': 'dag', 'n': 4, 'source': 0,
                               'edges': [[0, 1, 5], [0, 1, 5], [1, 3, 1], [0, 2, 2], [2, 3, 4]]},
     {'acyclic': True, 'distance': [0, 5, 2, 6]}),
    ('dag_cycle_unreachable_from_source', {'task': 'dag', 'n': 4, 'source': 0, 'edges': [[0, 1, 1], [2, 3, 1], [3, 2, 1]]},
     {'acyclic': False, 'distance': [], 'parent_edge': []}),
    ('dag_self_loop', {'task': 'dag', 'n': 1, 'source': 0, 'edges': [[0, 0, 5]]},
     {'acyclic': False, 'distance': [], 'parent_edge': []}),
    ('dag_total_beyond_32_bit', {'task': 'dag', 'n': 4, 'source': 0,
                                 'edges': [[0, 1, 1000000000], [1, 2, 1000000000], [2, 3, 1000000000]]},
     {'acyclic': True, 'distance': [0, 1000000000, 2000000000, 3000000000]}),
    ('dag_singleton', {'task': 'dag', 'n': 1, 'source': 0, 'edges': []},
     {'acyclic': True, 'distance': [0], 'parent_edge': [-1]}),
]


def matches_expectation(req, ans, expect):
    """Compare only the fields that are unique by the contract."""
    t = req['task']
    if t == 'scc':
        return canon_scc(ans['component'], ans['condensation']) == canon_scc(expect['component'], expect['condensation'])
    if t in ('kruskal', 'prim'):
        return ans['cost'] == expect['cost'] and ans['components'] == expect['components']
    if t == 'topo':
        return ans['acyclic'] == expect['acyclic']
    return all(ans.get(k) == v for k, v in expect.items())


# ----------------------------------------------------------------------------
# Test groups
# ----------------------------------------------------------------------------

FAILURES = []


def report(name, problem):
    if problem:
        FAILURES.append(f'{name}: {problem}')
        print(f'FAIL {name}: {problem}')
    else:
        print(f'PASS {name}')


def test_validators_self_check():
    """The checker must accept alternative valid answers and reject invalid witnesses."""
    kr = {'task': 'kruskal', 'n': 4, 'edges': [[0, 1, 4], [1, 2, 2], [0, 2, 3]]}
    report('validator accepts edge ids in another order',
           check_forest(kr, {'cost': 5, 'edge_ids': [2, 1], 'components': 2}))
    kt = {'task': 'kruskal', 'n': 3, 'edges': [[0, 1, 1], [1, 2, 1], [0, 2, 1]]}
    report('validator accepts a different optimal forest',
           check_forest(kt, {'cost': 2, 'edge_ids': [0, 2], 'components': 1}))
    bad = check_forest(kt, {'cost': 3, 'edge_ids': [0, 1, 2], 'components': 1})
    report('validator rejects a forest with a cycle', None if bad else 'accepted an invalid forest')
    bad = check_forest(kr, {'cost': 7, 'edge_ids': [0, 1], 'components': 2})
    report('validator rejects a feasible but non-optimal forest', None if bad else 'accepted non-optimal forest')

    sc = {'task': 'scc', 'n': 4, 'edges': [[0, 1], [1, 0], [1, 2], [0, 2], [2, 3]]}
    report('validator accepts permuted scc labels',
           check_scc(sc, {'component': [9, 9, 4, 1], 'condensation': [[4, 1], [9, 4]]}))
    bad = check_scc(sc, {'component': [9, 9, 4, 1], 'condensation': [[9, 4], [9, 4], [4, 1]]})
    report('validator rejects a duplicate condensation pair', None if bad else 'accepted duplicates')
    bad = check_scc(sc, {'component': [9, 9, 4, 1], 'condensation': [[9, 4]]})
    report('validator rejects a missing condensation pair', None if bad else 'accepted missing pair')
    bad = check_scc(sc, {'component': [0, 1, 2, 3], 'condensation': []})
    report('validator rejects a wrong partition', None if bad else 'accepted wrong partition')

    tp = {'task': 'topo', 'n': 4, 'edges': [[0, 2], [1, 2], [2, 3]]}
    report('validator accepts either valid topological order',
           check_topo(tp, {'acyclic': True, 'order': [1, 0, 2, 3]}) or
           check_topo(tp, {'acyclic': True, 'order': [0, 1, 2, 3]}))
    bad = check_topo(tp, {'acyclic': True, 'order': [2, 0, 1, 3]})
    report('validator rejects an order with a backward edge', None if bad else 'accepted bad order')

    dg = {'task': 'dag', 'n': 4, 'source': 0, 'edges': [[0, 1, 5], [0, 1, 5], [1, 3, 1], [0, 2, 2], [2, 3, 4]]}
    for e in (0, 1):
        report(f'validator accepts tied parallel parent edge {e}',
               check_dag(dg, {'acyclic': True, 'distance': [0, 5, 2, 6], 'parent_edge': [-1, e, 3, 2]}))
    bad = check_dag(dg, {'acyclic': True, 'distance': [0, 5, 2, 6], 'parent_edge': [-1, 0, 3, 4]})
    report('validator accepts the other tied route to vertex 3',
           bad)  # edge 4 = 2->3 is also on a shortest path (2 + 4 = 6)
    bad = check_dag(dg, {'acyclic': True, 'distance': [0, 5, 2, 6], 'parent_edge': [-1, 3, 3, 2]})
    report('validator rejects a parent edge that does not end at the vertex', None if bad else 'accepted bad parent')
    bad = check_dag(dg, {'acyclic': True, 'distance': [0, 5, 2, 7], 'parent_edge': [-1, 0, 3, 2]})
    report('validator rejects a wrong distance', None if bad else 'accepted wrong distance')


def test_hand_cases(write_files):
    requests = [r for _, r, _ in HAND]
    answers = run_program(requests)
    for (name, req, expect), ans in zip(HAND, answers):
        report(f'hand {name} [exact unique fields]', None if matches_expectation(req, ans, expect) else f'got {ans}')
        report(f'hand {name} [semantic validator]', validate(req, ans))
    if write_files:
        with open(HERE / 'my_cases.jsonl', 'w', encoding='utf-8') as f:
            for r in requests:
                f.write(json.dumps(r, separators=(',', ':')) + '\n')
        with open(HERE / 'expected_outputs.jsonl', 'w', encoding='utf-8') as f:
            for name, _, e in HAND:
                f.write(json.dumps({'name': name, 'expected_unique_fields': e}, separators=(',', ':')) + '\n')
        with open(HERE / 'actual_outputs.jsonl', 'w', encoding='utf-8') as f:
            for (name, _, _), a in zip(HAND, answers):
                f.write(json.dumps({'name': name, 'actual': a}, separators=(',', ':')) + '\n')
        print('wrote my_cases.jsonl, expected_outputs.jsonl, actual_outputs.jsonl')


def random_request(rng, task):
    n = rng.randint(0, 9)
    m = rng.randint(0, 20) if n else 0
    wmax = rng.choice([1, 3, 1000])
    if task == 'dsu':
        return {'task': 'dsu', 'n': n, 'operations': [[rng.randrange(n), rng.randrange(n)] for _ in range(rng.randint(0, 15) if n else 0)]}
    if task in ('kruskal', 'prim'):
        return {'task': task, 'n': n, 'edges': [[rng.randrange(n), rng.randrange(n), rng.randint(-wmax, wmax)] for _ in range(m)]}
    if task in ('scc', 'topo'):
        return {'task': task, 'n': n, 'edges': [[rng.randrange(n), rng.randrange(n)] for _ in range(m)]}
    # dag: build a DAG on a random permutation (or sometimes allow cycles)
    n = max(n, 1)
    perm = list(range(n))
    rng.shuffle(perm)
    edges = []
    for _ in range(rng.randint(0, 20)):
        a, b = rng.randrange(n), rng.randrange(n)
        if rng.random() < 0.08:
            edges.append([perm[a], perm[b], rng.randint(-wmax, wmax)])  # may create a cycle
        elif a != b:
            lo, hi = min(a, b), max(a, b)
            edges.append([perm[lo], perm[hi], rng.randint(-wmax, wmax)])
    return {'task': 'dag', 'n': n, 'source': rng.randrange(n), 'edges': edges}


def test_random_differential(count_per_task=250, seed=20261025):
    rng = random.Random(seed)
    tasks = ['dsu', 'kruskal', 'prim', 'scc', 'topo', 'dag']
    requests = [random_request(rng, t) for t in tasks for _ in range(count_per_task)]
    rng.shuffle(requests)  # mixed order in a single process: also exercises state reset
    answers = run_program(requests)
    bad = [(r, validate(r, a)) for r, a in zip(requests, answers) if validate(r, a)]
    report(f'random differential: {len(requests)} mixed requests vs brute-force oracles',
           f'{len(bad)} failures, first: {bad[0]}' if bad else None)
    again = run_program(requests + requests)
    same = again[:len(requests)] == answers and again[len(requests):] == answers
    report('state reset: two batches in one process and a separate run give identical outputs',
           None if same else 'outputs changed between repeats')
    # Prim and Kruskal must agree on optimum cost and component count.
    pairs = {}
    for r, a in zip(requests, answers):
        if r['task'] in ('kruskal', 'prim'):
            pairs.setdefault(json.dumps([r['n'], r['edges']]), {})[r['task']] = (a['cost'], a['components'])
    disagree = [k for k, v in pairs.items() if len(v) == 2 and v['kruskal'] != v['prim']]
    report('kruskal and prim agree (only on requests that were sent to both)', None if not disagree else 'disagreement')
    both = []
    for r in requests:
        if r['task'] == 'kruskal':
            both.append(r)
            both.append(dict(r, task='prim'))
    ans2 = run_program(both)
    mism = [(both[i], ans2[i], ans2[i + 1]) for i in range(0, len(both), 2)
            if (ans2[i]['cost'], ans2[i]['components']) != (ans2[i + 1]['cost'], ans2[i + 1]['components'])]
    report(f'kruskal vs prim on {len(both) // 2} identical graphs', f'mismatch: {mism[0]}' if mism else None)


def tarjan_labels(n, edges):
    """Independent iterative Tarjan for large SCC checks (different algorithm from Kosaraju)."""
    adj = [[] for _ in range(n)]
    for u, v in edges:
        adj[u].append(v)
    index = [-1] * n
    low = [0] * n
    on = [False] * n
    comp = [-1] * n
    stack, counter, ncomp = [], 0, 0
    for s in range(n):
        if index[s] != -1:
            continue
        work = [(s, 0)]
        index[s] = low[s] = counter
        counter += 1
        stack.append(s)
        on[s] = True
        while work:
            v, i = work.pop()
            if i < len(adj[v]):
                work.append((v, i + 1))
                w = adj[v][i]
                if index[w] == -1:
                    index[w] = low[w] = counter
                    counter += 1
                    stack.append(w)
                    on[w] = True
                    work.append((w, 0))
                elif on[w]:
                    low[v] = min(low[v], index[w])
            else:
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[v])
                if low[v] == index[v]:
                    while True:
                        w = stack.pop()
                        on[w] = False
                        comp[w] = ncomp
                        if w == v:
                            break
                    ncomp += 1
    return comp


def test_large(seed=7):
    rng = random.Random(seed)
    N, M, Q = 100000, 250000, 250000
    big = 1000000000
    t0 = time.time()

    # DSU: full states against an independent plain DSU.
    ops = [[rng.randrange(N), rng.randrange(N)] for _ in range(Q)]
    d, size, comps, largest, want = Dsu(N), [1] * N, N, 1, []
    sz = {}
    for u, v in ops:
        a, b = d.find(u), d.find(v)
        if a != b:
            d.p[a] = b
            sz[b] = sz.get(b, 1) + sz.get(a, 1)
            comps -= 1
            largest = max(largest, sz[b])
        want.append([comps, largest])
    ans = run_program([{'task': 'dsu', 'n': N, 'operations': ops}])[0]
    report('large dsu n=100000 q=250000', None if ans['states'] == want else 'states differ')

    # Kruskal / Prim: identical big graph, weights up to +-1e9, sum beyond 32 bits.
    edges = [[rng.randrange(N), rng.randrange(N), rng.randint(-big, big)] for _ in range(M)]
    optimum = oracle_mst_fast(N, edges)
    ka, pa = run_program([{'task': 'kruskal', 'n': N, 'edges': edges}, {'task': 'prim', 'n': N, 'edges': edges}])
    report('large kruskal n=100000 m=250000', check_forest({'n': N, 'edges': edges}, ka, optimum))
    report('large prim n=100000 m=250000', check_forest({'n': N, 'edges': edges}, pa, optimum))
    report('large cost really exceeds 32 bits', None if abs(optimum[0]) > 2 ** 31 else f'cost {optimum[0]} fits in 32 bits')

    # Deep chains.
    chain = [[i, i + 1] for i in range(N - 1)]
    chain_w = [[i, i + 1, (-1) ** i * (i % 1000 + 1)] for i in range(N - 1)]
    cyc = chain + [[N - 1, 0]]
    a_scc, a_topo, a_dag, a_cyc_scc, a_cyc_topo, a_cyc_dag = run_program([
        {'task': 'scc', 'n': N, 'edges': chain},
        {'task': 'topo', 'n': N, 'edges': chain},
        {'task': 'dag', 'n': N, 'source': 0, 'edges': chain_w},
        {'task': 'scc', 'n': N, 'edges': cyc},
        {'task': 'topo', 'n': N, 'edges': cyc},
        {'task': 'dag', 'n': N, 'source': 0, 'edges': [e + [1] for e in cyc]},
    ])
    labels = a_scc['component']
    report('deep chain scc: 100000 singleton components, 99999 condensation pairs',
           None if len(set(labels)) == N and len(a_scc['condensation']) == N - 1 and
           {(labels[i], labels[i + 1]) for i in range(N - 1)} == {tuple(p) for p in a_scc['condensation']} else 'wrong')
    report('deep chain topo', check_topo({'n': N, 'edges': chain}, a_topo, cyclic=False))
    pref = [0]
    for e in chain_w:
        pref.append(pref[-1] + e[2])
    report('deep chain dag', check_dag({'n': N, 'source': 0, 'edges': chain_w}, a_dag, dist=pref, cyclic=False))
    report('deep cycle scc: one component, empty condensation',
           None if len(set(a_cyc_scc['component'])) == 1 and a_cyc_scc['condensation'] == [] else 'wrong')
    report('deep cycle topo', None if a_cyc_topo == {'acyclic': False, 'order': []} else 'wrong')
    report('deep cycle dag', None if a_cyc_dag.get('acyclic') is False and a_cyc_dag.get('distance') == [] else 'wrong')

    # Random large digraph (SCC vs Tarjan) and large random DAG.
    g = [[rng.randrange(N), rng.randrange(N)] for _ in range(M)]
    a = run_program([{'task': 'scc', 'n': N, 'edges': g}])[0]
    tj = tarjan_labels(N, g)
    ok = len(a['component']) == N and all(c >= 0 for c in a['component'])
    mp1, mp2 = {}, {}
    for x, y in zip(a['component'], tj):
        if mp1.setdefault(x, y) != y or mp2.setdefault(y, x) != x:
            ok = False
            break
    want_c = {(a['component'][u], a['component'][v]) for u, v in g if a['component'][u] != a['component'][v]}
    ok = ok and len(a['condensation']) == len(set(map(tuple, a['condensation']))) and want_c == set(map(tuple, a['condensation']))
    report('large random scc vs independent Tarjan + exact condensation', None if ok else 'mismatch')

    perm = list(range(N))
    rng.shuffle(perm)
    rank = {v: i for i, v in enumerate(perm)}
    dedges = []
    for _ in range(M):
        x, y = rng.randrange(N), rng.randrange(N)
        if x != y:
            lo, hi = min(x, y), max(x, y)
            dedges.append([perm[lo], perm[hi], rng.randint(-big, big)])
    src = perm[0]
    dist = [None] * N
    dist[src] = 0
    out_edges = [[] for _ in range(N)]
    for u, v, w in dedges:
        out_edges[u].append((v, w))
    for u in perm:
        if dist[u] is None:
            continue
        for v, w in out_edges[u]:
            if dist[v] is None or dist[u] + w < dist[v]:
                dist[v] = dist[u] + w
    req = {'n': N, 'source': src, 'edges': dedges}
    ad, at = run_program([dict(req, task='dag'), {'task': 'topo', 'n': N, 'edges': [e[:2] for e in dedges]}])
    report('large random dag distances and parent paths', check_dag(req, ad, dist=dist, cyclic=False))
    report('large random dag topo order', check_topo({'n': N, 'edges': [e[:2] for e in dedges]}, at, cyclic=False))
    # A back edge from a vertex reachable from the source to the source always closes a cycle.
    far = max((v for v in range(N) if dist[v] is not None and v != src), key=lambda v: rank[v])
    back = dedges + [[far, src, 1]]
    cyc_exists = oracle_cyclic_fast(N, [e[:2] for e in back])
    ab = run_program([dict(req, task='dag', edges=back)])[0]
    report(f'large dag with a back edge (Kahn oracle says cyclic={cyc_exists})',
           None if (cyc_exists and ab.get('acyclic') is False and ab.get('distance') == []) else 'cycle not detected')
    print(f'(large tests took {time.time() - t0:.1f} s)')


def oracle_mst_fast(n, edges):
    d = Dsu(n)
    cost = 0
    for u, v, w in sorted(edges, key=lambda e: e[2]):
        if d.union(u, v):
            cost += w
    return cost, len({d.find(i) for i in range(n)})


def oracle_cyclic_fast(n, edges):
    """Kahn's algorithm (independent from DFS): True if a directed cycle exists."""
    indeg = [0] * n
    adj = [[] for _ in range(n)]
    for u, v in edges:
        adj[u].append(v)
        indeg[v] += 1
    queue = [v for v in range(n) if indeg[v] == 0]
    seen = 0
    while queue:
        v = queue.pop()
        seen += 1
        for w in adj[v]:
            indeg[w] -= 1
            if indeg[w] == 0:
                queue.append(w)
    return seen != n


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--write-files', action='store_true')
    parser.add_argument('--skip-large', action='store_true')
    args = parser.parse_args()
    test_validators_self_check()
    test_hand_cases(args.write_files)
    test_random_differential()
    if not args.skip_large:
        test_large()
    print()
    if FAILURES:
        print(f'{len(FAILURES)} FAILED')
        return 1
    print('ALL OWN TESTS PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
