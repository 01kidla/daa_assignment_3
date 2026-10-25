# Assignment 3 – Analysis

Language: **Java 17** (`submission.json` = `{"language":"Java"}`). All algorithms are in `src/Java/Algorithms.java`
(six methods plus the route helper `reconstructRoute`). JSON input/output and `Main` are the supplied files.

## 0. Build, run and test commands

Run everything from the repository root.

```
python tools/run.py --setup                 # launch check (ping)
python tools/run.py --check                 # 36 public cases + two batches in one process (state reset)
python tools/run.py --input tests/my_cases.jsonl   # actual answers for my hand-made requests
python tests/check_cases.py --write-files   # own tests: oracles, random, large, deep, state reset
javac --release 17 -encoding UTF-8 -d .build/tests src/Java/*.java tests/RouteHelperTest.java tests/Bench.java
java -cp .build/tests RouteHelperTest       # direct calls of the route helper
java -cp .build/tests Bench                 # Kruskal vs Prim benchmark
```

Requirements: JDK 17+, Python 3.12+. No external libraries; only `java.util` is used.
The test files, the expected answers (derived by hand) and their justification are in `tests/` (see `tests/CASES.md`).

## 1. Common design decisions

**Iterative traversals / deep graphs.** There is no recursion anywhere. DFS uses an explicit `int[]` stack and a
per-vertex pointer `next[v]` (the next unread arc of `v`). A suspended vertex therefore resumes exactly where it stopped
and no neighbour is rescanned, so DFS is `O(n + m)` and a chain of 100 000 vertices needs no call stack.
Graphs are stored in compressed adjacency arrays (CSR: `start`, `to`, `edge`), built in `O(n + m)`; `edge` keeps the
**original** edge id of every arc, so ids survive sorting and adjacency construction.

**State reset.** `Main` handles one request after another in one process. Every method keeps all state in local
variables (arrays are allocated per request); the class has no mutable static field (only constants). Hence a request
cannot see anything from an earlier one. Tested by `tools/run.py --check` (two batches in one process) and by
`tests/check_cases.py` (1 500 shuffled mixed requests, repeated, identical outputs).

**Overflow.** Costs and distances are `long`. `|w| <= 10^9` and a path has fewer than 10^5 edges, so sums stay below
10^14. Edge weights in the Kruskal/Prim heap keys are shifted by 10^9 so they are non-negative before packing
(`(w + 10^9) << 20 | id`); this fits easily into 63 bits.
Tests with sums beyond 32 bits: `kruskal_total_beyond_32_bit`, `prim_total_beyond_32_bit`, `dag_total_beyond_32_bit`
and the large random graphs.

## 2. Disjoint-set union (`dsu`)

**Steps.** `parent[i] = i`, `size[i] = 1`, `components = n`, `largest = (n > 0 ? 1 : 0)`. For each pair `(u, v)`: find both
roots with path compression (iterative two-pass); if different, attach the smaller tree below the larger (union by size),
add the sizes, decrease `components`, update `largest`; append `[components, largest]`.

**Invariant.** Every component is a tree whose root `r` has `size[r]` = number of vertices in the component;
`components` = number of roots; `largest` = maximum size seen, which equals the current maximum because sizes only grow.

**Correctness.** `find(u) == find(v)` iff `u` and `v` were connected by earlier operations. A repeated union or a
self-union finds equal roots and changes nothing, so the partition is unchanged. No initial state is emitted;
for `n = 0` the result is `[]`.

**Boundaries.** `n = 0`, no operations, self-union, repeated union, `q` > `n`.

**Complexity.** `O(n + q α(n))` time (path compression + union by size), `O(n + q)` memory (the `q` returned states).

## 3. Kruskal (`kruskal`)

**Steps.** Pack every edge as `(w + 10^9) << 20 | id` and sort the `long[]` (primitive sort, order by weight, id is
kept in the low bits). Scan in order; accept edge `id` iff `find(u) != find(v)`, then union; add its weight.
`components = n - accepted`.

**Invariant.** The accepted edges are a forest contained in some minimum spanning forest, and DSU components =
connected components of the accepted edges.

**Correctness.** Cycle/cut property: the cheapest edge leaving a component of the accepted forest can be exchanged into
an optimum forest. An edge inside one component closes a cycle (self-loops always do) and is skipped. Negative weights
need no special case: a spanning forest has exactly `n - c` edges, so only the relative order of weights matters.
At the end the accepted edges connect each input component, so `components = n - accepted`.

**Boundaries.** `n = 0` (cost 0, no ids, 0 components), isolated vertices, self-loops, parallel edges, equal weights,
negative weights, sums beyond 32 bits.

**Complexity.** `O(n + m log(m + 1))` time (sort dominates, DSU part `O(m α(n))`), `O(n + m)` memory.

