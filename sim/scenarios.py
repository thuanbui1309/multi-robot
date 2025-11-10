from typing import Tuple, List, Dict, Any, Optional
from dataclasses import dataclass
from core.grid import Grid

@dataclass
class ScenarioConfig:
    """Simulation scenario configuration."""
    name: str
    description: str
    grid: Grid
    vehicle_positions: List[Tuple[int, int]]
    vehicle_batteries: List[float]
    expected_outcome: str
    step_delay: float = 0.5
    
    def get_metadata(self) -> Dict[str, Any]:
        """Get scenario metadata."""
        return {
            'name': self.name,
            'description': self.description,
            'num_agents': len(self.vehicle_positions),
            'num_stations': len(self.grid.charging_stations),
            'vehicle_configs': [
                {
                    'id': f'vehicle_{i}',
                    'position': pos,
                    'battery': self.vehicle_batteries[i]
                }
                for i, pos in enumerate(self.vehicle_positions)
            ],
            'station_configs': [
                {
                    'id': station.station_id,
                    'position': station.position,
                    'capacity': station.capacity
                }
                for station in self.grid.charging_stations
            ],
            'exit_position': self.grid.exit_position,
            'expected_outcome': self.expected_outcome,
            'step_delay': self.step_delay
        }


def create_standard_simple_1_agent() -> ScenarioConfig:
    """Baseline scenario: single vehicle charging cycle with orchestrator communication."""
    grid_str = """
        ...............
        ...............
        ...##..........
        ...##..........
        ...............
        ...............
        ...............
        ...............
        ...............
        ...............
        ...............
        ...............
    """.strip()
    
    grid = Grid.from_string(grid_str)
    
    grid.add_charging_station(5, 5, capacity=2)
    grid.add_charging_station(10, 6, capacity=2)
    
    grid.set_exit(0, 11)
    
    vehicle_positions = [(12, 1)]
    vehicle_batteries = [25.0] 
    
    return ScenarioConfig(
        name="Standard - Simple 1 Agent",
        description="""Single vehicle charging demonstration.
        
        1 vehicle at (12,1) with 25% battery requests charging.
        Orchestrator assigns optimal station based on distance.
        Vehicle navigates, charges to 95%, and exits at (0,11).""",
        grid=grid,
        vehicle_positions=vehicle_positions,
        vehicle_batteries=vehicle_batteries,
        expected_outcome="Vehicle successfully charges and exits",
        step_delay=0.5
    )


def create_multiple_agents_concurrent() -> ScenarioConfig:
    """Multiple vehicles requesting charging concurrently."""
    grid_str = """
        ....................
        ....................
        ....................
        ....####....####....
        ....#..#....#..#....
        .......#.......#....
        ....#..#....#..#....
        ....####....####....
        ....................
        ....................
        ....................
        ....................
        ....................
        ....................
        ....................
    """.strip()
    
    grid = Grid.from_string(grid_str)
    
    grid.add_charging_station(5, 5, capacity=1)
    grid.add_charging_station(14, 5, capacity=1)
    grid.add_charging_station(10, 12, capacity=1)
    
    grid.set_exit(0, 14)
    
    vehicle_positions = [(2, 2), (17, 2), (10, 8)]
    vehicle_batteries = [28.0, 26.0, 24.0]
    
    return ScenarioConfig(
        name="Multiple Agents - Concurrent Charging",
        description="""3 vehicles request charging simultaneously.
        
        Orchestrator assigns each to nearest available station.
        All vehicles navigate and charge concurrently.
        Path overlaps are acceptable in this scenario.""",
        grid=grid,
        vehicle_positions=vehicle_positions,
        vehicle_batteries=vehicle_batteries,
        expected_outcome="All 3 vehicles successfully charge and exit concurrently",
        step_delay=0.3
    )


def create_path_conflict_scenario() -> ScenarioConfig:
    """Priority-based head-on collision avoidance in narrow corridor."""
    grid_str = """.........
.........
.........
...#.#...
...#.#...
...#.#...
...#.#...
...#.#...
...#.#...
...#.#..."""
    
    grid = Grid.from_string(grid_str)
    
    grid.add_charging_station(2, 2, capacity=1)
    grid.add_charging_station(6, 2, capacity=1)
    
    grid.set_exit(4, 9)
    
    vehicle_positions = [(0, 2), (8, 2)]
    vehicle_batteries = [26.0, 26.0]
    
    return ScenarioConfig(
        name="Path Conflict - Head-On Avoidance",
        description="""2 vehicles on row 2 moving toward center in narrow corridor.
        
        vehicle_0 at (0,2) moves RIGHT to Station_0 at (2,2).
        vehicle_1 at (8,2) moves LEFT to Station_1 at (6,2).
        Priority-based collision avoidance: lower ID has priority.""",
        grid=grid,
        vehicle_positions=vehicle_positions,
        vehicle_batteries=vehicle_batteries,
        expected_outcome="Both vehicles successfully avoid collision and complete charging",
        step_delay=0.4
    )


