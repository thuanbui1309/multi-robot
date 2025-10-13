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


# Scenario registry
SCENARIOS = {
    'scenario_1_simple': create_standard_simple_1_agent,
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
