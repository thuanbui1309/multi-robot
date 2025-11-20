# Multi-Robot Charging Coordination System

## Table of Contents

1. [Project Overview](#project-overview)
2. [System Architecture](#system-architecture)
3. [Core Components](#core-components)
4. [Algorithms and Mechanisms](#algorithms-and-mechanisms)
5. [Scenario Descriptions](#scenario-descriptions)
6. [Installation and Usage](#installation-and-usage)
7. [Technical Details](#technical-details)
8. [Research Context](#research-context)

---

## Project Overview

### What This Project Does

This project implements a **multi-agent simulation system** for autonomous robot charging coordination. It models a fleet of battery-powered robots operating in a shared environment with limited charging infrastructure. The system addresses the challenge of **resource allocation under scarcity** through intelligent coordination, negotiation, and behavioral strategies.

### Problem Statement

In multi-robot systems, autonomous agents must efficiently share limited resources (charging stations) while maintaining operational continuity. Key challenges include:

- **Resource Contention**: Multiple robots competing for limited charging capacity
- **Path Conflicts**: Robots navigating shared spaces without collisions
- **Priority Determination**: Deciding which robot should charge first based on urgency
- **Behavioral Diversity**: Different agents employing different negotiation strategies
- **Fairness vs. Efficiency**: Balancing individual needs with system-wide optimization

### Motivation

This project addresses critical problems in:

1. **Autonomous Fleet Management**: Warehouse robots, delivery drones, autonomous vehicles
2. **Smart Infrastructure**: Electric vehicle charging networks, shared mobility systems
3. **Game Theory Applications**: Demonstrating cooperative and competitive strategies in multi-agent systems
4. **Distributed Systems**: Decentralized decision-making without global coordination
5. **Real-Time Coordination**: Dynamic resource allocation in time-sensitive environments

### Core Capabilities

- **A* Pathfinding**: Optimal path planning in grid environments with obstacles
- **Collision Avoidance**: Priority-based and reservation-based conflict resolution
- **Orchestrator-Agent Communication**: Message-passing protocol for assignments and status updates
- **Queue Management**: FIFO and negotiation-based queue systems for station access
- **Behavioral Strategies**: Cooperative, competitive, and tit-for-tat negotiation patterns
- **Real-Time Visualization**: Web-based interface with live simulation monitoring
- **Performance Metrics**: Comprehensive tracking of efficiency, fairness, and system utilization

---

## System Architecture

### High-Level Design

```
┌─────────────────────────────────────────────────────────────┐
│                     Mesa Framework                          │
│  (Multi-Agent Simulation Engine)                           │
└─────────────────────────────────────────────────────────────┘
                          │
        ┌─────────────────┴─────────────────┐
        │                                   │
┌───────▼────────┐                 ┌────────▼────────┐
│   Orchestrator │◄────Messages────►│   Vehicles      │
│     Agent      │                 │   (Fleet)       │
└───────┬────────┘                 └────────┬────────┘
        │                                   │
        │         ┌─────────────────────────┘
        │         │
┌───────▼─────────▼───────┐
│   Environment Grid      │
│ • Charging Stations     │
│ • Obstacles             │
│ • Exit Points           │
│ • Reservation Table     │
└─────────────────────────┘
        │
┌───────▼─────────────────┐
│  Web Visualization      │
│  (FastAPI + WebSocket)  │
└─────────────────────────┘
```

### Component Interaction Flow

1. **Initialization**: Grid loaded, vehicles and orchestrator spawned
2. **Status Updates**: Vehicles broadcast battery/position to orchestrator
3. **Assignment**: Orchestrator computes optimal station assignments
4. **Path Planning**: Vehicles calculate A* paths to assigned stations
5. **Collision Avoidance**: Vehicles check reservations and priority rules
6. **Movement**: Vehicles navigate toward targets while avoiding conflicts
7. **Charging**: Vehicles occupy station slots and recharge batteries
8. **Queue Management**: Waiting vehicles form queues at full stations
9. **Negotiation** (optional): Vehicles dispute assignments based on strategy
10. **Completion**: Vehicles exit after charging completes

---

## Core Components

### 1. Agents

#### VehicleAgent (`agents/vehicle.py`)

**Purpose**: Base class for autonomous vehicles with pathfinding and charging capabilities.

**Key Features**:
- **A* Pathfinding**: Computes optimal paths using Manhattan or Euclidean heuristics
- **Battery Management**: Tracks battery level with configurable drain/charge rates
- **State Machine**: Manages states (IDLE, MOVING, CHARGING, WAITING, EXITING)
- **Collision Avoidance**: Priority-based rules (lower ID yields to higher ID)
- **Message Protocol**: Sends status updates and receives assignments

**Attributes**:
```python
position: Tuple[int, int]           # Current grid position
battery_level: float                # Current battery (0-100%)
path: List[Tuple[int, int]]        # Planned path to destination
state: VehicleStatus               # Current operational state
assigned_station_id: Optional[int] # Assigned charging station
```

**Critical Methods**:
- `plan_path(start, goal, grid)`: Compute A* path
- `move()`: Execute one movement step along path
- `charge()`: Increase battery at charging station
- `check_collision(next_pos)`: Verify if movement is safe

#### NegotiatingVehicle (`agents/negotiating_vehicle.py`)

**Purpose**: Extended vehicle with negotiation and queue awareness.

**Additional Features**:
- **Queue Position Tracking**: Knows its position in station queues
- **Counter-Proposals**: Can reject assignments and propose alternatives
- **Urgency Calculation**: Computes priority based on battery criticality
- **Collision Detection**: Enhanced logic for queue waiting positions

**Queue Behavior**:
- `queue_pos = 0`: Allowed to enter station
- `queue_pos > 0`: Wait at adjacent cell until queue advances

#### TitForTatVehicle (`agents/tit_for_tat_vehicle.py`)

**Purpose**: Implements game-theoretic behavioral strategies.

**Strategies**:
1. **COOPERATIVE**: Always accepts assignments (unconditional cooperator)
2. **COMPETITIVE**: Always demands priority (unconditional defector)
3. **TIT_FOR_TAT**: Mirrors opponent's last action (conditional cooperator)

**Memory System**:
```python
opponent_history: Dict[str, List[str]]  # Track opponent actions
our_action_history: Dict[str, List[str]]  # Track our responses
```

**Decision Logic**:
- Round 1: Cooperate (optimistic start)
- Round N: If opponent cooperated last time → Cooperate, else → Defect

#### OrchestratorAgent (`agents/orchestrator.py`)

**Purpose**: Central coordinator managing assignments and conflicts.

**Responsibilities**:
- Monitor vehicle battery levels and positions
- Track charging station capacity and load
- Compute optimal vehicle-station assignments
- Handle assignment rejections and re-assignments
- Broadcast assignment messages to vehicles

**Assignment Algorithm** (Hungarian Method):
- Constructs cost matrix: `cost = distance_weight × distance + battery_weight × (100 - battery) + load_weight × station_load`
- Uses linear sum assignment to minimize total cost
- Assigns each vehicle to optimal available station

#### NegotiatingOrchestrator (`agents/negotiating_orchestrator.py`)

**Purpose**: Queue-based orchestrator with negotiation support.

**Additional Features**:
- **Queue Management**: Maintains FIFO queues for each station
- **Negotiation Rounds**: Processes disputes and counter-proposals
- **Dynamic Re-ordering**: Adjusts queue based on accepted negotiations

#### TitForTatOrchestrator (`agents/tit_for_tat_orchestrator.py`)

**Purpose**: Tracks behavioral statistics for strategy analysis.

**Analytics**:
- Counts cooperations/defections per vehicle
- Tracks negotiation outcomes (accepted/rejected)
- Records interaction patterns between vehicles

### 2. Core Systems

#### Grid (`core/grid.py`)

**Purpose**: Represents the 2D environment with obstacles, stations, and exit points.

**Structure**:
```python
class Grid:
    cells: List[List[Cell]]          # 2D array of cells
    charging_stations: List[ChargingStation]
    exit_position: Tuple[int, int]
    width: int
    height: int
```

**Cell Types**:
- `.` : Empty (walkable)
- `#` : Obstacle (blocked)
- `C` : Charging station
- `E` : Exit point

**Methods**:
- `from_string(grid_str)`: Parse ASCII grid representation
- `add_charging_station(x, y, capacity)`: Create charging point
- `is_walkable(x, y)`: Check if position is traversable
- `get_neighbors(x, y)`: Return adjacent cells for pathfinding

#### AStarPlanner (`core/planner.py`)

**Purpose**: Implements A* pathfinding algorithm.

**Algorithm**:
```
1. Initialize open_set = [start], closed_set = []
2. While open_set not empty:
   a. Get node with lowest f_score = g_score + h_score
   b. If node == goal: reconstruct path and return
   c. For each neighbor:
      - Calculate tentative g_score
      - If better than previous: update parent and scores
3. Return empty path if no solution
```

**Heuristics**:
- **Manhattan Distance**: `|x1 - x2| + |y1 - y2|` (grid with 4-way movement)
- **Euclidean Distance**: `√((x1-x2)² + (y1-y2)²)` (diagonal movement)

**Features**:
- Dynamic obstacle avoidance
- Cost-weighted pathfinding
- Configurable heuristic functions

#### ReservationTable (`core/reservation.py`)

**Purpose**: Spatial-temporal conflict resolution system.

**Concept**: Each vehicle reserves grid cells at specific time steps to prevent collisions.

**Data Structure**:
```python
reservations: Dict[time_step, Dict[position, vehicle_id]]
vehicle_reservations: Dict[vehicle_id, Dict[time_step, position]]
```

**Operations**:
- `reserve(position, time_step, vehicle_id)`: Claim cell at time
- `reserve_path(path, start_time, vehicle_id)`: Reserve entire path
- `is_reserved(position, time_step)`: Check for conflicts
- `clear_old_reservations(current_time)`: Cleanup past reservations

#### VehicleStationAssigner (`core/assign.py`)

**Purpose**: Optimal assignment using Hungarian algorithm (linear sum assignment).

**Cost Function**:
```python
cost[i][j] = (distance_weight × distance(vehicle_i, station_j) +
              battery_weight × (100 - battery_i) +
              load_weight × station_j.load)
```

**Optimization**: Minimizes total system cost across all assignments.

**Libraries**: Uses `scipy.optimize.linear_sum_assignment` for O(n³) optimal matching.

#### SimulationMetrics (`core/metrics.py`)

**Purpose**: Collect performance and efficiency data.

**Tracked Metrics**:
- Per-vehicle: Distance traveled, charging time, waiting time, replans
- Per-station: Utilization rate, queue lengths, idle time
- System-wide: Total conflicts, average efficiency, fairness index

**Output**: JSON summaries for analysis and visualization.

### 3. Simulation Model

#### ChargingModel (`sim/model.py`)

**Purpose**: Mesa-based simulation orchestrating all agents and systems.

**Components**:
- **OrderedScheduler**: Ensures vehicles step before orchestrator each tick
- **Grid**: Environment representation
- **ReservationTable**: Collision prevention system
- **Metrics Collector**: Performance tracking
- **Message Queue**: Inter-agent communication

**Execution Cycle**:
```python
def step():
    1. All vehicles execute step()
       - Update battery
       - Send status messages
       - Plan/execute movement
    2. Orchestrator executes step()
       - Process status messages
       - Compute assignments
       - Send assignment messages
    3. Update metrics
    4. Check termination conditions
```

#### ScenarioConfig (`sim/scenarios.py`)

**Purpose**: Defines pre-configured simulation scenarios.

**Structure**:
```python
@dataclass
class ScenarioConfig:
    name: str                          # Scenario identifier
    description: str                   # Detailed explanation
    grid: Grid                         # Environment layout
    vehicle_positions: List[Tuple]     # Starting positions
    vehicle_batteries: List[float]     # Initial battery levels
    expected_outcome: str              # Test oracle
    step_delay: float                  # Visualization speed
```

### 4. Web Interface

#### FastAPI Server (`web/server.py`)

**Purpose**: Real-time visualization and control interface.

**Endpoints**:
- `GET /`: Serve HTML visualization page
- `GET /scenarios`: List available scenarios
- `POST /start/{scenario_id}`: Initialize simulation
- `POST /step`: Execute one simulation step
- `POST /reset`: Reset simulation state
- `WebSocket /ws`: Live state streaming

**Rendering**:
- **Grid**: Canvas-based rendering with color-coded cells
- **Vehicles**: Colored rectangles with battery indicators
- **Paths**: Trail visualization showing movement history
- **Stations**: Highlighted charging zones
- **Logs**: Real-time message stream

---

## Algorithms and Mechanisms

### 1. A* Pathfinding

**Purpose**: Find shortest path from source to destination avoiding obstacles.

**Complexity**: O(b^d) where b = branching factor, d = solution depth

**Optimality**: Guaranteed to find shortest path with admissible heuristic.

**Implementation Highlights**:
- Uses priority queue (heapq) for efficient node selection
- Tracks visited nodes to avoid cycles
- Reconstructs path by backtracking through parent pointers

### 2. Hungarian Algorithm (Linear Sum Assignment)

**Purpose**: Optimal bipartite matching for vehicle-station assignment.

**Complexity**: O(n³) where n = max(vehicles, stations)

**Optimality**: Minimizes total cost across all assignments.

**Use Case**: Assign 5 vehicles to 3 stations such that total (distance + urgency + load) is minimized.

### 3. Priority-Based Collision Avoidance

**Rule**: When two vehicles approach same cell, lower `unique_id` has priority.

**Mechanism**:
```python
def check_collision(next_pos):
    other_vehicles = [v for v in all_vehicles if v.next_pos == next_pos]
    for other in other_vehicles:
        if my_id > other.id:
            return True  # I must yield
    return False
```

**Advantage**: Deterministic, deadlock-free for small numbers of agents.

### 4. Reservation-Based Coordination

**Concept**: Reserve cells in advance along planned path.

**Protocol**:
1. Vehicle plans path P at time T
2. Vehicle reserves P[0] at T+1, P[1] at T+2, ..., P[n] at T+n+1
3. Other vehicles check reservations before planning
4. If conflict detected, replan with updated costs

**Advantage**: Prevents collisions in dense multi-agent scenarios.

### 5. Queue-Based Station Access

**Problem**: Station has capacity 1, but 3 robots want to charge.

**Solution**:
1. Orchestrator assigns `queue_pos`: 0, 1, 2
2. Only `queue_pos = 0` enters station
3. Others wait at adjacent cells (e.g., (x-1, y) or (x, y-1))
4. When `queue_pos = 0` finishes, everyone shifts: 1→0, 2→1

**Implementation**:
```python
class ChargingStation:
    queue: List[str] = []  # [vehicle_id_0, vehicle_id_1, ...]
    
    def add_to_queue(vehicle_id):
        queue.append(vehicle_id)
        return len(queue) - 1  # queue_pos
    
    def advance_queue():
        if queue:
            queue.pop(0)
        for i, vid in enumerate(queue):
            update_vehicle_queue_pos(vid, i)
```

### 6. Tit-for-Tat Negotiation

**Based on**: Axelrod's iterated Prisoner's Dilemma tournaments.

**Strategy Properties**:
- **Nice**: Start by cooperating
- **Retaliatory**: Punish defection
- **Forgiving**: Return to cooperation if opponent does
- **Clear**: Predictable pattern

**Application to Charging**:
- **Cooperate**: Accept assigned queue position
- **Defect**: Dispute assignment, demand better position

**Learning Mechanism**:
```python
def decide_response(opponent_id, current_assignment):
    if first_interaction(opponent_id):
        return COOPERATE  # Nice start
    else:
        last_action = opponent_history[opponent_id][-1]
        if last_action == COOPERATE:
            return COOPERATE  # Reciprocate
        else:
            return DEFECT  # Retaliate
```

---

## Scenario Descriptions

### Scenario 1: Standard - Simple 1 Agent

**Purpose**: Baseline validation of fundamental mechanics.

#### Configuration
- **Grid**: 15×12 with 2 obstacles
- **Vehicles**: 1 robot at (12, 1) with 25% battery
- **Stations**: 2 stations at (5,5) and (10,6), capacity 2 each
- **Exit**: (0, 11)

#### Objectives
1. Vehicle detects low battery (< 30%)
2. Sends status update to orchestrator
3. Orchestrator assigns nearest station
4. Vehicle plans A* path to station
5. Vehicle navigates to station
6. Vehicle charges to 95%
7. Vehicle navigates to exit

#### Why This Scenario Matters
- **Validates Core Loop**: Status → Assignment → Pathfinding → Movement → Charging
- **Tests Message Protocol**: Ensures vehicle-orchestrator communication works
- **Baseline Performance**: Establishes metrics for single-agent efficiency

#### Expected Outcome
Vehicle successfully charges and exits without errors.

---

### Scenario 2: Multiple Agents - Concurrent Charging

**Purpose**: Test concurrent operations and multi-agent coordination.

#### Configuration
- **Grid**: 20×16 with 8 obstacles (symmetric layout)
- **Vehicles**: 3 robots at (2,2), (17,2), (10,8) with batteries 28%, 26%, 24%
- **Stations**: 3 stations at (5,5), (14,5), (10,12), capacity 1 each
- **Exit**: (0, 14)

#### Objectives
1. All 3 vehicles request charging simultaneously
2. Orchestrator computes optimal 1-to-1 assignments
3. Vehicles navigate concurrently on different paths
4. All charge and exit without collisions

#### Challenges
- **Assignment Optimization**: Minimize total distance across all assignments
- **Path Overlaps**: Vehicles may cross paths (acceptable if no same-time collision)
- **Concurrent Charging**: All stations utilized simultaneously

#### Why This Scenario Matters
- **Scalability Test**: Validates system handles multiple agents
- **Assignment Algorithm**: Tests Hungarian method correctness
- **Parallelism**: Ensures concurrent operations don't interfere

#### Expected Outcome
All 3 vehicles successfully charge and exit concurrently.

---

### Scenario 3: Path Conflict - Head-On Avoidance

**Purpose**: Demonstrate collision avoidance in narrow corridors.

#### Configuration
- **Grid**: 9×10 with narrow 2-cell-wide corridor (obstacles on sides)
- **Vehicles**: 2 robots
  - `vehicle_0` at (0, 2) → Station at (2, 2)
  - `vehicle_1` at (8, 2) → Station at (6, 2)
- **Conflict**: Both on row 2, moving toward center
- **Exit**: (4, 9)

#### Collision Scenario
```
Step 1: vehicle_0 at (0,2), vehicle_1 at (8,2)
Step 2: vehicle_0 at (1,2), vehicle_1 at (7,2)
Step 3: vehicle_0 at (2,2), vehicle_1 at (6,2)  [At stations]
```

If no avoidance: Both try to occupy (4,2) simultaneously → **COLLISION**

#### Avoidance Mechanism
- **Priority Rule**: `vehicle_0` (lower ID) has priority
- **Yielding**: `vehicle_1` detects conflict, waits or deviates
- **Alternative Path**: `vehicle_1` may take detour if available

#### Why This Scenario Matters
- **Safety Critical**: Tests collision prevention logic
- **Priority System**: Validates deterministic conflict resolution
- **Narrow Spaces**: Stress-tests pathfinding in constrained areas

#### Expected Outcome
Both vehicles successfully avoid collision and complete charging.

---

### Scenario 4: Station Contention - Resource Allocation

**Purpose**: Queue management when demand exceeds capacity.

#### Configuration
- **Grid**: 12×10 open environment
- **Vehicles**: 3 robots at (3,1), (10,1), (6,7) with batteries 28%, 26%, 24%
- **Stations**: **1 station** at (6,4) with **capacity 1**
- **Bottleneck**: 3 robots, 1 slot

#### Resource Contention
- Only 1 robot can charge at a time
- Other 2 must wait in queue
- System must decide charging order

#### Assignment Strategy
Orchestrator assigns queue positions based on:
1. **Distance**: Closer robots get priority
2. **Battery Urgency**: Lower battery gets priority
3. **Fairness**: Avoid starvation

#### Queue Behavior
```
Initial: queue_pos assignments [0, 1, 2]
- vehicle_0 (queue_pos=0): Enters station, charges
- vehicle_1 (queue_pos=1): Waits at (5,4) or (7,4)
- vehicle_2 (queue_pos=2): Waits at (6,3) or (6,5)

After vehicle_0 completes:
- vehicle_1 (queue_pos=1 → 0): Enters station
- vehicle_2 (queue_pos=2 → 1): Moves to adjacent cell
```

#### Why This Scenario Matters
- **Scarcity Handling**: Tests queue management under resource limits
- **Waiting Logic**: Validates vehicles wait at correct positions
- **Fairness**: Ensures no robot is starved indefinitely
- **Throughput**: Measures system efficiency under contention

#### Expected Outcome
All 3 vehicles charge sequentially at single station, exit successfully.

---

### Scenario 5: Queue Negotiation - 2 Robots, 1 Station

**Purpose**: Demonstrate urgency-based negotiation and queue re-ordering.

#### Configuration
- **Grid**: 15×12 open environment
- **Vehicles**: 
  - `vehicle_0` at (2,2) with 25% battery (moderate urgency)
  - `vehicle_1` at (10,2) with **15% battery (critical urgency)**
- **Station**: 1 station at (6,4), capacity 1
- **Exit**: (0, 11)

#### Negotiation Scenario

**Round 1: Initial Assignment**
```
Orchestrator: "vehicle_0 is closer → queue_pos=0"
Orchestrator: "vehicle_1 is farther → queue_pos=1"
```

**Round 2: Counter-Proposal**
```
vehicle_1: "My battery is critical (15%)! I need priority."
vehicle_1: Sends AssignmentCounterProposalMessage requesting queue_pos=0
```

**Round 3: Re-Evaluation**
```
Orchestrator: Compares urgency
  - vehicle_0: 25% battery → urgency = 0.75
  - vehicle_1: 15% battery → urgency = 0.85
Orchestrator: "Accepted. vehicle_1 now queue_pos=0, vehicle_0 now queue_pos=1"
```

**Round 4: Execution**
```
vehicle_1: Enters station (despite being farther)
vehicle_0: Waits at adjacent cell
vehicle_1: Charges to 95%, exits
vehicle_0: Advances to queue_pos=0, charges, exits
```

#### Why This Scenario Matters
- **Dynamic Adaptation**: System responds to changing priorities
- **Negotiation Protocol**: Tests counter-proposal handling
- **Urgency vs. Distance**: Balances competing factors
- **Real-World Relevance**: Emergency vehicles, critical tasks

#### Expected Outcome
`vehicle_1` negotiates to go first due to critical battery, `vehicle_0` accepts waiting.

---

### Scenario 6: Tit-for-Tat - Behavioral Learning

**Purpose**: Demonstrate game-theoretic strategies and emergent cooperation.

#### Configuration
- **Grid**: 12×10 open environment
- **Vehicles**: 3 robots, all at 22% battery
  - `vehicle_0` (COOPERATIVE) at (3,5): Always accepts assignments
  - `vehicle_1` (COMPETITIVE) at (9,5): Always demands priority
  - `vehicle_2` (TIT_FOR_TAT) at (6,2): Mirrors opponent behavior
- **Station**: 1 station at (6,5), capacity 1
- **Exit**: (6, 9)

#### Behavioral Strategies

**COOPERATIVE (vehicle_0)**
```python
def respond_to_assignment(assignment):
    return ACCEPT  # Always yields
```
- **Advantage**: No conflict, easy coordination
- **Disadvantage**: Exploited by competitive agents
- **Expected Outcome**: Waits longest, worst outcomes

**COMPETITIVE (vehicle_1)**
```python
def respond_to_assignment(assignment):
    return DISPUTE  # Always demands better position
```
- **Advantage**: Wins initial confrontations
- **Disadvantage**: Faces retaliation, unsustainable
- **Expected Outcome**: Early wins, later penalties

**TIT-FOR-TAT (vehicle_2)**
```python
def respond_to_assignment(assignment, opponent):
    if first_interaction(opponent):
        return ACCEPT  # Start nice
    else:
        last_action = opponent_history[opponent][-1]
        if last_action == ACCEPT:
            return ACCEPT  # Reciprocate cooperation
        else:
            return DISPUTE  # Retaliate against defection
```
- **Advantage**: Balances self-interest and cooperation
- **Disadvantage**: Can get stuck in retaliation cycles
- **Expected Outcome**: Achieves fairest outcomes

#### Interaction Dynamics

**Phase 1: Initial Assignments (Steps 1-10)**
```
Orchestrator assigns queue positions based on distance:
  vehicle_0: queue_pos=1
  vehicle_1: queue_pos=2  
  vehicle_2: queue_pos=0 (closest)

vehicle_1 (COMPETITIVE): "I dispute! I should be queue_pos=0"
vehicle_2 (TFT): First interaction → ACCEPT
vehicle_0 (COOPERATIVE): ACCEPT

Result: vehicle_1 wins, moves to queue_pos=0
```

**Phase 2: Learning (Steps 11-30)**
```
vehicle_2 updates history: vehicle_1 → [DEFECT]

Next round:
vehicle_1 (COMPETITIVE): "I dispute again!"
vehicle_2 (TFT): vehicle_1 defected last time → DISPUTE (retaliate)

Orchestrator: Deadlock detected, resolves based on battery urgency
```

**Phase 3: Equilibrium (Steps 31-60)**
```
vehicle_0 - vehicle_2 interactions:
  vehicle_2: vehicle_0 always cooperates → Continue cooperating
  Result: Mutual cooperation (both benefit)

vehicle_1 - vehicle_2 interactions:
  vehicle_2: vehicle_1 always defects → Continue retaliating
  Result: Alternating disputes (balanced outcome)

vehicle_0 - vehicle_1 interactions:
  vehicle_0: Always accepts (exploited)
  vehicle_1: Always wins (exploits)
```

#### Why This Scenario Matters
- **Game Theory Application**: Real-world demonstration of classic strategies
- **Emergent Behavior**: Cooperation/conflict patterns emerge from simple rules
- **Fairness Analysis**: TFT achieves better outcomes than pure strategies
- **Behavioral Learning**: Agents adapt based on opponent patterns
- **Research Validation**: Reproduces Axelrod's tournament results

#### Research Foundation
Based on:
- Axelrod, R., & Hamilton, W. D. (1981). "The Evolution of Cooperation." *Science*.
- Nowak, M. A., & Sigmund, K. (1993). "Win-stay, lose-shift in Prisoner's Dilemma." *Nature*.

#### Expected Outcome
TFT robot learns and adapts, cooperative exploited, competitive faces retaliation, all complete charging.

---

## Installation and Usage

### Prerequisites

- **Python**: 3.10 or higher
- **Anaconda**: For environment management
- **Operating System**: Linux, macOS, or Windows (native support with .bat/.ps1 files)

### Installation Steps

1. **Clone Repository**
```bash
git clone https://github.com/thuanbui1309/multi-robot.git
cd multi-robot
```

2. **Create Conda Environment**

**Linux/macOS:**
```bash
./setup.sh
```

**Windows (Command Prompt):**
```cmd
setup.bat
```

**Windows (PowerShell):**
```powershell
.\setup.ps1
```

This script:
- Creates `multi_robot_system` conda environment
- Installs all dependencies from `requirements.txt`
- Configures Python 3.10+

3. **Verify Installation**
```bash
conda activate multi_robot_system
python -c "import mesa; import scipy; import fastapi; print('All dependencies installed!')"
```

### Running Simulations

#### Web Interface (Recommended)

**Linux/macOS:**
```bash
./run_web.sh
```

**Windows (Command Prompt):**
```cmd
run_web.bat
```

**Windows (PowerShell):**
```powershell
.\run_web.ps1
```

Then open browser: `http://localhost:8000`

**Features**:
- Select scenario from dropdown
- Start/pause/reset simulation
- Adjust speed with step delay slider
- View real-time logs and metrics
- Visualize paths and battery levels

#### Command Line

Run specific scenario:
```bash
conda run -n multi_robot_system python test_scenario6.py
```

Run all tests:
```bash
conda run -n multi_robot_system pytest
```

### Project Structure

```
multi-robot/
├── agents/                    # Agent implementations
│   ├── vehicle.py            # Base vehicle class
│   ├── negotiating_vehicle.py
│   ├── tit_for_tat_vehicle.py
│   ├── orchestrator.py       # Base orchestrator
│   ├── negotiating_orchestrator.py
│   └── tit_for_tat_orchestrator.py
│
├── core/                      # Core systems
│   ├── grid.py               # Environment representation
│   ├── planner.py            # A* pathfinding
│   ├── reservation.py        # Collision prevention
│   ├── assign.py             # Hungarian assignment
│   ├── messages.py           # Message protocol
│   └── metrics.py            # Performance tracking
│
├── sim/                       # Simulation engine
│   ├── model.py              # Mesa model
│   └── scenarios.py          # Scenario definitions
│
├── web/                       # Web interface
│   └── server.py             # FastAPI server
│
├── tests/                     # Test suites
│   ├── test_scenario4.py
│   ├── test_scenario6.py
│   ├── test_exit_conflict.py
│   └── test_wait_outside.py
│
├── requirements.txt           # Python dependencies
├── setup.sh                   # Environment setup script
├── run_web.sh                 # Web server launcher
├── README.md                  # Quick start guide
├── DOCUMENTATION.md           # This file
└── TIT_FOR_TAT.md            # TFT algorithm details
```

---

## Technical Details

### Message Protocol

All agent communication uses typed message classes:

```python
@dataclass
class StatusUpdateMessage:
    """Vehicle → Orchestrator"""
    vehicle_id: str
    position: Tuple[int, int]
    battery_level: float
    state: VehicleStatus
    timestamp: int

@dataclass
class AssignmentMessage:
    """Orchestrator → Vehicle"""
    station_id: int
    position: Tuple[int, int]
    queue_position: int
    priority: float

@dataclass
class AssignmentCounterProposalMessage:
    """Vehicle → Orchestrator (negotiation)"""
    vehicle_id: str
    current_assignment: int
    proposed_assignment: int
    reason: str
    urgency: float
```

### State Machine (VehicleAgent)

```
           ┌──────────┐
           │   IDLE   │ (Initial state)
           └────┬─────┘
                │ battery < threshold
                ▼
         ┌────────────┐
         │  WAITING   │ (Requesting assignment)
         └─────┬──────┘
               │ assignment received
               ▼
         ┌────────────┐
         │   MOVING   │ (Navigating to station)
         └─────┬──────┘
               │ arrived at station
               ▼
         ┌────────────┐
         │  CHARGING  │ (Recharging battery)
         └─────┬──────┘
               │ battery > 95%
               ▼
         ┌────────────┐
         │  EXITING   │ (Moving to exit)
         └─────┬──────┘
               │ reached exit
               ▼
         ┌────────────┐
         │ COMPLETED  │ (Removed from simulation)
         └────────────┘
```

### Performance Characteristics

| Component | Complexity | Notes |
|-----------|-----------|-------|
| A* Pathfinding | O(b^d) | b=branching factor, d=depth |
| Hungarian Assignment | O(n³) | n=max(vehicles, stations) |
| Collision Check | O(n) | n=number of vehicles |
| Reservation Table | O(1) | Dict lookup |
| Message Broadcast | O(n) | n=number of agents |

### Configuration Parameters

```python
# Battery
BATTERY_DRAIN_RATE = 0.5    # % per step
CHARGE_RATE = 5.0           # % per step at station
BATTERY_THRESHOLD = 30.0    # % trigger for charging request

# Assignment
DISTANCE_WEIGHT = 1.0       # Cost multiplier for distance
BATTERY_WEIGHT = 2.0        # Cost multiplier for urgency
LOAD_WEIGHT = 0.5           # Cost multiplier for station load

# Simulation
STEP_DELAY = 0.5            # Seconds between steps (web UI)
MAX_STEPS = 1000            # Simulation timeout
```

---

## Research Context

### Multi-Agent Systems

This project demonstrates core concepts from multi-agent systems research:

1. **Distributed Coordination**: No central controller for movement decisions
2. **Emergent Behavior**: System-level patterns emerge from agent-level rules
3. **Resource Allocation**: Optimal assignment under scarcity
4. **Conflict Resolution**: Negotiation and priority-based mechanisms

### Game Theory

Scenario 6 implements classic game-theoretic strategies:

- **Prisoner's Dilemma**: Cooperate vs. defect in resource sharing
- **Iterated Games**: Repeated interactions enable learning and adaptation
- **Evolutionary Stability**: TFT outperforms pure strategies in repeated games
- **Reciprocal Altruism**: Conditional cooperation based on partner behavior

### Robotics Applications

Real-world applications include:

1. **Warehouse Automation**: Amazon robots charging coordination
2. **Autonomous Vehicles**: EV charging station allocation
3. **Drone Fleets**: Battery swap station management
4. **Mobile Robots**: Museum guide robots, hospital delivery robots

### Key Research Papers

1. **Pathfinding**:
   - Hart, P. E., Nilsson, N. J., & Raphael, B. (1968). "A Formal Basis for the Heuristic Determination of Minimum Cost Paths." *IEEE Transactions on Systems Science and Cybernetics*.

2. **Assignment**:
   - Kuhn, H. W. (1955). "The Hungarian Method for the Assignment Problem." *Naval Research Logistics Quarterly*.

3. **Game Theory**:
   - Axelrod, R. (1984). *The Evolution of Cooperation*. Basic Books.
   - Nowak, M. A., & Sigmund, K. (1993). "A strategy of win-stay, lose-shift that outperforms tit-for-tat." *Nature*, 364(6432), 56-58.

4. **Multi-Robot Systems**:
   - Gerkey, B. P., & Matarić, M. J. (2002). "Sold!: Auction methods for multirobot coordination." *IEEE Transactions on Robotics and Automation*, 18(5), 758-768.

---

## Future Extensions

### Potential Improvements

1. **Advanced Pathfinding**: D* Lite for dynamic replanning, RRT for continuous spaces
2. **Learning Agents**: Reinforcement learning for strategy optimization
3. **Decentralized Coordination**: Remove orchestrator, peer-to-peer negotiation
4. **Energy Optimization**: Battery wear models, partial charging strategies
5. **Real Robot Integration**: ROS interface, physical robot deployment
6. **Scalability**: Hierarchical orchestration for 100+ robots
7. **Uncertainty**: Probabilistic models for battery drain, sensor noise

### Research Questions

1. What is optimal number of charging stations vs. fleet size?
2. How does TFT perform with noisy communication?
3. Can deep RL learn better strategies than TFT?
4. What happens with heterogeneous robots (different speeds, battery capacities)?
5. How to handle dynamic obstacles and changing environments?

---

## Conclusion

This multi-robot charging coordination system demonstrates the intersection of **pathfinding algorithms**, **game theory**, **multi-agent coordination**, and **distributed systems**. Through six carefully designed scenarios, it validates core concepts from robotics research while providing a foundation for exploring emergent behavior, negotiation strategies, and resource allocation under scarcity.

The implementation balances **theoretical rigor** (A*, Hungarian algorithm, Tit-for-Tat) with **practical engineering** (Mesa framework, FastAPI, real-time visualization), making it suitable for both academic study and applied robotics development.

---

## License

MIT License - See repository for details.

## Contributors

- Thuan Bui (thuanbui1309)
- Swinburne University of Technology
- COS30008 - Advanced Software Development

## Acknowledgments

- **Mesa Framework**: Agent-based modeling infrastructure
- **Robert Axelrod**: Tit-for-Tat algorithm research
- **SciPy**: Hungarian algorithm implementation
- **FastAPI**: Modern web framework for real-time visualization
