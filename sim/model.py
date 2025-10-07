"""Mesa-based multi-agent simulation model."""

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
    ):
        """
        Initialize simulation model.
        
        Args:
            grid: Grid environment
            initial_vehicle_positions: Starting positions for vehicles
            initial_battery_levels: Starting battery levels (optional)
        """
        super().__init__()
        
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
        self.max_trail_length = 10
        
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
            self.add_vehicle(pos, battery)
        
        self.running = True
    
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
        
        vehicle = VehicleAgent(
            unique_id=vehicle_id,
            model=self,
            position=position,
            battery_level=battery_level,
            battery_drain_rate=0.5,
            charge_rate=2.0
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
        # Clear logs from previous step
        self.activity_logs.clear()
        
        # Don't clear message queue here - let it accumulate
        # Messages will be processed by orchestrator
        
        # Execute all agents
        self.schedule.step()
        
        # Clear processed messages after all agents have stepped
        self.message_queue.clear()
        
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
