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


def create_path_conflict_scenario() -> ScenarioConfig:
    """
    Scenario 3: Path Conflict - Head-On Collision Avoidance
    
    Description:
    This scenario demonstrates priority-based conflict resolution when two robots
    encounter each other head-on in a narrow corridor. It validates the collision
    avoidance mechanism using robot ID-based priorities.
    
    Initial Configuration:
    - Grid: 9x10 (9 columns, 10 rows) with vertical wall barriers
    - Agents: 2 vehicles (vehicle_0 and vehicle_1)
    - Stations: 2 charging stations on row 2 between walls
    - Exit: Center bottom (4, 9)
    
    Agent Configuration:
    - vehicle_0: Position (0, 2), Battery 28% (low, needs charging)
      Target: Station_0 at (2, 2) - must travel RIGHT (2 steps on row 2)
    - vehicle_1: Position (8, 2), Battery 26% (low, needs charging)
      Target: Station_1 at (6, 2) - must travel LEFT (2 steps on row 2)
    
    Station Configuration:
    - Station_0: Position (2, 2), Capacity 1 - Left-center of row 2
    - Station_1: Position (6, 2), Capacity 1 - Right-center of row 2
    
    Conflict Setup:
    Both vehicles are on the SAME ROW (row 2) and must move toward the center.
    vehicle_0 moves from (0,2) → (1,2) → (2,2) [Station_0]
    vehicle_1 moves from (8,2) → (7,2) → (6,2) [Station_1]
    They will approach each other and may conflict near the center columns.
    
    Conflict Resolution Mechanism (Priority-Based):
    1. When vehicles detect potential collision (same cell or adjacent cells)
    2. Vehicle with HIGHER ID (vehicle_1) has LOWER priority
    3. Lower priority vehicle WAITS while higher priority vehicle passes
    4. This creates asymmetric behavior preventing deadlock
    
    Expected Flow:
    1. Both vehicles detect low battery and request charging
    2. Orchestrator assigns vehicle_0 → Station_0 at (2,2)
    3. Orchestrator assigns vehicle_1 → Station_1 at (6,2)
    4. Both vehicles plan straight-line paths along ROW 2
    5. Both start moving toward each other on row 2:
       - vehicle_0: (0,2) → (1,2) → (2,2)
       - vehicle_1: (8,2) → (7,2) → (6,2)
    6. If they get close during movement, collision detection activates
    7. vehicle_1 (higher ID = lower priority) may WAIT if needed
    8. vehicle_0 (lower ID = higher priority) proceeds
    9. Both reach their stations and charge to 95%+
    10. Both navigate downward through wall corridors to exit at (4,9)
    11. Mission complete
    
    Success Criteria:
    - No collisions occur (vehicles never occupy same cell simultaneously)
    - Lower priority vehicle successfully yields
    - Both vehicles reach their assigned stations
    - Both vehicles charge and exit successfully
    - Conflict resolution is logged
    
    Returns:
        ScenarioConfig with conflict scenario setup
    """
    # Create grid with narrow corridor
    # Design: 9x10 map with narrow corridor forcing head-on collision
    # Layout based on user diagram:
    # Row 0: Empty row
    # Row 1: Empty row  
    # Row 2: Vehicles at (0,2) and (8,2), Stations at (2,2) and (6,2)
    # Rows 3-9: Two vertical walls at columns 3 and 5
    # Row 9: Exit at (4,9) between the two walls
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
    
    # Add charging stations at RED positions (row 2)
    grid.add_charging_station(2, 2, capacity=1)  # Station_0 at LEFT-CENTER
    grid.add_charging_station(6, 2, capacity=1)  # Station_1 at RIGHT-CENTER
    
    # Set exit at GREEN position (center bottom, row 9)
    grid.set_exit(4, 9)
    
    # Vehicle positions at YELLOW positions (row 2, far left and far right)
    vehicle_positions = [
        (0, 2),   # vehicle_0 starts at FAR LEFT - needs Station_0 at (2,2)
        (8, 2),   # vehicle_1 starts at FAR RIGHT - needs Station_1 at (6,2)
    ]
    
    # Low batteries to force charging
    vehicle_batteries = [
        26.0,  # vehicle_0 - needs to move RIGHT from (0,0) to (2,0)
        26.0,  # vehicle_1 - needs to move LEFT from (8,0) to (6,0)
    ]
    
    return ScenarioConfig(
        name="Path Conflict - Head-On Avoidance",
        description="""
        Two robots on row 2 moving toward center stations with wall barriers.

        Map Layout (9x10):
        - Rows 0-1: Empty
        - Row 2: Vehicle start positions at (0,2) and (8,2), Stations at (2,2) and (6,2)
        - Rows 3-9: Two vertical walls at columns 3 and 5
        - Row 9: Exit at center (4,9) between walls

        Vehicle Configurations:
        - vehicle_0: (0, 2) with 28% battery → Station_0 at (2, 2) [2 steps RIGHT]
        - vehicle_1: (8, 2) with 26% battery → Station_1 at (6, 2) [2 steps LEFT]

        Station Configurations:
        - Station_0: (2, 2), Capacity 1 - Left-center
        - Station_1: (6, 2), Capacity 1 - Right-center

        Conflict Resolution:
        - Both on SAME ROW (row 2)
        - Move toward center on row 2
        - Priority based on vehicle ID
        - vehicle_0 (ID=0, higher priority) proceeds
        - vehicle_1 (ID=1, lower priority) waits if needed

        Expected Behavior:
        1. Both request charging simultaneously
        2. Orchestrator assigns nearby stations
        3. Both move toward center on row 2
        4. Priority-based resolution if they get too close
        5. Both reach stations, charge to 95%+
        6. Navigate downward through corridors to exit
        7. Exit at (4,9)

        This scenario validates collision avoidance in a constrained environment.""",
        grid=grid,
        vehicle_positions=vehicle_positions,
        vehicle_batteries=vehicle_batteries,
        expected_outcome="Both vehicles successfully avoid collision and complete charging",
        step_delay=0.4  # Slower to observe conflict resolution
    )


