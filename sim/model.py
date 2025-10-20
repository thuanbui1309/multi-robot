from typing import List, Tuple, Dict, Any, Optional
import random
from mesa import Model
from mesa.time import BaseScheduler
from core.grid import Grid
from core.reservation import ReservationTable
from core.metrics import SimulationMetrics
from agents.vehicle import VehicleAgent
from agents.orchestrator import OrchestratorAgent

class OrderedScheduler(BaseScheduler):
    """
    Custom scheduler that runs vehicles first, then orchestrator.
    This ensures vehicles send status updates before orchestrator processes them.
    """
    
    def __init__(self, model):
        super().__init__(model)
        self.vehicle_agents = []
        self.orchestrator = None
    
    def add(self, agent):
        """Add agent to scheduler."""
        super().add(agent)
        if isinstance(agent, VehicleAgent):
            self.vehicle_agents.append(agent)
        elif isinstance(agent, OrchestratorAgent):
            self.orchestrator = agent
    
    def remove(self, agent):
        """Remove agent from scheduler."""
        super().remove(agent)
        if isinstance(agent, VehicleAgent) and agent in self.vehicle_agents:
            self.vehicle_agents.remove(agent)
    
    def step(self):
        """Execute one step - vehicles first, then orchestrator."""
        # Step all vehicles first (they send status messages)
        for agent in self.vehicle_agents:
            agent.step()
        
        # Then step orchestrator (processes messages and assigns)
        if self.orchestrator:
            self.orchestrator.step()
        
        self.steps += 1
        self.time += 1


