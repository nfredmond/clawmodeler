# Tiny Region Fixture

Small public integration fixture for ClawModeler workflow checks. It is intentionally
not the synthetic demo generator path, but it uses the same lightweight schemas so CI
can run intake, workflow, bridge preparation, report export, Planner Pack, what-if,
diff, and portfolio checks quickly.

The staged `network_edges.csv` is intentionally different from straight-line proxy
travel time between zone centroids so workflow reports can exercise the routing
diagnostic that compares selected network shortest paths against the proxy method.

`tiny.graphml` plus `zone_node_map.csv` cover the GraphML routing path without
requiring OSMnx or network access in tests.
