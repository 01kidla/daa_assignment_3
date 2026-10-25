import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Graph algorithms for the campus-festival assignment.
 *
 * Every method keeps all of its state in local variables, so each request is
 * independent of the previous one. All graph traversals are iterative (explicit
 * stacks), so chains of 100 000 vertices cannot overflow the call stack.
 */
public final class Algorithms {
    private Algorithms() {
    }

    /** Added to a signed weight (|w| <= 1e9) so that it becomes non-negative. */
    private static final long WEIGHT_OFFSET = 1_000_000_000L;
    /** Low bits of a packed sort key hold an id (< 2^20 = 1 048 576). */
    private static final int ID_BITS = 20;
    private static final long ID_MASK = (1L << ID_BITS) - 1;

    // ------------------------------------------------------------------
    // Shared helpers
    // ------------------------------------------------------------------

    /** Compressed adjacency lists (CSR): arcs of v are start[v] .. start[v+1]-1. */
    private static final class Csr {
        final int[] start;
        final int[] to;
        final int[] edge; // original edge id of each arc

        Csr(int[] start, int[] to, int[] edge) {
            this.start = start;
            this.to = to;
            this.edge = edge;
        }
    }

    private static final int DIRECTED = 0;
    private static final int REVERSED = 1;
    private static final int UNDIRECTED = 2; // self-loops are dropped

    private static Csr buildCsr(int n, int[][] edges, int mode) {
        int[] start = new int[n + 1];
        for (int[] e : edges) {
            int u = e[0];
            int v = e[1];
            if (mode == UNDIRECTED) {
                if (u == v) {
                    continue;
                }
                start[u + 1]++;
                start[v + 1]++;
            } else if (mode == DIRECTED) {
                start[u + 1]++;
            } else {
                start[v + 1]++;
            }
        }
        for (int i = 0; i < n; i++) {
            start[i + 1] += start[i];
        }
        int[] fill = Arrays.copyOf(start, n);
        int[] to = new int[start[n]];
        int[] edge = new int[start[n]];
        for (int id = 0; id < edges.length; id++) {
            int u = edges[id][0];
            int v = edges[id][1];
            if (mode == UNDIRECTED) {
                if (u == v) {
                    continue;
                }
                int a = fill[u]++;
                to[a] = v;
                edge[a] = id;
                int b = fill[v]++;
                to[b] = u;
                edge[b] = id;
            } else if (mode == DIRECTED) {
                int a = fill[u]++;
                to[a] = v;
                edge[a] = id;
            } else {
                int a = fill[v]++;
                to[a] = u;
                edge[a] = id;
            }
        }
        return new Csr(start, to, edge);
    }

    /** Find with iterative path compression. */
    private static int find(int[] parent, int x) {
        int root = x;
        while (parent[root] != root) {
            root = parent[root];
        }
        while (parent[x] != root) {
            int next = parent[x];
            parent[x] = root;
            x = next;
        }
        return root;
    }

    /**
     * Three-state iterative DFS over every component (0 = unvisited, 1 = active,
     * 2 = finished). Returns the vertices in finishing order. An edge into an
     * active vertex is a back edge and sets cyclic[0]; an edge into a finished
     * vertex is not a cycle. The explicit stack keeps one "next arc" pointer per
     * suspended vertex, so no neighbour is ever rescanned.
     */
    private static int[] finishOrder(int n, Csr g, boolean[] cyclic) {
        byte[] state = new byte[n];
        int[] next = Arrays.copyOf(g.start, n);
        int[] stack = new int[n];
        int[] order = new int[n];
        int count = 0;
        for (int s = 0; s < n; s++) {
            if (state[s] != 0) {
                continue;
            }
            int top = 0;
            stack[top++] = s;
            state[s] = 1;
            while (top > 0) {
                int v = stack[top - 1];
                if (next[v] < g.start[v + 1]) {
                    int w = g.to[next[v]++];
                    if (state[w] == 0) {
                        state[w] = 1;
                        stack[top++] = w;
                    } else if (state[w] == 1) {
                        cyclic[0] = true;
                    }
                } else {
                    state[v] = 2;
                    order[count++] = v;
                    top--;
                }
            }
        }
        return order;
    }

    // ------------------------------------------------------------------
    // DSU
    // ------------------------------------------------------------------

