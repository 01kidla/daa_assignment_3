import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;

/**
 * Calls the route-reconstruction helper directly (it is not a JSON task).
 *
 * Build and run from the repository root:
 *   javac --release 17 -d .build/tests src/Java/*.java tests/RouteHelperTest.java tests/Bench.java
 *   java -cp .build/tests RouteHelperTest
 *
 * "No route" result of the helper: an EMPTY list (JSON distance stays null).
 */
public final class RouteHelperTest {
    private static int failures = 0;

    private static void check(boolean condition, String message) {
        if (!condition) {
            failures++;
            System.out.println("  FAIL: " + message);
        } else {
            System.out.println("  ok:   " + message);
        }
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> solve(String json) {
        return Algorithms.dag(Json.parseRequest(json));
    }

    private static int[] ints(Object value) {
        return (int[]) value;
    }

    private static boolean isValidRoute(List<Integer> route, int source, int target, int[][] edges) {
        if (route.isEmpty() || route.get(0) != source || route.get(route.size() - 1) != target) {
            return false;
        }
        for (int i = 0; i + 1 < route.size(); i++) {
            boolean found = false;
            for (int[] e : edges) {
                if (e[0] == route.get(i) && e[1] == route.get(i + 1)) {
                    found = true;
                }
            }
            if (!found) {
                return false; // a consecutive pair is not a real directed edge
            }
        }
        return true;
    }

    public static void main(String[] args) {
        // ---- 1. Specification example: reachable target, the source, unreachable target.
        System.out.println("Case A (specification example): n=5 source=0");
        int[][] edgesA = {{0, 1, 3}, {0, 2, 8}, {1, 2, -7}, {2, 3, 4}};
        Map<String, Object> a = solve(
                "{\"task\":\"dag\",\"n\":5,\"source\":0,\"edges\":[[0,1,3],[0,2,8],[1,2,-7],[2,3,4]]}");
        int[] parentA = ints(a.get("parent_edge"));
        System.out.println("  parent_edge = " + Arrays.toString(parentA)
                + ", distance = " + Arrays.toString((Long[]) a.get("distance")));
        List<Integer> toThree = Algorithms.reconstructRoute(0, 3, parentA, edgesA);
        System.out.println("  route(0 -> 3) = " + toThree + ", cost = "
                + Algorithms.routeCost(0, 3, parentA, edgesA));
        check(toThree.equals(List.of(0, 1, 2, 3)), "route to vertex 3 is [0, 1, 2, 3]");
        check(Algorithms.routeCost(0, 3, parentA, edgesA) == 0, "total weight 3 + (-7) + 4 = 0");
        check(isValidRoute(toThree, 0, 3, edgesA), "every consecutive pair is a real directed edge u -> v");
        List<Integer> toSource = Algorithms.reconstructRoute(0, 0, parentA, edgesA);
        System.out.println("  route(0 -> 0) = " + toSource);
        check(toSource.equals(List.of(0)), "route to the source is [source]");
        List<Integer> toUnreachable = Algorithms.reconstructRoute(0, 4, parentA, edgesA);
        System.out.println("  route(0 -> 4) = " + toUnreachable + " (vertex 4 is unreachable)");
        check(toUnreachable.isEmpty(), "unreachable target gives the documented empty list");

        // ---- 2. Tied shortest routes and parallel edges.
        System.out.println("Case B (tied routes and parallel edges): n=4 source=0");
        // ids: 0:[0,1,5] 1:[0,1,5] (parallel, tied)  2:[1,3,1]  3:[0,2,2]  4:[2,3,4]
        // distance to 3 is 6 via 0-1-3 (5+1) and via 0-2-3 (2+4): a tie.
        int[][] edgesB = {{0, 1, 5}, {0, 1, 5}, {1, 3, 1}, {0, 2, 2}, {2, 3, 4}};
        Map<String, Object> b = solve("{\"task\":\"dag\",\"n\":4,\"source\":0,"
                + "\"edges\":[[0,1,5],[0,1,5],[1,3,1],[0,2,2],[2,3,4]]}");
        int[] parentB = ints(b.get("parent_edge"));
        Long[] distB = (Long[]) b.get("distance");
        System.out.println("  parent_edge = " + Arrays.toString(parentB) + ", distance = " + Arrays.toString(distB));
        List<Integer> toThreeB = Algorithms.reconstructRoute(0, 3, parentB, edgesB);
        List<Integer> toOneB = Algorithms.reconstructRoute(0, 1, parentB, edgesB);
        long cost3 = Algorithms.routeCost(0, 3, parentB, edgesB);
        System.out.println("  route(0 -> 3) = " + toThreeB + ", selected edge ids on it: "
                + selectedIds(0, 3, parentB, edgesB) + ", cost = " + cost3);
        System.out.println("  route(0 -> 1) = " + toOneB + ", selected edge id: " + parentB[1]
                + " (edge 0 and edge 1 are parallel and tied; either is correct)");
        check(distB[3] == 6, "shortest distance to 3 is 6");
        check(cost3 == 6, "cost of the reconstructed route equals the distance (6)");
        check(toThreeB.equals(List.of(0, 1, 3)) || toThreeB.equals(List.of(0, 2, 3)),
                "route to 3 is one of the two tied routes");
        check(isValidRoute(toThreeB, 0, 3, edgesB), "direction check: every pair is a directed edge");
        check(parentB[1] == 0 || parentB[1] == 1, "parent of 1 is one of the parallel edges 0 or 1");
        check(toOneB.equals(List.of(0, 1)), "route to 1 is [0, 1]");

        // ---- 3. Negative weights, finite distance -1, and a longer chain with a shortcut.
        System.out.println("Case C (distance -1 is a real distance): n=5 source=1");
        int[][] edgesC = {{1, 2, -1}, {2, 3, -1}, {1, 3, 5}, {0, 1, 7}};
        Map<String, Object> c = solve("{\"task\":\"dag\",\"n\":5,\"source\":1,"
                + "\"edges\":[[1,2,-1],[2,3,-1],[1,3,5],[0,1,7]]}");
        int[] parentC = ints(c.get("parent_edge"));
        System.out.println("  parent_edge = " + Arrays.toString(parentC)
                + ", distance = " + Arrays.toString((Long[]) c.get("distance")));
        List<Integer> toTwoC = Algorithms.reconstructRoute(1, 2, parentC, edgesC);
        List<Integer> toThreeC = Algorithms.reconstructRoute(1, 3, parentC, edgesC);
        List<Integer> toZeroC = Algorithms.reconstructRoute(1, 0, parentC, edgesC);
        System.out.println("  route(1 -> 2) = " + toTwoC + ", cost = " + Algorithms.routeCost(1, 2, parentC, edgesC));
        System.out.println("  route(1 -> 3) = " + toThreeC + ", cost = " + Algorithms.routeCost(1, 3, parentC, edgesC));
        System.out.println("  route(1 -> 0) = " + toZeroC + " (0 only has an edge INTO the source: unreachable)");
        check(toTwoC.equals(List.of(1, 2)) && Algorithms.routeCost(1, 2, parentC, edgesC) == -1,
                "route to 2 is [1, 2] with cost -1");
        check(toThreeC.equals(List.of(1, 2, 3)) && Algorithms.routeCost(1, 3, parentC, edgesC) == -2,
                "route to 3 is [1, 2, 3] with cost -2 (shorter than the direct edge of weight 5)");
        check(toZeroC.isEmpty(), "vertex 0 is not reachable from the source: empty list");

        // ---- 4. Long route (deep chain) is rebuilt without recursion.
        System.out.println("Case D (chain of 100000 vertices)");
        int n = 100000;
        int[][] chain = new int[n - 1][];
        StringBuilder sb = new StringBuilder("{\"task\":\"dag\",\"n\":" + n + ",\"source\":0,\"edges\":[");
        for (int i = 0; i < n - 1; i++) {
            chain[i] = new int[] {i, i + 1, 1};
            sb.append(i == 0 ? "" : ",").append("[").append(i).append(",").append(i + 1).append(",1]");
        }
        sb.append("]}");
        int[] parentD = ints(solve(sb.toString()).get("parent_edge"));
        List<Integer> longRoute = Algorithms.reconstructRoute(0, n - 1, parentD, chain);
        check(longRoute.size() == n && longRoute.get(0) == 0 && longRoute.get(n - 1) == n - 1,
                "route over 100000 vertices has 100000 entries from 0 to 99999");
        check(Algorithms.routeCost(0, n - 1, parentD, chain) == n - 1, "its cost is 99999");

        System.out.println();
        if (failures == 0) {
            System.out.println("ALL ROUTE HELPER TESTS PASSED");
        } else {
            System.out.println(failures + " ROUTE HELPER CHECK(S) FAILED");
            System.exit(1);
        }
    }

    private static List<Integer> selectedIds(int source, int target, int[] parent, int[][] edges) {
        List<Integer> ids = new ArrayList<>();
        int v = target;
        while (v != source) {
            ids.add(0, parent[v]);
            v = edges[parent[v]][0];
        }
        return ids;
    }
}