def create_station_contention_scenario() -> ScenarioConfig:
    """
    Scenario 4: Charging Station Contention (Limited Capacity)
    
    Description:
    This scenario demonstrates intelligent queueing and resource allocation when multiple
    vehicles compete for limited charging station capacity. The orchestrator must optimize
    assignments to minimize wait time and maximize throughput.
    
    Initial Configuration:
    - Grid: 12x10 simple environment
    - Agents: 3 vehicles (vehicle_0, vehicle_1, vehicle_2)
    - Stations: 1 charging station with capacity 1 (only 1 vehicle at a time)
    - Exit: Bottom center (6, 9)
    
    Agent Configuration:
    - vehicle_0: Position (2, 1), Battery 28% (low, needs charging)
    - vehicle_1: Position (10, 1), Battery 26% (low, needs charging)
    - vehicle_2: Position (6, 7), Battery 24% (low, needs charging)
    
    Station Configuration:
    - Station_0: Position (6, 4), Capacity 1 - CENTER position
    
    Challenge:
    All 3 vehicles need charging, but only 1 can charge at a time.
    The orchestrator must:
    1. Assign vehicles based on distance and battery urgency
    2. Queue vehicles when station is occupied
    3. Reassign waiting vehicles once station becomes available
    4. Optimize total charging time
    
    Expected Flow:
    1. All 3 vehicles detect low battery and request charging
    2. Orchestrator evaluates: distance + battery urgency
    3. Orchestrator assigns FIRST vehicle to station (e.g., closest or most urgent)
    4. Other vehicles wait (IDLE state, no assignment yet)
    5. First vehicle arrives, charges, and notifies orchestrator when complete
    6. Orchestrator receives ChargingCompleteMessage
    7. Orchestrator immediately assigns SECOND vehicle
    8. Second vehicle charges and completes
    9. Orchestrator assigns THIRD vehicle
    10. Third vehicle charges and completes
    11. All vehicles navigate to exit sequentially
    
    Success Criteria:
    - Only 1 vehicle occupies station at a time
    - No collisions at station
    - All vehicles get assigned and charged
    - Orchestrator optimizes assignment order
    - Total time is minimized
    - Queue management is efficient
    
    Key Observations:
    - Orchestrator tracks station.occupied_slots
    - Orchestrator only assigns when station has capacity
    - Vehicles notify orchestrator on charging completion
    - Assignment algorithm considers distance + battery level
    
    Returns:
        ScenarioConfig with station contention setup
    """
    # Create simple grid
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
    
    # Add SINGLE charging station with capacity 1 (CENTER position)
    grid.add_charging_station(6, 4, capacity=1)
    
    # Set exit
    grid.set_exit(6, 9)
    
    # 3 vehicles at different positions, all need charging
    vehicle_positions = [
        (2, 1),   # vehicle_0 - top left
        (10, 1),  # vehicle_1 - top right
        (6, 7),   # vehicle_2 - bottom center (closest to station)
    ]
    
    # All have low batteries
    vehicle_batteries = [
        28.0,  # vehicle_0 - needs charging
        26.0,  # vehicle_1 - needs charging (lower, more urgent)
        24.0,  # vehicle_2 - needs charging (lowest, most urgent + closest)
    ]
    
    return ScenarioConfig(
        name="Station Contention - Resource Allocation",
        description="""
        Three vehicles competing for single charging station with capacity 1.

        Map Layout (12x10):
        - Simple open environment
        - 1 charging station at center (6, 4)
        - Exit at bottom center (6, 9)

        Vehicle Configurations:
        - vehicle_0: (2, 1) with 28% battery - Top left
        - vehicle_1: (10, 1) with 26% battery - Top right
        - vehicle_2: (6, 7) with 24% battery - Bottom center (CLOSEST)

        Station Configuration:
        - Station_0: (6, 4), Capacity 1 - CENTER
        - Only 1 vehicle can charge at a time

        Challenge:
        All vehicles need charging simultaneously, but station can only serve one.
        
        Orchestrator Strategy:
        1. Evaluates all requests using assignment algorithm
        2. Considers: distance to station + battery urgency
        3. Assigns optimal vehicle first (likely vehicle_2: closest + most urgent)
        4. Queues other vehicles (no assignment yet)
        5. Waits for ChargingCompleteMessage
        6. Assigns next vehicle from queue
        7. Repeats until all vehicles charged

        Expected Order (by algorithm):
        1. vehicle_2 charges first (closest + lowest battery)
        2. vehicle_1 or vehicle_0 next (based on distance/battery)
        3. Remaining vehicle last

        Success Criteria:
        - No station overcrowding (max 1 vehicle)
        - All vehicles eventually charge
        - Efficient queue management
        - Optimized assignment order

        This scenario validates resource contention handling and queueing logic.""",
        grid=grid,
        vehicle_positions=vehicle_positions,
        vehicle_batteries=vehicle_batteries,
        expected_outcome="All 3 vehicles charge sequentially at single station",
        step_delay=0.4
    )


