# Own test cases: inputs, expected answers, justification

Files in this folder:

| File | Content |
|---|---|
| `my_cases.jsonl` | the 28 hand-made requests below (one JSON request per line) |
| `expected_outputs.jsonl` | the hand-derived answer for each case (only fields that are unique by the contract) |
| `actual_outputs.jsonl` | the real answers of the Java program, written by `check_cases.py --write-files` |
| `check_cases.py` | semantic checker, brute-force oracles, random differential and large tests |
| `RouteHelperTest.java` | direct calls of the route-reconstruction helper |
| `Bench.java` | Kruskal vs Prim benchmark |

Commands (repository root):

```
python tools/run.py --check                       # 36 public cases + state reset
python tests/check_cases.py --write-files         # own tests (about 15 s)
python tests/check_cases.py --skip-large          # own tests without the 100 000-vertex graphs
python tools/run.py --input tests/my_cases.jsonl  # prints the actual answers of my_cases.jsonl
javac --release 17 -encoding UTF-8 -d .build/tests src/Java/*.java tests/RouteHelperTest.java tests/Bench.java
java -cp .build/tests RouteHelperTest
java -cp .build/tests Bench
```

Non-unique answers (selected edge ids, labels, topological order, parent edges) are never compared
for equality. `check_cases.py` checks them by properties: forest feasibility and optimum cost, SCC
membership and the exact condensation set, topological precedence, shortest distances and valid parent
paths. Its self-check shows that it **accepts** alternative valid answers (edge ids in another order, a
different optimal forest, permuted SCC labels, another valid order, either tied parallel edge) and
**rejects** invalid witnesses (forest with a cycle, feasible but non-optimal forest, duplicate or missing
condensation pair, wrong partition, order with a backward edge, parent edge that does not end at the
vertex, wrong distance).

## Hand cases (expected answers derived by hand, independent of the program)

| Name | Why this answer is correct |
|---|---|
| `dsu_repeat_and_self` | The specification example. 0-1 gives 3 components, largest 2; 1-2 gives 2, 3; 0-2 is a repeat; 3-3 is a self-union, so the state stays `[2,3]`. |
| `dsu_empty_graph` | `n=0`: no vertices, no operations, `states=[]`. |
| `dsu_no_operations` | No operation means no state is output (no initial state), `states=[]`. |
| `dsu_chain_merges` | n=5. {0,1}: `[4,2]`. {2,3}: `[3,2]`. 1-2 joins them: `[2,4]`. 4-4 is a self-union: `[2,4]`. 3-4 joins vertex 4: `[1,5]`. |
| `kruskal_disconnected_isolate` | Edges 1-2 (2) and 0-2 (3) form a tree on {0,1,2}, cost 5; edge 0-1 (4) would close a cycle. Vertex 3 is isolated, so 2 components. |
| `kruskal_negative_loop_parallel` | The self-loop (-9) must never be chosen. Between 0 and 1 the parallel edges are 5 and -2: take -2. Between 1 and 2 take 0. Cost -2 + 0 = -2, 1 component. |
| `kruskal_total_beyond_32_bit` | A path of three edges of weight 10^9 must all be taken: 3 * 10^9 = 3 000 000 000 > 2^31 - 1, so a 32-bit sum would overflow. |
| `kruskal_empty` | `n=0`: cost 0, no edges, 0 components. |
| `prim_disconnected_isolate` | Same graph as the Kruskal example: cost 5, 2 components; Prim must restart for vertex 3. |
| `prim_two_components_restart` | Component {0,1,2}: two edges of weight 1, cost 2. Component {3,4,5}: edges -5, 2, 2: take -5 and one 2, cost -3. Total -1; 2 components. |
| `prim_total_beyond_32_bit` | A triangle with all weights -10^9: any two edges, cost -2 * 10^9 < -2^31. |
| `prim_ties_everywhere` | Five edges of weight 1 on 4 vertices; any spanning tree has 3 edges: cost 3, 1 component. |
| `scc_two_cycle_plus_tail` | The specification example. {0,1} are mutually reachable; 2 and 3 are singletons. Cross pairs: {0,1}->{2}, {2}->{3}. |
| `scc_isolated_and_loop` | Self-loops are internal edges; each of the 3 vertices is its own SCC and the condensation is empty. |
| `scc_duplicate_cross_edges` | {0,1} and {2,3} are SCCs (0->1, 1->0 and 3->2, 2->3 are internal, the duplicate 0->1 too). The only cross edge is 1->2, given twice, so the pair {0,1}->{2,3} must be listed exactly once. |
| `scc_empty` | `n=0`: both arrays empty. |
| `topo_simple` | The specification example: acyclic. |
| `topo_diamond_duplicates` | Diamond 0->1,0->2,1->3,2->3 plus the duplicate and shortcut edges 0->3: acyclic (every edge goes from a smaller to a larger number). A DFS reaches 3 again through a finished vertex: that is not a cycle. |
| `topo_self_loop` | A self-loop is a directed cycle: `acyclic=false`, `order=[]`. |
| `topo_cycle_in_second_component` | Component {0,1} is acyclic but {2,3,4} contains the cycle 2->3->4->2, so the answer must be cyclic: all components are checked. |
| `topo_empty` | `n=0`: acyclic, empty order. |
| `dag_spec_example` | The specification example. dist(1)=3, dist(2)=min(8, 3-7)=-4, dist(3)=-4+4=0, vertex 4 unreachable (`null`). |
| `dag_negative_one_is_a_distance` | Distance to vertex 1 is exactly -1 (a legal finite value); vertex 2 has no incoming edge and stays `null`. |
| `dag_tied_and_parallel` | Edges 0 and 1 are parallel with weight 5; dist(1)=5. dist(3)=min(5+1, 2+4)=6 (a tie), dist(2)=2. |
| `dag_cycle_unreachable_from_source` | Vertices 2 and 3 form a cycle although they are unreachable from source 0: the whole graph is cyclic, so `acyclic=false` with empty arrays. |
| `dag_self_loop` | A self-loop makes the graph cyclic even when it is on the source. |
| `dag_total_beyond_32_bit` | Prefix sums 10^9, 2 * 10^9, 3 * 10^9 on a path; the last two exceed 2^31 - 1. |
| `dag_singleton` | `n=1`, no edges: distance `[0]`, parent edge `[-1]`. |

## Further own tests (all in `check_cases.py`)

* 1 500 random small requests (250 per task, `n` from 0 to 9, many ties, negative weights, self-loops,
  parallel edges, cycles in the DAG task) in shuffled mixed order in **one process**, each answer checked
  against a brute-force oracle: naive label-merging DSU, naive relabelling Kruskal, boolean transitive closure
  for SCC / cycles, Bellman-Ford for DAG distances.
* The same 1 500 requests are sent twice in one process and once in another process: identical outputs (state reset).
* Kruskal and Prim on 250 identical random graphs: equal optimum cost and component count.
* Large inputs at the published limits (n = 100 000, m or q = 250 000): DSU states against an independent DSU;
  Kruskal and Prim with weights up to +-10^9 (the optimum exceeds 32 bits); SCC against an independent iterative
  Tarjan and the exact condensation; a random DAG (distances, parent paths, topological order) and the same DAG
  with a back edge (Kahn's algorithm confirms the cycle).
* Deep chains of 100 000 vertices for SCC, topological order and DAG distances, and the same chain closed to a cycle.
