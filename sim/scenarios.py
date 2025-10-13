from typing import Tuple, List, Dict, Any, Optional
from dataclasses import dataclass
from core.grid import Grid


@dataclass
class ScenarioConfig:
    """Configuration for a simulation scenario."""
    name: str
    description: str
    grid: Grid
    vehicle_positions: List[Tuple[int, int]]
    vehicle_batteries: List[float]
    expected_outcome: str
    step_delay: float = 0.5
    
    def get_metadata(self) -> Dict[str, Any]:
        """Get scenario metadata for display."""
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
    """
        Scenario 1: Standard - Simple 1 Agent
        
        Description:
        This is the baseline scenario demonstrating the complete charging cycle for a single
        autonomous vehicle. It validates the fundamental multi-agent communication protocol
        between a vehicle agent and the orchestrator agent.
        
        Initial Configuration:
        - Grid: 15x12 simple environment with minimal obstacles
        - Agents: 1 vehicle (vehicle_0)
        - Stations: 2 charging stations with capacity 2 each
        - Exit: Bottom-left corner (0, 11)
        
        Agent Configuration:
        - vehicle_0: Position (12, 1), Battery 25% (low, needs charging)
        
        Station Configuration:
        - Station_0: Position (5, 5), Capacity 2, Accessible
        - Station_1: Position (10, 6), Capacity 2, Accessible
        
        Expected Flow:
        1. vehicle_0 detects low battery (25% < 30% threshold)
        2. vehicle_0 sends StatusUpdateMessage to orchestrator with position and battery level
        3. Orchestrator receives request, evaluates available stations
        4. Orchestrator assigns optimal station based on distance and battery level
        5. Orchestrator sends AssignmentMessage to vehicle_0 with station location
        6. vehicle_0 receives assignment, plans path using A* algorithm
        7. vehicle_0 navigates to assigned station, avoiding obstacles
        8. vehicle_0 arrives at station, begins charging (2% per tick)
        9. vehicle_0 charges to 95%, releases station
        10. vehicle_0 sends ChargingCompleteMessage to orchestrator
        11. vehicle_0 plans path to exit
        12. vehicle_0 navigates to exit and completes scenario
        
        Success Criteria:
        - Complete agent-to-agent communication logged
        - Vehicle successfully reaches assigned station
        - Battery charges to ≥95%
        - Vehicle successfully exits the area
        - No collisions or stuck states
        
        Returns:
            ScenarioConfig with complete scenario setup
    """
    # Create simple grid
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
    
    # Add charging stations
    grid.add_charging_station(5, 5, capacity=2)   # Center station
    grid.add_charging_station(10, 6, capacity=2)  # Bottom-right station
    
    # Set exit position
    grid.set_exit(0, 11)
    
    # Single vehicle with low battery that needs charging
    vehicle_positions = [(12, 1)]
    vehicle_batteries = [25.0] 
    
    return ScenarioConfig(
        name="Standard - Simple 1 Agent",
        description="""
            Single agent charging scenario demonstrating complete communication protocol.

            Initial State:
            - 1 vehicle at (12, 1) with 25% battery (below 30% threshold)
            - 2 available charging stations
            - Exit at (0, 11)

            Expected Behavior:
            1. Agent detects low battery and requests charging
            2. Orchestrator receives request and assigns optimal station
            3. Agent navigates to station using A* pathfinding
            4. Agent charges to 95%
            5. Agent notifies orchestrator of completion
            6. Agent exits the area
        """,
        grid=grid,
        vehicle_positions=vehicle_positions,
        vehicle_batteries=vehicle_batteries,
        expected_outcome="Vehicle successfully charges and exits",
        step_delay=0.5
    )


