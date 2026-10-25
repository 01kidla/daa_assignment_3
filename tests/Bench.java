import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Random;

/**
 * Kruskal vs Prim benchmark on IDENTICAL graphs at three sizes.
 *
 * Build and run from the repository root:
 *   javac --release 17 -d .build/tests src/Java/*.java tests/RouteHelperTest.java tests/Bench.java
 *   java -cp .build/tests Bench
 *
 * Measured region (same for both methods): one call Algorithms.kruskal(request) or
 * Algorithms.prim(request), i.e. Input conversion of the already-parsed request,
 * the algorithm itself and building the result map. Excluded: compilation, JSON text
 * parsing, JSON output, graph generation and the correctness checks.
 * Timer: System.nanoTime(). Warm-up: WARMUP untimed runs of each method per size
 * (after a global warm-up on the smallest graph) so the JIT has compiled the code.
 * Kruskal and Prim runs are interleaved (K, P, K, P, ...) to share machine noise.
 */
public final class Bench {
    private static final long SEED = 20261025L;
    private static final int WARMUP = 3;
    private static final int RUNS = 7;
    private static final int[][] SIZES = {{1_000, 5_000}, {20_000, 100_000}, {100_000, 250_000}};

    public static void main(String[] args) {
        System.out.println("java.version=" + System.getProperty("java.version")
                + " os=" + System.getProperty("os.name") + " " + System.getProperty("os.arch")
                + " cpus=" + Runtime.getRuntime().availableProcessors()
                + " maxHeapMB=" + Runtime.getRuntime().maxMemory() / (1024 * 1024));
        System.out.println("seed=" + SEED + " warmup=" + WARMUP + " runs=" + RUNS + " timer=System.nanoTime");

        // Global JIT warm-up on a small graph.
        Map<String, Object> tiny = makeRequest(1_000, 5_000, new Random(1));
        for (int i = 0; i < 30; i++) {
            Algorithms.kruskal(tiny);
            Algorithms.prim(tiny);
        }

        System.out.println();
        System.out.println("| n | m | method | run 1 | run 2 | run 3 | run 4 | run 5 | run 6 | run 7 | median (ms) |");
        System.out.println("|---|---|--------|-------|-------|-------|-------|-------|-------|-------|-------------|");
        for (int[] size : SIZES) {
            int n = size[0];
            int m = size[1];
            Random rng = new Random(SEED + n); // the graph is fixed by (seed, n, m)
            Map<String, Object> request = makeRequest(n, m, rng);

            // Correctness first: same optimum cost and component count, valid forests.
            Map<String, Object> k = Algorithms.kruskal(request);
            Map<String, Object> p = Algorithms.prim(request);
            verify(n, Input.edges(request), k, p);

            for (int i = 0; i < WARMUP; i++) {
                Algorithms.kruskal(request);
                Algorithms.prim(request);
            }
            double[] kt = new double[RUNS];
            double[] pt = new double[RUNS];
            for (int r = 0; r < RUNS; r++) {
                long t0 = System.nanoTime();
                Algorithms.kruskal(request);
                kt[r] = (System.nanoTime() - t0) / 1e6;
                long t1 = System.nanoTime();
                Algorithms.prim(request);
                pt[r] = (System.nanoTime() - t1) / 1e6;
            }
            printRow(n, m, "Kruskal", kt);
            printRow(n, m, "Prim", pt);
        }
    }

    private static Map<String, Object> makeRequest(int n, int m, Random rng) {
        List<Object> edges = new ArrayList<>(m);
        for (int i = 0; i < m; i++) {
            List<Object> e = new ArrayList<>(3);
            e.add((long) rng.nextInt(n));
            e.add((long) rng.nextInt(n));
            e.add((long) rng.nextInt(2_000_001) - 1_000_000L); // weights in [-1e6, 1e6]
            edges.add(e);
        }
        Map<String, Object> request = new LinkedHashMap<>();
        request.put("task", "kruskal");
        request.put("n", (long) n);
        request.put("edges", edges);
        return request;
    }

    private static void verify(int n, int[][] edges, Map<String, Object> k, Map<String, Object> p) {
        long kc = (Long) k.get("cost");
        long pc = (Long) p.get("cost");
        int kcomp = (Integer) k.get("components");
        int pcomp = (Integer) p.get("components");
        if (kc != pc || kcomp != pcomp) {
            throw new IllegalStateException("Kruskal and Prim disagree: " + kc + "/" + kcomp + " vs " + pc + "/" + pcomp);
        }
        checkForest(n, edges, (int[]) k.get("edge_ids"), kc, kcomp, "Kruskal");
        checkForest(n, edges, (int[]) p.get("edge_ids"), pc, pcomp, "Prim");
        System.out.println("verified n=" + n + " m=" + edges.length + ": cost=" + kc + " components=" + kcomp
                + " forest edges=" + ((int[]) k.get("edge_ids")).length + " (both methods)");
    }

    private static void checkForest(int n, int[][] edges, int[] ids, long cost, int components, String name) {
        int[] parent = new int[n];
        for (int i = 0; i < n; i++) {
            parent[i] = i;
        }
        long sum = 0;
        boolean[] used = new boolean[edges.length];
        for (int id : ids) {
            if (used[id] || edges[id][0] == edges[id][1]) {
                throw new IllegalStateException(name + ": repeated id or self-loop");
            }
            used[id] = true;
            int a = root(parent, edges[id][0]);
            int b = root(parent, edges[id][1]);
            if (a == b) {
                throw new IllegalStateException(name + ": selected edges contain a cycle");
            }
            parent[a] = b;
            sum += edges[id][2];
        }
        if (sum != cost || ids.length != n - components) {
            throw new IllegalStateException(name + ": wrong cost or edge count");
        }
        for (int[] e : edges) { // spanning: every input edge joins vertices already connected
            if (root(parent, e[0]) != root(parent, e[1])) {
                throw new IllegalStateException(name + ": forest does not span a component");
            }
        }
    }

    private static int root(int[] parent, int x) {
        while (parent[x] != x) {
            parent[x] = parent[parent[x]];
            x = parent[x];
        }
        return x;
    }

    private static void printRow(int n, int m, String method, double[] times) {
        double[] sorted = times.clone();
        Arrays.sort(sorted);
        double median = sorted[sorted.length / 2];
        StringBuilder row = new StringBuilder("| " + n + " | " + m + " | " + method + " |");
        for (double t : times) {
            row.append(String.format(" %.2f |", t));
        }
        row.append(String.format(" **%.2f** |", median));
        System.out.println(row);
    }
}
