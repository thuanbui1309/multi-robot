"""Predefined simulation scenarios."""

from typing import Tuple, List
from core.grid import Grid


def create_simple_scenario() -> Tuple[Grid, List[Tuple[int, int]], List[Tuple[int, int]]]:
    """
    Create a simple scenario with a small grid.
    All stations and vehicles are fully accessible.
    
    Returns:
        Tuple of (grid, vehicle_positions, station_positions)
    """
    grid_str = """
..........
..........
..###.....
..#.#.....
....#.....
..........
..........
..........
..........
..........
""".strip()
    
    grid = Grid.from_string(grid_str)
    
    # Add charging stations - all accessible
    grid.add_charging_station(4, 4, capacity=2)  # Center accessible
    grid.add_charging_station(8, 2, capacity=2)  # Right top
    grid.add_charging_station(8, 7, capacity=2)  # Right bottom
    
    # Set exit position (bottom-left corner)
    grid.set_exit(0, 9)
    
    # Initial vehicle positions - all can reach stations and exit
    vehicle_positions = [
        (1, 1),   # Top left
        (1, 8),   # Bottom left
        (8, 5),   # Right middle
    ]
    
    return grid, vehicle_positions, []


def create_medium_scenario() -> Tuple[Grid, List[Tuple[int, int]], List[Tuple[int, int]]]:
    """
    Create a medium-sized scenario with obstacles.
    All stations and vehicles are fully accessible.
    
    Returns:
        Tuple of (grid, vehicle_positions, station_positions)
    """
    grid_str = """
....................
....................
....####............
....#..#......####..
........#.....#..#..
....#..#..........#.
....####......####..
....................
....................
..####..............
..#..#..............
........#...........
..#..#..............
..####..............
....................
....................
""".strip()
    
    grid = Grid.from_string(grid_str)
    
    # Add accessible charging stations
    grid.add_charging_station(6, 4, capacity=2)   # Left station - accessible
    grid.add_charging_station(16, 5, capacity=2)  # Right station - accessible
    grid.add_charging_station(6, 11, capacity=2)  # Bottom left - accessible
    
    # Initial vehicle positions - all accessible
    vehicle_positions = [
        (1, 1),
        (18, 1),
        (1, 14),
        (18, 14),
        (10, 8),
    ]
    
    return grid, vehicle_positions, []


def create_large_scenario() -> Tuple[Grid, List[Tuple[int, int]], List[Tuple[int, int]]]:
    """
    Create a large complex scenario.
    
    Returns:
        Tuple of (grid, vehicle_positions, station_positions)
    """
    width, height = 30, 20
    grid = Grid(width, height)
    
    # Create walls around the edges
    for x in range(width):
        grid.set_obstacle(x, 0)
        grid.set_obstacle(x, height - 1)
    for y in range(height):
        grid.set_obstacle(0, y)
        grid.set_obstacle(width - 1, y)
    
    # Create some internal structures
    # Vertical wall with gap
    for y in range(5, 15):
        if y != 10:  # Gap
            grid.set_obstacle(10, y)
    
    # Horizontal wall with gap
    for x in range(15, 25):
        if x != 20:  # Gap
            grid.set_obstacle(x, 10)
    
    # Add charging stations in strategic locations
    grid.add_charging_station(5, 5, capacity=2)
    grid.add_charging_station(5, 15, capacity=2)
    grid.add_charging_station(25, 5, capacity=2)
    grid.add_charging_station(25, 15, capacity=2)
    grid.add_charging_station(15, 10, capacity=3)
    
    # Initial vehicle positions
    vehicle_positions = [
        (2, 2),
        (2, 17),
        (27, 2),
        (27, 17),
        (15, 2),
        (15, 17),
    ]
    
    return grid, vehicle_positions, []


def create_stress_test_scenario() -> Tuple[Grid, List[Tuple[int, int]], List[Tuple[int, int]]]:
    """
    Create a stress test scenario with many vehicles and limited stations.
    All stations and vehicles are fully accessible.
    
    Returns:
        Tuple of (grid, vehicle_positions, station_positions)
    """
    width, height = 40, 30
    grid = Grid(width, height)
    
    # Create a maze-like structure with guaranteed passages
    for x in range(0, width, 6):
        for y in range(2, height - 2):
            if y % 5 != 0:  # Leave gaps every 5 rows
                grid.set_obstacle(x, y)
    
    # Add charging stations in accessible open areas
    grid.add_charging_station(3, 15, capacity=3)   # Left center
    grid.add_charging_station(18, 10, capacity=2)  # Center
    grid.add_charging_station(33, 20, capacity=2)  # Right lower
    grid.add_charging_station(15, 25, capacity=2)  # Lower center
    
    # Many vehicle positions - all in accessible areas
    vehicle_positions = [
        (3, 3), (9, 3), (15, 3), (21, 3), (27, 3),
        (3, 10), (9, 10), (15, 10), (21, 10), (27, 10),
        (3, 20), (9, 20), (15, 20), (21, 20), (27, 20),
    ]
    
    return grid, vehicle_positions, []


def create_custom_scenario(
    width: int,
    height: int,
    num_stations: int = 3,
    num_vehicles: int = 5
) -> Tuple[Grid, List[Tuple[int, int]], List[Tuple[int, int]]]:
    """
    Create a custom scenario.
    
    Args:
        width: Grid width
        height: Grid height
        num_stations: Number of charging stations
        num_vehicles: Number of vehicles
    
    Returns:
        Tuple of (grid, vehicle_positions, station_positions)
    """
    import random
    
    grid = Grid(width, height)
    
    # Add some random obstacles (20% of cells)
    num_obstacles = int(width * height * 0.2)
    for _ in range(num_obstacles):
        x = random.randint(0, width - 1)
        y = random.randint(0, height - 1)
        grid.set_obstacle(x, y)
    
    # Add charging stations
    for _ in range(num_stations):
        placed = False
        attempts = 0
        while not placed and attempts < 100:
            x = random.randint(0, width - 1)
            y = random.randint(0, height - 1)
            if grid.is_walkable(x, y):
                grid.add_charging_station(x, y, capacity=2)
                placed = True
            attempts += 1
    
    # Generate vehicle positions
    vehicle_positions = []
    for _ in range(num_vehicles):
        placed = False
        attempts = 0
        while not placed and attempts < 100:
            x = random.randint(0, width - 1)
            y = random.randint(0, height - 1)
            if grid.is_walkable(x, y) and (x, y) not in vehicle_positions:
                vehicle_positions.append((x, y))
                placed = True
            attempts += 1
    
    return grid, vehicle_positions, []


# Scenario registry
SCENARIOS = {
    'simple': create_simple_scenario,
    'medium': create_medium_scenario,
    'large': create_large_scenario,
    'stress': create_stress_test_scenario,
}


def get_scenario(name: str = 'simple'):
    """Get a scenario by name."""
    if name in SCENARIOS:
        return SCENARIOS[name]()
    else:
        return create_simple_scenario()