def create_multiple_agents_concurrent() -> ScenarioConfig:
    """
    Scenario 2: Multiple Agents - Concurrent Charging
    
    Description:
    This scenario demonstrates multi-agent coordination with concurrent charging requests.
    Multiple vehicles simultaneously request charging and are assigned to different stations
    based on availability and proximity. All agents operate concurrently without waiting
    for each other.
    
    Initial Configuration:
    - Grid: 20x15 environment with some obstacles
    - Agents: 3 vehicles (vehicle_0, vehicle_1, vehicle_2)
    - Stations: 3 charging stations with capacity 1 each
    - Exit: Bottom-left corner (0, 14)
    
    Agent Configuration:
    - vehicle_0: Position (2, 2), Battery 28% (needs charging)
    - vehicle_1: Position (17, 2), Battery 26% (needs charging)
    - vehicle_2: Position (10, 8), Battery 24% (needs charging)
    
    Station Configuration:
    - Station_0: Position (5, 5), Capacity 1, Accessible
    - Station_1: Position (14, 5), Capacity 1, Accessible
    - Station_2: Position (10, 12), Capacity 1, Accessible
    
    Expected Flow:
    1. All 3 vehicles detect low battery simultaneously
    2. All send charging requests to orchestrator concurrently
    3. Orchestrator receives all requests, evaluates available stations
    4. Orchestrator assigns each vehicle to nearest available station
       - Uses assignment algorithm to optimize distribution
    5. All vehicles receive assignments simultaneously
    6. All vehicles plan paths and navigate concurrently
       - May overlap on same cells (conflict accepted at this stage)
    7. All vehicles arrive at respective stations, charge to 95%
    8. All vehicles complete charging and head to exit
    9. All vehicles exit concurrently
    
    Success Criteria:
    - All 3 vehicles successfully assigned to different stations
    - No vehicle waits for another (concurrent execution)
    - All vehicles reach their assigned stations
    - All vehicles charge to ≥95%
    - All vehicles successfully exit
    - Path conflicts are acceptable (agents may overlap)
    
    Accepted Limitations:
    - Path conflicts allowed (agents can occupy same cell)
    - Assumes sufficient battery to reach assigned station
    
    Returns:
        ScenarioConfig with complete scenario setup
    """
    # Create larger grid for multiple agents
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
    
    # Add charging stations
    grid.add_charging_station(5, 5, capacity=1)   # Left station
    grid.add_charging_station(14, 5, capacity=1)  # Right station
    grid.add_charging_station(10, 12, capacity=1) # Bottom center station
    
    # Set exit position
    grid.set_exit(0, 14)
    
    # Multiple vehicles at different positions with low batteries
    vehicle_positions = [
        (2, 2),    # vehicle_0 - top left
        (17, 2),   # vehicle_1 - top right
        (10, 8),   # vehicle_2 - center
    ]
    
    vehicle_batteries = [
        28.0,  # vehicle_0 - low battery
        26.0,  # vehicle_1 - low battery
        24.0,  # vehicle_2 - low battery
    ]
    
    return ScenarioConfig(
        name="Multiple Agents - Concurrent Charging",
        description="""
        Multiple agents requesting charging simultaneously and operating concurrently.

        Initial State:
        - 3 vehicles at different positions, all with low battery (<30%)
        - 3 available charging stations
        - Exit at (0, 14)

        Vehicle Configurations:
        - vehicle_0: (2, 2) with 28% battery
        - vehicle_1: (17, 2) with 26% battery
        - vehicle_2: (10, 8) with 24% battery

        Station Configurations:
        - Station_0: (5, 5), Capacity 1
        - Station_1: (14, 5), Capacity 1
        - Station_2: (10, 12), Capacity 1

        Expected Behavior:
        1. All vehicles detect low battery and request charging concurrently
        2. Orchestrator receives all requests simultaneously
        3. Orchestrator assigns each vehicle to optimal available station
        4. All vehicles navigate to their stations concurrently
        5. All vehicles charge simultaneously
        6. All vehicles exit concurrently

        Accepted Limitations:
        - Path conflicts allowed (vehicles may overlap on same cells)
        - Assumes sufficient battery to reach assigned station

        This scenario validates concurrent multi-agent coordination and station assignment.""",
        grid=grid,
        vehicle_positions=vehicle_positions,
        vehicle_batteries=vehicle_batteries,
        expected_outcome="All 3 vehicles successfully charge and exit concurrently",
        step_delay=0.3
    )


# Scenario registry
SCENARIOS = {
    'scenario_1_simple': create_standard_simple_1_agent,
    'scenario_2_multiple': create_multiple_agents_concurrent,
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
