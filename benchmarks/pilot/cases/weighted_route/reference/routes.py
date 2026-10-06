import heapq


def cheapest_route(graph, start, destination):
    queue = [(0, start)]
    best = {start: 0}
    while queue:
        cost, node = heapq.heappop(queue)
        if cost != best[node]:
            continue
        if node == destination:
            return cost
        for neighbor, edge_cost in graph.get(node, ()):
            new_cost = cost + edge_cost
            if new_cost < best.get(neighbor, float("inf")):
                best[neighbor] = new_cost
                heapq.heappush(queue, (new_cost, neighbor))
    return None