    /** DSU with path compression and union by size/rank; return states. */
    static Map<String, Object> dsu(Map<String, Object> input) {
        int n = Input.vertexCount(input);
        int[][] operations = Input.operations(input);

        int[] parent = new int[n];
        int[] size = new int[n];
        for (int i = 0; i < n; i++) {
            parent[i] = i;
            size[i] = 1;
        }
        int components = n;
        int largest = n > 0 ? 1 : 0;
        int[][] states = new int[operations.length][];

        for (int i = 0; i < operations.length; i++) {
            int a = find(parent, operations[i][0]);
            int b = find(parent, operations[i][1]);
            if (a != b) {
                if (size[a] < size[b]) {
                    int t = a;
                    a = b;
                    b = t;
                }
                parent[b] = a;
                size[a] += size[b];
                components--;
                if (size[a] > largest) {
                    largest = size[a];
                }
            }
            states[i] = new int[] {components, largest};
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("states", states);
        return result;
    }

    // ------------------------------------------------------------------
    // Kruskal
    // ------------------------------------------------------------------

    /** Separate Kruskal implementation; return cost, edge_ids, components. */
    static Map<String, Object> kruskal(Map<String, Object> input) {
        int n = Input.vertexCount(input);
        int[][] edges = Input.edges(input);
        int m = edges.length;

        // Pack (weight, original id) into one long so that a primitive sort
        // orders by weight and keeps the original id.
        long[] keys = new long[m];
        for (int id = 0; id < m; id++) {
            keys[id] = ((edges[id][2] + WEIGHT_OFFSET) << ID_BITS) | id;
        }
        Arrays.sort(keys);

        int[] parent = new int[n];
        int[] size = new int[n];
        for (int i = 0; i < n; i++) {
            parent[i] = i;
            size[i] = 1;
        }

        int[] chosen = new int[Math.max(0, n - 1)];
        int taken = 0;
        long cost = 0;
        for (long key : keys) {
            int id = (int) (key & ID_MASK);
            int a = find(parent, edges[id][0]);
            int b = find(parent, edges[id][1]);
            if (a == b) {
                continue; // cycle or self-loop
            }
            if (size[a] < size[b]) {
                int t = a;
                a = b;
                b = t;
            }
            parent[b] = a;
            size[a] += size[b];
            chosen[taken++] = id;
            cost += edges[id][2];
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("cost", cost);
        result.put("edge_ids", Arrays.copyOf(chosen, taken));
        result.put("components", n - taken);
        return result;
    }

    // ------------------------------------------------------------------
    // Prim
    // ------------------------------------------------------------------

    /** Minimal binary min-heap of primitive longs. */
    private static final class LongHeap {
        private long[] data;
        private int size;

        LongHeap(int capacity) {
            data = new long[Math.max(capacity, 4)];
        }

        boolean isEmpty() {
            return size == 0;
        }

        void push(long x) {
            if (size == data.length) {
                data = Arrays.copyOf(data, size * 2);
            }
            int i = size++;
            while (i > 0) {
                int p = (i - 1) >> 1;
                if (data[p] <= x) {
                    break;
                }
                data[i] = data[p];
                i = p;
            }
            data[i] = x;
        }

        long pop() {
            long top = data[0];
            long x = data[--size];
            if (size > 0) {
                int i = 0;
                while (true) {
                    int c = 2 * i + 1;
                    if (c >= size) {
                        break;
                    }
                    if (c + 1 < size && data[c + 1] < data[c]) {
                        c++;
                    }
                    if (data[c] >= x) {
                        break;
                    }
                    data[i] = data[c];
                    i = c;
                }
                data[i] = x;
            }
            return top;
        }
    }

    /** Separate Prim implementation; restart for every unvisited component. */
    static Map<String, Object> prim(Map<String, Object> input) {
        int n = Input.vertexCount(input);
        int[][] edges = Input.edges(input);

        Csr g = buildCsr(n, edges, UNDIRECTED);
        boolean[] visited = new boolean[n];
        LongHeap heap = new LongHeap(Math.min(g.to.length, 1 << 16));
        int[] chosen = new int[Math.max(0, n - 1)];
        int taken = 0;
        long cost = 0;
        int components = 0;

        for (int s = 0; s < n; s++) {
            if (visited[s]) {
                continue;
            }
            components++;
            visited[s] = true;
            pushArcs(g, edges, visited, heap, s);
            while (!heap.isEmpty()) {
                int arc = (int) (heap.pop() & ID_MASK);
                int v = g.to[arc];
                if (visited[v]) {
                    continue; // stale lazy-heap entry
                }
                visited[v] = true;
                int id = g.edge[arc];
                chosen[taken++] = id;
                cost += edges[id][2];
                pushArcs(g, edges, visited, heap, v);
            }
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("cost", cost);
        result.put("edge_ids", Arrays.copyOf(chosen, taken));
        result.put("components", components);
        return result;
    }

    private static void pushArcs(Csr g, int[][] edges, boolean[] visited, LongHeap heap, int v) {
        for (int a = g.start[v]; a < g.start[v + 1]; a++) {
            if (!visited[g.to[a]]) {
                long w = edges[g.edge[a]][2];
                heap.push(((w + WEIGHT_OFFSET) << ID_BITS) | a);
            }
        }
    }

    // ------------------------------------------------------------------
    // Kosaraju SCC
    // ------------------------------------------------------------------

    /** Kosaraju's two DFS passes; return component and exact condensation. */
    static Map<String, Object> scc(Map<String, Object> input) {
        int n = Input.vertexCount(input);
        int[][] edges = Input.edges(input);

        // Pass 1: DFS on the original graph, record finishing order.
        Csr forward = buildCsr(n, edges, DIRECTED);
        int[] order = finishOrder(n, forward, new boolean[1]);

        // Pass 2: sweep the transposed graph in decreasing finishing order.
        Csr reverse = buildCsr(n, edges, REVERSED);
        int[] component = new int[n];
        Arrays.fill(component, -1);
        int[] stack = new int[n];
        int labels = 0;
        for (int i = n - 1; i >= 0; i--) {
            int s = order[i];
            if (component[s] != -1) {
                continue;
            }
            component[s] = labels;
            int top = 0;
            stack[top++] = s;
            while (top > 0) {
                int v = stack[--top];
                for (int a = reverse.start[v]; a < reverse.start[v + 1]; a++) {
                    int w = reverse.to[a];
                    if (component[w] == -1) {
                        component[w] = labels;
                        stack[top++] = w;
                    }
                }
            }
            labels++;
        }

        // Condensation: every cross-component pair exactly once.
        Set<Long> seen = new HashSet<>();
        List<int[]> pairs = new ArrayList<>();
        for (int[] e : edges) {
            int a = component[e[0]];
            int b = component[e[1]];
            if (a != b && seen.add((long) a * labels + b)) {
                pairs.add(new int[] {a, b});
            }
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("component", component);
        result.put("condensation", pairs);
        return result;
    }

    // ------------------------------------------------------------------
    // DFS topological ordering
    // ------------------------------------------------------------------

    /** Three-state DFS and reverse finish order; return acyclic and order. */
    static Map<String, Object> topo(Map<String, Object> input) {
        int n = Input.vertexCount(input);
        int[][] edges = Input.edges(input);

        boolean[] cyclic = new boolean[1];
        int[] finish = finishOrder(n, buildCsr(n, edges, DIRECTED), cyclic);

        Map<String, Object> result = new LinkedHashMap<>();
        if (cyclic[0]) {
            result.put("acyclic", false);
            result.put("order", new int[0]);
            return result;
        }
        int[] order = new int[n];
        for (int i = 0; i < n; i++) {
            order[i] = finish[n - 1 - i];
        }
        result.put("acyclic", true);
        result.put("order", order);
        return result;
    }

    // ------------------------------------------------------------------
    // DAG shortest paths
    // ------------------------------------------------------------------

    /** Whole-graph cycle check and DAG relaxation; return acyclic, distance, parent_edge. */
    static Map<String, Object> dag(Map<String, Object> input) {
        int n = Input.vertexCount(input);
        int source = Input.source(input);
        int[][] edges = Input.edges(input);

        Csr g = buildCsr(n, edges, DIRECTED);
        boolean[] cyclic = new boolean[1];
        int[] finish = finishOrder(n, g, cyclic);

        Map<String, Object> result = new LinkedHashMap<>();
        if (cyclic[0]) {
            result.put("acyclic", false);
            result.put("distance", new Long[0]);
            result.put("parent_edge", new int[0]);
            return result;
        }

        long[] dist = new long[n];
        boolean[] reached = new boolean[n];
        int[] parentEdge = new int[n];
        Arrays.fill(parentEdge, -1);
        reached[source] = true;

        // Reverse finishing order is a topological order.
        for (int i = n - 1; i >= 0; i--) {
            int u = finish[i];
            if (!reached[u]) {
                continue; // never relax from an unreachable vertex
            }
            for (int a = g.start[u]; a < g.start[u + 1]; a++) {
                int v = g.to[a];
                int id = g.edge[a];
                long candidate = dist[u] + edges[id][2];
                if (!reached[v] || candidate < dist[v]) {
                    reached[v] = true;
                    dist[v] = candidate;
                    parentEdge[v] = id;
                }
            }
        }

        Long[] distance = new Long[n];
        for (int v = 0; v < n; v++) {
            distance[v] = reached[v] ? Long.valueOf(dist[v]) : null;
        }
        result.put("acyclic", true);
        result.put("distance", distance);
        result.put("parent_edge", parentEdge);
        return result;
    }

    // ------------------------------------------------------------------
    // Route reconstruction helper (not a JSON task)
    // ------------------------------------------------------------------

    /**
     * Rebuilds the vertex sequence source -> ... -> target from parent edge ids.
     * The route to the source itself is [source]. If target has no route
     * (unreachable), the documented "no route" result is an EMPTY list.
     * Time and output space are O(L) for a route with L vertices.
     */
    static List<Integer> reconstructRoute(int source, int target, int[] parentEdge, int[][] edges) {
        List<Integer> route = new ArrayList<>();
        int v = target;
        route.add(v);
        while (v != source) {
            int id = parentEdge[v];
            if (id < 0 || edges[id][1] != v || route.size() > parentEdge.length) {
                return new ArrayList<>(); // unreachable (or inconsistent) target
            }
            v = edges[id][0];
            route.add(v);
        }
        Collections.reverse(route);
        return route;
    }

    /** Total weight of a route given as a vertex sequence, following parent edges. */
    static long routeCost(int source, int target, int[] parentEdge, int[][] edges) {
        long total = 0;
        int v = target;
        while (v != source) {
            int id = parentEdge[v];
            total += edges[id][2];
            v = edges[id][0];
        }
        return total;
    }
}