class ChargingSimulationModel(Model):
    """
    Mesa model for multi-robot charging simulation.
    
    Manages:
    - Grid environment
    - Vehicle and orchestrator agents
    - Reservation table for collision avoidance
    - Message passing between agents
    - Metrics collection
    """
    
    def __init__(
        self,
        grid: Grid,
        initial_vehicle_positions: List[Tuple[int, int]],
        initial_battery_levels: Optional[List[float]] = None,
        scenario_name: str = "Unknown Scenario",
        scenario_description: str = "",
        step_delay: float = 0.3
    ):
        """
        Initialize simulation model.
        
        Args:
            grid: Grid environment
            initial_vehicle_positions: Starting positions for vehicles
            initial_battery_levels: Starting battery levels (optional)
            scenario_name: Name of the scenario being run
            scenario_description: Description of the scenario
            step_delay: Delay between steps for visualization
        """
        super().__init__()
        
        # Scenario information
        self.scenario_name = scenario_name
        self.scenario_description = scenario_description
        self.step_delay = step_delay
        
        # Initial delay for observation (reduced to ~0.5 seconds)
        self.initial_delay_steps = 2  # ~0.3 seconds at 0.15s per step
        self.steps_with_initial_delay = 0
        self.initial_logs_shown = False  # Track if initial logs were added
        self.completion_logged = False  # Track if completion message was logged
        
        # Environment
        self.grid = grid
        self.reservation_table = ReservationTable()
        
        # Metrics
        self.metrics = SimulationMetrics()
        
        # Message passing
        self.message_queue: List[Any] = []
        
        # Agent activity logs for visualization
        self.activity_logs: List[Dict[str, str]] = []
        
        # Vehicle trails for visualization (last N positions per vehicle)
        self.vehicle_trails: Dict[str, List[Tuple[int, int]]] = {}
        self.max_trail_length = 50  # Increased to show more of the path
        
        # Agent scheduling (ordered: vehicles first, then orchestrator)
        self.schedule = OrderedScheduler(self)
        
        # Create orchestrator agent
        self.orchestrator = OrchestratorAgent("orchestrator", self)
        self.schedule.add(self.orchestrator)
        
        # Create vehicle agents
        self.vehicles: Dict[str, VehicleAgent] = {}
        self._vehicle_counter = 0
        
        # Add initial vehicles
        for i, pos in enumerate(initial_vehicle_positions):
            battery = initial_battery_levels[i] if initial_battery_levels else random.uniform(20, 80)
            vehicle_id = self.add_vehicle(pos, battery)
        
        self.running = True
        
        # Don't add initial logs here - will be added in first step
        # to avoid duplicate broadcasts
    
    def add_vehicle(
        self,
        position: Tuple[int, int],
        battery_level: float = 50.0
    ) -> str:
        """
        Add a new vehicle to the simulation.
        
        Args:
            position: Starting position
            battery_level: Initial battery level
        
        Returns:
            Vehicle ID
        """
        vehicle_id = f"vehicle_{self._vehicle_counter}"
        self._vehicle_counter += 1
        
        # Enable negotiation for Scenario 5
        enable_negotiation = "negotiation" in self.scenario_name.lower()
        
        vehicle = VehicleAgent(
            unique_id=vehicle_id,
            model=self,
            position=position,
            battery_level=battery_level,
            battery_drain_rate=0.5,
            charge_rate=5.0,  # Faster charging: 5% per tick instead of 2%
            enable_negotiation=enable_negotiation
        )
        
        self.vehicles[vehicle_id] = vehicle
        self.schedule.add(vehicle)
        
        return vehicle_id
    
    def remove_vehicle(self, vehicle_id: str):
        """Remove a vehicle from the simulation."""
        if vehicle_id in self.vehicles:
            vehicle = self.vehicles[vehicle_id]
            self.schedule.remove(vehicle)
            del self.vehicles[vehicle_id]
            
            # Clean up reservations
            self.reservation_table.release_all(vehicle_id)
    
    def step(self):
        """Execute one step of the simulation."""
        # Apply initial delay at the start (slower for first few steps)
        # This allows user to see the initial messages without agents acting
        if self.steps_with_initial_delay < self.initial_delay_steps:
            self.steps_with_initial_delay += 1
            
            # Add initial logs only on the very first step
            if self.steps_with_initial_delay == 1:
                self.log_activity(
                    "System",
                    f"Starting Scenario: {self.scenario_name}",
                    "action"
                )
                
                for vehicle_id, vehicle in self.vehicles.items():
                    self.log_activity(
                        vehicle_id,
                        f"Initialized at {vehicle.position} with {vehicle.battery_level:.1f}% battery",
                        "info"
                    )
            else:
                # Clear logs after first step to prevent duplicates
                self.activity_logs.clear()
            
            # Don't execute agents during initial delay
            return
        
        # Clear logs from previous step (after initial delay)
        self.activity_logs.clear()
        
        # Don't clear message queue here - let it accumulate
        # Messages will be processed by orchestrator
        
        # Execute all agents
        self.schedule.step()
        
        # Clear processed messages after all agents have stepped
        self.message_queue.clear()
        
        # Check if all vehicles have completed (reached exit)
        all_completed = all(
            vehicle.status.value == 'completed' 
            for vehicle in self.vehicles.values()
        )
        
        if all_completed and len(self.vehicles) > 0:
            if not self.completion_logged:
                self.running = False
                self.log_activity(
                    "System",
                    "Scenario complete - all vehicles have exited",
                    "action"
                )
                self.completion_logged = True
            return
        
        # Update metrics
        self.metrics.increment_tick()
        
        # Cleanup old reservations periodically
        if self.schedule.steps % 10 == 0:
            self.reservation_table.cleanup_old_reservations(
                self.schedule.steps,
                keep_history=20
            )
    
    def log_activity(self, agent: str, message: str, log_type: str = "info"):
        """Log agent activity for visualization."""
        self.activity_logs.append({
            "agent": agent,
            "message": message,
            "type": log_type
        })
    
    def get_state(self) -> Dict[str, Any]:
        """
        Get current simulation state.
        
        Returns:
            Dictionary containing full simulation state
        """
        # Get vehicle states with paths and trails
        vehicle_states = []
        vehicle_positions = {}
        
        for vehicle_id, vehicle in self.vehicles.items():
            state = vehicle.get_state()
            # Add current path information
            state['current_path'] = vehicle.path if vehicle.path else []
            state['path_index'] = vehicle.path_index
            # Add trail information
            state['trail'] = self.vehicle_trails.get(vehicle_id, [])
            vehicle_states.append(state)
            vehicle_positions[vehicle.position] = vehicle_id
            
            # Update trail
            if vehicle_id not in self.vehicle_trails:
                self.vehicle_trails[vehicle_id] = []
            trail = self.vehicle_trails[vehicle_id]
            if not trail or trail[-1] != vehicle.position:
                trail.append(vehicle.position)
                # Keep only last N positions
                if len(trail) > self.max_trail_length:
                    trail.pop(0)
        
        # Get station states
        station_states = []
        for station in self.grid.charging_stations:
            station_states.append({
                'id': station.station_id,
                'position': station.position,
                'capacity': station.capacity,
                'occupied': len(station.occupied_slots),
                'load': station.get_load(),
            })
        
        # Get orchestrator state
        orchestrator_state = self.orchestrator.get_state()
        
        return {
            'tick': self.schedule.steps,
            'scenario_name': self.scenario_name,
            'scenario_description': self.scenario_description,
            'step_delay': self.step_delay,
            'vehicles': vehicle_states,
            'stations': station_states,
            'orchestrator': orchestrator_state,
            'grid_string': self.grid.to_string(vehicle_positions),
            'grid_exit': self.grid.exit_position,  # Add exit position
            'metrics_summary': self.metrics.get_summary(),
            'logs': self.activity_logs,  # Include activity logs
        }
    
    def run_until_complete(self, max_steps: int = 1000) -> Dict[str, Any]:
        """
        Run simulation until all vehicles are charged or max steps reached.
        
        Args:
            max_steps: Maximum number of steps
        
        Returns:
            Final simulation state
        """
        for _ in range(max_steps):
            self.step()
            
            # Check if all vehicles are idle and fully charged
            all_charged = all(
                v.battery_level >= 95.0 and v.status.value == 'idle'
                for v in self.vehicles.values()
            )
            
            if all_charged:
                break
        
        return self.get_state()