def create_negotiation_scenario() -> ScenarioConfig:
    """
    Scenario 5: Queue-Based Assignment Negotiation - Simple 2 Robots, 1 Station
    
    Description:
    This scenario demonstrates clear queue-based negotiation where the robot assigned
    to wait (position 1) will negotiate to go first (position 0) based on higher urgency.
    
    NEGOTIATION FLOW:
    
    Phase 1: Initial Assignment (Distance-Based)
    - Orchestrator assigns based on distance to station
    - vehicle_0: Position (2, 2), Battery 20%, Distance to Station = 4
      → Initially assigned Queue Position 0 (closer)
    - vehicle_1: Position (10, 2), Battery 15%, Distance to Station = 6  
      → Initially assigned Queue Position 1 (farther)
    
    Phase 2: Negotiation
    - vehicle_1 has CRITICAL battery (15%) but assigned to wait
    - vehicle_1 negotiates: "I have critical battery (15%), need to go first!"
    - vehicle_0 has better battery (20%) and is willing to wait
    
    Phase 3: Re-assignment After Negotiation
    - Orchestrator evaluates: vehicle_1 urgency (15% battery) > vehicle_0 urgency (20% battery)
    - Queue order SWAPPED:
      * vehicle_1 → Queue Position 0 (goes first due to critical battery)
      * vehicle_0 → Queue Position 1 (waits, has safer battery level)
    
    Phase 4: Consensus & Execution
    - Both vehicles accept new assignments
    - vehicle_1 moves to station first
    - vehicle_0 waits until vehicle_1 completes charging
    
    Initial Configuration:
    - Grid: 15x12 environment
    - Agents: 2 vehicles
    - Station: 1 station with capacity 2 (allows queuing)
    - Exit: Bottom left (0, 11)
    
    Agent Configuration:
    - vehicle_0: Position (2, 2), Battery 25% (LOW) - Close to station, safer battery
    - vehicle_1: Position (10, 2), Battery 15% (CRITICAL) - Far from station, critical battery
    
    Station Configuration:
    - Station_0: Position (6, 4), Capacity 2
    
    Expected Flow:
    1. Initial: vehicle_0 → pos 0 (closer), vehicle_1 → pos 1 (farther)
    2. Negotiate: vehicle_1 requests pos 0 due to critical battery
    3. Final: vehicle_1 → pos 0 (critical), vehicle_0 → pos 1 (safer)
    4. Execute: vehicle_1 goes first, vehicle_0 waits
    
    Returns:
        ScenarioConfig with queue-based negotiation scenario setup
    """
    # Create grid
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
    
    # One station with capacity 2 (allows queuing)
    grid.add_charging_station(6, 4, capacity=1)  # Station_0 - Center
    
    # Set exit
    grid.set_exit(0, 11)
    
    # 2 vehicles positioned to create clear negotiation scenario
    vehicle_positions = [
        (2, 2),   # vehicle_0 - Close to station, distance = 4 + 2 = 6
        (10, 2),  # vehicle_1 - Far from station, distance = 4 + 2 = 6 (but with critical battery)
    ]
    
    # Battery levels: vehicle_1 has CRITICAL battery, vehicle_0 has LOW battery
    # This should trigger negotiation: vehicle_1 will want to go first despite being farther
    vehicle_batteries = [
        25.0,  # vehicle_0 - LOW (safer, can wait - above 20% threshold)
        15.0,  # vehicle_1 - CRITICAL (needs to go first! - below 20% threshold)
    ]
    
    return ScenarioConfig(
        name="Queue Negotiation: 2 Robots, 1 Station",
        description="""
        Simple negotiation scenario showing queue order change.

        INITIAL ASSIGNMENT (Distance-Based):
        - vehicle_0: (2,2), Battery 25%, Distance=6 → Queue Position 0
        - vehicle_1: (10,2), Battery 15%, Distance=6 → Queue Position 1

        NEGOTIATION:
        - vehicle_1 has CRITICAL battery (15% < 20%) but assigned to wait (pos 1)
        - vehicle_1 negotiates: "Critical battery! Need to go first!"
        - vehicle_0 has safer battery (25% > 20%) and accepts waiting
        - Orchestrator re-evaluates based on urgency

        FINAL ASSIGNMENT (After Negotiation):
        - vehicle_1: Queue Position 0 (critical battery wins)
        - vehicle_0: Queue Position 1 (safer battery, can wait)

        EXECUTION:
        - vehicle_1 moves to station first
        - vehicle_0 waits until vehicle_1 completes charging
        - Both eventually charge and exit

        Watch for:
        1. Initial assignment based on distance (both equal distance)
        2. vehicle_1 negotiation message (critical battery claim)
        3. Queue order swap (pos 0 ↔ pos 1)
        4. vehicle_1 moves first, vehicle_0 waits
        """,
        grid=grid,
        vehicle_positions=vehicle_positions,
        vehicle_batteries=vehicle_batteries,
        expected_outcome="vehicle_1 negotiates to go first due to critical battery, vehicle_0 accepts waiting",
        step_delay=0.5
    )


# Scenario registry
SCENARIOS = {
    'scenario_1_simple': create_standard_simple_1_agent,
    'scenario_2_multiple': create_multiple_agents_concurrent,
    'scenario_3_conflict': create_path_conflict_scenario,
    'scenario_4_contention': create_station_contention_scenario,
    'scenario_5_negotiation': create_negotiation_scenario,
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