def create_station_contention_scenario() -> ScenarioConfig:
    """Queue management when multiple vehicles compete for limited station capacity."""
    grid_str = """............
............
............
............
............
............
............
............
............
............"""
    
    grid = Grid.from_string(grid_str)
    
    grid.add_charging_station(6, 4, capacity=1)
    grid.set_exit(6, 9)
    
    vehicle_positions = [(3, 1), (10, 1), (6, 7)]
    vehicle_batteries = [28.0, 26.0, 24.0]
    
    return ScenarioConfig(
        name="Station Contention - Resource Allocation",
        description="""3 vehicles compete for 1 charging station (capacity 1).
        
        Orchestrator assigns based on distance and battery urgency.
        Vehicles queue sequentially: only 1 charges at a time.
        Optimizes assignment order to minimize total wait time.""",
        grid=grid,
        vehicle_positions=vehicle_positions,
        vehicle_batteries=vehicle_batteries,
        expected_outcome="All 3 vehicles charge sequentially at single station",
        step_delay=0.4
    )


def create_negotiation_scenario() -> ScenarioConfig:
    """Queue-based negotiation where urgent robot requests priority."""
    grid_str = """...............
...............
...............
...............
...............
...............
...............
...............
...............
...............
...............
..............."""
    
    grid = Grid.from_string(grid_str)
    
    grid.add_charging_station(6, 4, capacity=1)
    grid.set_exit(0, 11)
    
    vehicle_positions = [(2, 2), (10, 2)]
    vehicle_batteries = [25.0, 15.0]
    
    return ScenarioConfig(
        name="Queue Negotiation: 2 Robots, 1 Station",
        description="""2 vehicles negotiate queue order based on urgency.
        
        Initial: vehicle_0 (closer) gets pos 0, vehicle_1 (farther) gets pos 1.
        Negotiation: vehicle_1 has critical battery (15%), requests priority.
        Final: vehicle_1 moves to pos 0, vehicle_0 accepts pos 1.
        Execution: vehicle_1 charges first, vehicle_0 waits.""",
        grid=grid,
        vehicle_positions=vehicle_positions,
        vehicle_batteries=vehicle_batteries,
        expected_outcome="vehicle_1 negotiates to go first due to critical battery, vehicle_0 accepts waiting",
        step_delay=0.5
    )


def create_tit_for_tat_scenario() -> ScenarioConfig:
    """Tit-for-Tat behavioral negotiation with cooperative, competitive, and adaptive strategies."""
    grid_str = """............
............
............
............
............
............
............
............
............
............"""
    
    grid = Grid.from_string(grid_str)
    
    grid.add_charging_station(6, 5, capacity=1)
    grid.set_exit(6, 9)
    
    vehicle_positions = [(3, 5), (9, 5), (6, 2)]
    vehicle_batteries = [22.0, 22.0, 22.0]
    
    return ScenarioConfig(
        name="Tit-for-Tat: Behavioral Learning",
        description="""3 robots with different strategies compete for 1 station.

STRATEGIES:
• vehicle_0 (COOPERATIVE): Always accepts assignments, gets exploited
• vehicle_1 (COMPETITIVE): Always demands priority, wins initially
• vehicle_2 (TIT-FOR-TAT): Starts cooperative, mirrors opponent behavior

QUEUE BEHAVIOR:
Robots form priority queue, wait at adjacent cells (not starting positions).
Only queue_pos=0 enters station. Others wait nearby until their turn.

TIT-FOR-TAT MECHANISM:
Round 1: Cooperates (optimistic)
Round 2+: Mirrors opponents' last actions
- If exploited → retaliates
- If cooperated with → cooperates

EXPECTED DYNAMICS:
• Cooperative: Exploited, waits longest
• Competitive: Wins early, faces retaliation
• TFT: Learns patterns, achieves balance
• Multiple negotiation rounds demonstrate adaptation""",
        grid=grid,
        vehicle_positions=vehicle_positions,
        vehicle_batteries=vehicle_batteries,
        step_delay=0.8,
        expected_outcome="TFT robot learns and adapts, cooperative exploited, competitive faces retaliation, all complete charging"
    )


SCENARIOS = {
    'scenario_1_simple': create_standard_simple_1_agent,
    'scenario_2_multiple': create_multiple_agents_concurrent,
    'scenario_3_conflict': create_path_conflict_scenario,
    'scenario_4_contention': create_station_contention_scenario,
    'scenario_5_negotiation': create_negotiation_scenario,
    'scenario_6_tit_for_tat': create_tit_for_tat_scenario,
}


def get_scenario(name: str = 'scenario_1_simple') -> ScenarioConfig:
    """
    Get a scenario configuration by name.
    
    Args:
        name: Scenario identifier
        
    Returns:
        ScenarioConfig object
    """
    if name in SCENARIOS:
        return SCENARIOS[name]()
    else:
        return create_standard_simple_1_agent()


def list_scenarios() -> List[Dict[str, Any]]:
    """
    List all available scenarios with metadata.
    
    Returns:
        List of scenario metadata dictionaries
    """
    scenarios = []
    for scenario_id, scenario_func in SCENARIOS.items():
        config = scenario_func()
        metadata = config.get_metadata()
        metadata['id'] = scenario_id
        scenarios.append(metadata)
    return scenarios