## 4. Prim (`prim`)

**Steps.** Build undirected CSR (a self-loop is dropped, every other edge gives two arcs). Lazy binary min-heap of
primitive `long` keys `(w + 10^9) << 20 | arcIndex`. For each unvisited vertex `s` (a new component): mark `s`, push its arcs
to unvisited vertices; repeatedly pop the minimum arc; skip it if its target is already visited (stale entry); otherwise
visit the target, record the original edge id and weight, push the new arcs. When the heap is empty, restart from the next unvisited vertex.

**Invariant.** The recorded edges form a tree on the visited vertices of the current component and belong to some
minimum spanning forest.

**Correctness.** The heap holds (at least) every arc leaving the visited set; the popped non-stale arc is the lightest arc
crossing the cut (visited, unvisited), so the cut property applies. A stale entry has both ends visited and is ignored.
When the heap is empty the whole connected component is visited; restarting handles every component, including isolated
vertices (they count as components with no edge). No edge id is repeated because a target is visited only once.

**Boundaries.** Same as Kruskal; the restart logic is covered by `prim_two_components_restart` and
`prim_disconnected_isolate`.

**Complexity.** Each arc is pushed at most once, so the heap has `<= 2m` entries: `O(n + m log(m + 1))` time, `O(n + m)` memory.
Kruskal and Prim return the same cost and number of components (tested on 250 random graphs and on the big ones); their edge ids may differ.

## 5. Kosaraju SCC (`scc`)

**Steps.** (1) Iterative DFS over all vertices of the original graph, recording the finishing order. (2) Build the transposed
graph. (3) Take vertices in **decreasing** finishing order; every unlabelled vertex starts a new label and an iterative
sweep over the transposed graph labels everything it reaches that is still unlabelled. (4) For every input edge with
different labels add the pair `[label(u), label(v)]` to a `HashSet<Long>` keyed by `a * labels + b` and to the output list when new.

**Invariant.** After pass 2 has labelled `k` components, they are exactly `k` complete SCCs, taken in a topological order of
the condensation (source components first).

**Correctness.** The vertex with the largest finishing time lies in a source SCC of the condensation. In the transposed graph
that SCC has no incoming edges from unlabelled SCCs, so the sweep from it reaches exactly its own SCC. Removing it and
repeating gives all SCCs. Edges inside an SCC (including self-loops) are not output; each cross-component pair is output once because of the hash set.

**Boundaries.** `n = 0`, isolated vertices, self-loops, duplicate edges, duplicate cross edges (`scc_duplicate_cross_edges`), one big cycle, a chain of 10^5 vertices.

**Complexity.** `O(n + m)` expected time (hash set), `O(n + m)` memory. Verified on random graphs against a boolean transitive
closure (small) and an independent iterative Tarjan with the exact condensation (n = 10^5, m = 2.5 · 10^5).

## 6. DFS topological ordering (`topo`)

**Steps.** Iterative DFS with three states per vertex (0 unvisited, 1 active = on the explicit stack, 2 finished), started from
every unvisited vertex. For each arc `v -> w`: `w` unvisited, then push; `w` active, then a back edge, so a cycle is recorded;
`w` finished, then nothing. When `v` has no more arcs it is finished and appended to the finish list.
No cycle: the order is the finish list reversed. Cycle: `acyclic=false`, `order=[]`.

**Invariant.** The active vertices are exactly the path from the current DFS root to the current vertex.

**Correctness.** A directed cycle exists iff DFS finds a back edge (an arc to an active vertex): a back edge closes a cycle
with the active path; conversely the first-visited vertex of a cycle has all other cycle vertices as descendants and the
cycle arc into it is a back edge. A self-loop is an arc to the active vertex itself. An arc to a finished vertex is a forward
or cross edge and does not indicate a cycle. For every arc `u -> v` of an acyclic graph, `v` finishes before `u`, so in the reversed finish order `u` comes first.

**Boundaries.** `n = 0`, isolated vertices, duplicate and parallel edges, self-loop, cycle in a component other than the first, 10^5-vertex chain and cycle.

**Complexity.** `O(n + m)` time and memory (each arc is read once because of `next[v]`).

## 7. DAG shortest paths (`dag`)

**Steps.** Run the same three-state DFS on the **whole** graph. If a cycle exists anywhere (even unreachable from
`source`) return `acyclic=false`, `distance=[]`, `parent_edge=[]`. Otherwise process vertices in reversed finishing order
(topological order). A vertex is relaxed only if it is reachable (`reached[u]`); for each arc `u -> v` with edge id `id`:
if `v` is not yet reached or `dist[u] + w < dist[v]`, set `dist[v]`, `parent_edge[v] = id`, `reached[v] = true`.
`distance[v] = null` for unreached vertices; `parent_edge = -1` for the source and unreachable vertices.

