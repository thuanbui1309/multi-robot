import heapq
from typing import List, Tuple, Optional, Set, Callable
from dataclasses import dataclass, field

@dataclass(order=True)
class Node:
    """Node for A* search."""
    f_score: float
    position: Tuple[int, int] = field(compare=False)
    g_score: float = field(compare=False)
    h_score: float = field(compare=False)
    parent: Optional[Tuple[int, int]] = field(default=None, compare=False)


def manhattan_distance(pos1: Tuple[int, int], pos2: Tuple[int, int]) -> float:
    """Calculate Manhattan distance between two positions."""
    return abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1])


def euclidean_distance(pos1: Tuple[int, int], pos2: Tuple[int, int]) -> float:
    """Calculate Euclidean distance between two positions."""
    return ((pos1[0] - pos2[0]) ** 2 + (pos1[1] - pos2[1]) ** 2) ** 0.5


class AStarPlanner:
    """A* pathfinding planner."""
    
    def __init__(
        self,
        heuristic: Callable[[Tuple[int, int], Tuple[int, int]], float] = manhattan_distance
    ):
        """
        Initialize A* planner.
        
        Args:
            heuristic: Heuristic function for A*
        """
        self.heuristic = heuristic
    
    def plan(
        self,
        start: Tuple[int, int],
        goal: Tuple[int, int],
        is_walkable: Callable[[int, int], bool],
        get_neighbors: Callable[[int, int], List[Tuple[int, int]]],
        blocked_cells: Optional[Set[Tuple[int, int]]] = None
    ) -> Tuple[List[Tuple[int, int]], float]:
        """
        Find shortest path from start to goal using A*.
        
        Args:
            start: Starting position
            goal: Goal position
            is_walkable: Function to check if a position is walkable
            get_neighbors: Function to get neighboring positions
            blocked_cells: Set of temporarily blocked cells
        
        Returns:
            Tuple of (path, cost). Path is empty if no path found.
        """
        if start == goal:
            return [start], 0.0
        
        if not is_walkable(goal[0], goal[1]):
            return [], float('inf')
        
        blocked_cells = blocked_cells or set()
        
        # Initialize
        open_set = []
        closed_set = set()
        g_scores = {start: 0.0}
        came_from = {}
        
        h_start = self.heuristic(start, goal)
        start_node = Node(
            f_score=h_start,
            position=start,
            g_score=0.0,
            h_score=h_start,
            parent=None
        )
        heapq.heappush(open_set, start_node)
        
        while open_set:
            current = heapq.heappop(open_set)
            current_pos = current.position
            
            if current_pos in closed_set:
                continue
            
            # Goal reached
            if current_pos == goal:
                return self._reconstruct_path(came_from, current_pos), current.g_score
            
            closed_set.add(current_pos)
            
            # Explore neighbors
            for neighbor_pos in get_neighbors(current_pos[0], current_pos[1]):
                if neighbor_pos in closed_set:
                    continue
                
                # Skip blocked cells (unless it's the goal)
                if neighbor_pos in blocked_cells and neighbor_pos != goal:
                    continue
                
                # Calculate tentative g score
                tentative_g = current.g_score + 1.0  # Assuming uniform cost
                
                # If this path to neighbor is better
                if neighbor_pos not in g_scores or tentative_g < g_scores[neighbor_pos]:
                    g_scores[neighbor_pos] = tentative_g
                    h_score = self.heuristic(neighbor_pos, goal)
                    f_score = tentative_g + h_score
                    
                    came_from[neighbor_pos] = current_pos
                    
                    neighbor_node = Node(
                        f_score=f_score,
                        position=neighbor_pos,
                        g_score=tentative_g,
                        h_score=h_score,
                        parent=current_pos
                    )
                    heapq.heappush(open_set, neighbor_node)
        
        # No path found
        return [], float('inf')
    
    def _reconstruct_path(
        self,
        came_from: dict,
        current: Tuple[int, int]
    ) -> List[Tuple[int, int]]:
        """Reconstruct path from came_from dictionary."""
        path = [current]
        while current in came_from:
            current = came_from[current]
            path.append(current)
        path.reverse()
        return path


def smooth_path(path: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """
    Smooth path by removing unnecessary waypoints.
    
    Args:
        path: Original path
    
    Returns:
        Smoothed path
    """
    if len(path) <= 2:
        return path
    
    smoothed = [path[0]]
    i = 0
    
    while i < len(path) - 1:
        j = len(path) - 1
        while j > i + 1:
            # Check if we can go directly from path[i] to path[j]
            if _is_line_of_sight(path[i], path[j], path):
                smoothed.append(path[j])
                i = j
                break
            j -= 1
        else:
            i += 1
            if i < len(path):
                smoothed.append(path[i])
    
    return smoothed


def _is_line_of_sight(
    p1: Tuple[int, int],
    p2: Tuple[int, int],
    path: List[Tuple[int, int]]
) -> bool:
    """Check if there's line of sight between two points in path."""
    # Simple check: all intermediate points should be in path
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    steps = max(abs(dx), abs(dy))
    
    if steps == 0:
        return True
    
    for i in range(1, steps):
        x = p1[0] + (dx * i) // steps
        y = p1[1] + (dy * i) // steps
        if (x, y) not in path:
            return False
    
    return True
