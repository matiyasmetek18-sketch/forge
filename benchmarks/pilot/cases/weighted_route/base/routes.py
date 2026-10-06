from collections import deque


def cheapest_route(graph, start, destination):
    queue = deque([(start, 0)])
    seen = {start}
    while queue:
        node, cost = queue.popleft()
        if node == destination:
            return cost
        for neighbor, edge_cost in graph.get(node, ()):
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append((neighbor, cost + edge_cost))
    return None