**Invariant.** When `u` is processed, every predecessor has already been processed, so `dist[u]` is final.

**Correctness.** In a DAG every shortest path follows the topological order, so relaxing outgoing arcs in that order computes
exact distances (negative weights are harmless because no vertex is relaxed twice after being final). The source cannot be
improved: any path into it from a reachable vertex would form a cycle. `parent_edge[v]` is the id of an edge `u -> v` with
`dist[u] + w = dist[v]` and `u` strictly earlier in topological order, so following parents reaches the source. Unreachable
vertices are never relaxed from, and `null` (not -1) is used for them because -1 can be a real distance.

**Boundaries.** `n = 1`, source with no edges, unreachable vertices, cycle outside the source's reach, self-loop, parallel and tied edges, distance -1, sums beyond 32 bits, 10^5-vertex chain.

**Complexity.** `O(n + m)` time and memory.

### Route-reconstruction helper

`Algorithms.reconstructRoute(source, target, parentEdge, edges)` starts at `target`, repeatedly takes the edge id
`parentEdge[v]` and moves to its start vertex, then reverses the list. The route to the source is `[source]`.
**Documented no-route result: an empty list** (`[]`) when `target` is unreachable (`parentEdge[target] = -1`); the JSON
`distance` of that vertex is still `null`. `Algorithms.routeCost` adds the weights of the selected edges. Complexity: `O(L)` time and output space for `L` vertices.

Actual calls (`java -cp .build/tests RouteHelperTest`; edge ids are positions in `edges`):

| Case | Call | Selected edge ids / parent_edge | Result | Check |
|---|---|---|---|---|
| Spec example `n=5, source=0, edges=[[0,1,3],[0,2,8],[1,2,-7],[2,3,4]]` | route(0 → 3) | `parent_edge = [-1,0,2,3,-1]`, ids on route `[0,2,3]` | `[0,1,2,3]` | edges 0→1, 1→2, 2→3 all exist in the right direction; cost 3 − 7 + 4 = **0** = distance[3] |
| same | route(0 → 0) | – | `[0]` | route to the source |
| same | route(0 → 4) | `parent_edge[4] = -1` | `[]` | vertex 4 unreachable, `distance[4] = null` |
| Ties/parallel `n=4, source=0, edges=[[0,1,5],[0,1,5],[1,3,1],[0,2,2],[2,3,4]]` | route(0 → 3) | `parent_edge = [-1,0,3,4]`, ids on route `[3,4]` | `[0,2,3]` | edges 0→2 (2) and 2→3 (4): cost **6** = distance[3]; the other tied route `[0,1,3]` (5 + 1 = 6) would be equally valid |
| same | route(0 → 1) | `parent_edge[1] = 0` | `[0,1]` | edges 0 and 1 are parallel and tied, either id is correct; cost 5 |
| Negative `n=5, source=1, edges=[[1,2,-1],[2,3,-1],[1,3,5],[0,1,7]]` | route(1 → 3) | `parent_edge = [-1,-1,0,1,-1]` | `[1,2,3]` | cost −1 − 1 = **−2** < direct edge 5; distance −1 to vertex 2 is a real value |
| same | route(1 → 0) | – | `[]` | only an edge *into* the source exists; vertex 0 unreachable |
| Chain of 100 000 vertices | route(0 → 99999) | – | 100 000 vertices | cost 99 999, no recursion |

## 8. Testing summary

* `python tools/run.py --check`: the 36 public cases and the two-batch state-reset check.
* `python tests/check_cases.py`: 28 hand-made cases with expected answers derived by hand (`tests/CASES.md`), each checked
  for the unique fields and by the semantic validator; self-checks showing that the validators accept alternative valid
  answers and reject invalid witnesses; 1 500 random mixed requests against brute-force oracles; repeated runs for state
  reset; Kruskal vs Prim on identical graphs; large inputs at the limits (n = 10^5, m/q = 2.5 · 10^5); deep chains of 10^5 vertices.
* `RouteHelperTest`: direct calls of the helper (table above).
* Non-unique answers are verified semantically (forest feasibility and optimum cost, SCC membership and exact condensation,
  topological precedence, shortest distances with valid parent paths), never by exact equality.

## 9. Benchmark: Kruskal vs Prim on identical graphs

**Method.** `tests/Bench.java`. Three sizes: (n, m) = (1 000, 5 000), (20 000, 100 000), (100 000, 250 000).
Graph generator: `java.util.Random` with seed `20261025 + n`; both endpoints uniform in `[0, n)` (self-loops and parallel edges possible),
weights uniform in `[-10^6, 10^6]`. Each size uses **one** graph object for both methods. Before any timing the program checks that
both methods return the same cost and number of components and that each selected edge set is a valid spanning forest
(no cycle, no repeated id or self-loop, `n - c` edges, the edges connect every component, the cost equals the sum).
Verified optima (deterministic for the seed): n = 1 000: cost −761 691 264, 1 component;
n = 20 000: cost −15 218 042 290, 1 component; n = 100 000: cost −52 744 406 754, 645 components.

**Measured region (same for both methods).** One call of `Algorithms.kruskal(request)` / `Algorithms.prim(request)` on an
already parsed request: includes `Input` conversion of the request to arrays, graph construction (CSR for Prim, key array for
Kruskal), the algorithm and creation of the result map. **Excluded:** compilation, JSON text parsing, JSON output, graph
generation and the correctness checks. Timer: `System.nanoTime()` (milliseconds shown). Warm-up: 30 calls of each method on
a 1 000-vertex graph, then 3 untimed calls per method per size. 7 timed runs per method and size, interleaved (Kruskal, Prim, Kruskal, …);
the table shows all 7 timings and the median.

**Hardware and run (fill in from your own run).**

```
Command:   java -cp .build/tests Bench
Machine:   <AMD Ryzen 5 8645HS w/ Radeon 760M Graphics, 12 logical CPUs, 16 GB RAM, Windows 11>
JVM line:  <java.version=25.0.4.1 os=Windows 11 amd64 cpus=12 maxHeapMB=3900>
```

**Results (paste the table printed by `Bench`; times in ms).**

| n | m | method | run 1 | run 2 | run 3 | run 4 | run 5 | run 6 | run 7 | median (ms) |
|---|---|--------|-------|-------|-------|-------|-------|-------|-------|-------------|
| 1000 | 5000 | Kruskal | 1.67 | 1.37 | 1.42 | 1.35 | 1.33 | 0.90 | 0.98 | **1.35** |
| 1000 | 5000 | Prim | 1.79 | 1.54 | 1.38 | 1.77 | 1.09 | 0.95 | 1.05 | **1.38** |
| 20000 | 100000 | Kruskal | 18.54 | 21.19 | 23.47 | 25.90 | 25.28 | 19.31 | 14.78 | **21.19** |
| 20000 | 100000 | Prim | 37.99 | 27.15 | 30.66 | 41.64 | 47.21 | 28.90 | 30.93 | **30.93** |
| 100000 | 250000 | Kruskal | 46.53 | 48.92 | 51.72 | 44.37 | 43.48 | 57.38 | 111.83 | **48.92** |
| 100000 | 250000 | Prim | 100.67 | 99.03 | 114.03 | 94.70 | 102.20 | 148.22 | 97.91 | **100.67** |

**Asymptotic argument (independent of the measurements).** Both methods are `O(n + m log(m + 1))`. Kruskal sorts `m` keys and
then does `m` DSU operations; Prim builds adjacency arrays, pushes at most `2m` arcs into a heap and pops them, each push and pop `O(log m)`.
The constants differ: Kruskal uses a primitive-`long` sort with sequential memory access, Prim does heap sifting with
random access into the adjacency arrays and the `visited` array.

**Observations.** At n = 1 000 the two methods were practically tied (median 1.35 ms for Kruskal and 1.38 ms for Prim). At n = 20 000 Kruskal was about 1.5 times faster (21.19 ms against 30.93 ms), and at n = 100 000 about 2.1 times faster (48.92 ms against 100.67 ms). The gap grows with the size of the graph, which matches the larger constant of Prim (heap operations with random memory access) compared with a primitive sort followed by DSU operations. Both times grow a little faster than linearly in m. Some runs are noticeably slower than the rest (Kruskal run 7 at n = 100 000: 111.83 ms; Prim run 6: 148.22 ms), probably because of garbage collection or other activity of the machine; the medians are not affected by such outliers.

**Limitations.** One random graph family (uniform endpoints, sparse, average degree 5–10); results for dense graphs,
other weight distributions or already sorted input may differ. A small number of runs (7) and a shared machine make
single timings noisy, which is why medians are reported. JIT compilation and garbage collection can move individual runs;
the warm-up reduces but does not remove this. Parsing and output are excluded, so absolute end-to-end times through the
JSON interface are larger than the numbers above.

## 10. Sources, AI tools and own verification

* Algorithms follow the textbook descriptions of DSU, Kruskal, Prim, Kosaraju and DFS topological sorting
  (e.g. Cormen, Leiserson, Rivest, Stein, *Introduction to Algorithms*) and the course lectures.
* AI tool: **Claude (Anthropic)** was used to draft `src/Java/Algorithms.java`, the tests in `tests/` and this analysis.
I read each method and the explanation of why it is correct, ran all commands from section 0 on my own computer, ran the benchmark myself and took the numbers in section 9 from my own run.
* No other external code was used; no dependencies beyond the Java standard library.
