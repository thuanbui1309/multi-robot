from typing import Optional, List, Tuple, Dict, Any
from mesa import Agent
from core.messages import (
    VehicleStatus, StatusUpdateMessage, AssignmentMessage,
    ChargingCompleteMessage
)
from core.planner import AStarPlanner
from core.grid import Grid

class VehicleAgent(Agent):
    """
    Autonomous vehicle agent that:
    - Receives charging station assignments
    - Plans path using A*
    - Navigates while avoiding obstacles
    - Reports status to orchestrator
    """
    
    def __init__(
        self,
        unique_id: str,
        model,
        position: Tuple[int, int],
        battery_level: float = 100.0,
        battery_drain_rate: float = 0.5,
        charge_rate: float = 2.0
    ):
        """
        Initialize vehicle agent.
        
        Args:
            unique_id: Unique identifier for vehicle
            model: Mesa model reference
            position: Starting position
            battery_level: Initial battery level (0-100)
            battery_drain_rate: Battery drain per movement step
            charge_rate: Charging rate per tick at station
        """
        super().__init__(model)
        self.unique_id = unique_id
        
        # Position and movement
        self.position = position
        self.path: List[Tuple[int, int]] = []
        self.path_index = 0
        
        # Battery management
        self.battery_level = battery_level
        self.battery_drain_rate = battery_drain_rate
        self.charge_rate = charge_rate
        self.battery_threshold = 30.0  # Request charging below this
        
        # Status
        self.status = VehicleStatus.IDLE
        self.target_station: Optional[int] = None
        self.target_position: Optional[Tuple[int, int]] = None
        
        # Planning
        self.planner = AStarPlanner()
        self.stuck_counter = 0
        self.max_stuck_time = 5
        
        # Statistics
        self.total_distance = 0.0
        self.num_replans = 0
        self.charging_start_time: Optional[int] = None
        
        # Charging request tracking
        self.has_requested_charging = False
    
    @property
    def needs_charging(self) -> bool:
        """Check if vehicle needs charging."""
        return self.battery_level < self.battery_threshold
    
    def step(self):
        """Execute one step of the vehicle's behavior."""
        # Main agent loop: sense -> plan -> act -> report
        
        # 1. SENSE - Update status based on environment
        self._sense()
        
        # 2. REQUEST CHARGING if needed (proactive agent behavior)
        if self.needs_charging and not self.has_requested_charging and self.status == VehicleStatus.IDLE:
            self._request_charging()
        
        # 3. PLAN - Decide next action
        self._plan()
        
        # 4. ACT - Execute action
        self._act()
        
        # 5. REPORT - Send status to orchestrator
        self._report_status()
    
    def _sense(self):
        """Sense environment and update internal state."""
        # Check if at charging station
        grid: Grid = self.model.grid
        station = grid.get_station_at(self.position)
        
        if station and station.station_id == self.target_station:
            if self.status != VehicleStatus.CHARGING:
                # Arrived at target station
                if station.occupy(self.unique_id):
                    self.status = VehicleStatus.CHARGING
                    self.charging_start_time = self.model.schedule.steps
                    self.path = []
                    self.path_index = 0
                    
                    # Log arrival
                    self.model.log_activity(
                        self.unique_id,
                        f"Arrived at Station_{self.target_station}, started charging (battery: {self.battery_level:.1f}%)",
                        "action"
                    )
        
        # Check if charging complete
        if self.status == VehicleStatus.CHARGING:
            if self.battery_level >= 95.0:
                self._complete_charging()
    
    def _request_charging(self):
        """Request charging from orchestrator when battery is low."""
        self.has_requested_charging = True
        
        # Log the charging request
        self.model.log_activity(
            self.unique_id,
            f"Battery low ({self.battery_level:.1f}%), requesting charging assignment from Orchestrator",
            "action"
        )
        
        # Send status update which will trigger orchestrator assignment logic
        # The orchestrator will detect low battery and assign a station
    
    def _plan(self):
        """Plan next action based on current state."""
        if self.status == VehicleStatus.CHARGING:
            # Do nothing, just charge
            return
        
        if self.status == VehicleStatus.IDLE:
            # Wait for assignment
            return
        
        # Handle EXITING status - plan path to exit
        if self.status == VehicleStatus.EXITING and self.target_position and not self.path:
            self._plan_path_to_target()
        
        # If we have a target but no path, plan path
        if self.target_position and not self.path:
            self._plan_path_to_target()
        
        # Check if path is blocked and needs replanning
        if self.path and self.path_index < len(self.path):
            next_pos = self.path[self.path_index]
            grid: Grid = self.model.grid
            
            # Check if next position is blocked
            if not grid.is_walkable(next_pos[0], next_pos[1]):
                self._replan()
    
    def _act(self):
        """Execute planned action."""
        if self.status == VehicleStatus.CHARGING:
            # Charge battery
            self.battery_level = min(100.0, self.battery_level + self.charge_rate)
            return
        
        if self.status == VehicleStatus.IDLE:
            # Stay in place, maybe drain a little battery
            old_battery = self.battery_level
            self.battery_level = max(0.0, self.battery_level - 0.1)
            
            # Log when battery gets critically low
            if old_battery > 20 and self.battery_level <= 20:
                self.model.log_activity(
                    self.unique_id,
                    f"Battery critically low: {self.battery_level:.1f}%, waiting for assignment",
                    "warning"
                )
            return
        
        # Try to move along path
        if self.path and self.path_index < len(self.path):
            next_pos = self.path[self.path_index]
            
            # Try to reserve next position
            reservation_table = self.model.reservation_table
            current_time = self.model.schedule.steps
            
            if reservation_table.reserve(next_pos, current_time + 1, self.unique_id):
                # Move successful
                old_pos = self.position
                self.position = next_pos
                self.path_index += 1
                
                # Update distance and drain battery
                distance = abs(next_pos[0] - old_pos[0]) + abs(next_pos[1] - old_pos[1])
                self.total_distance += distance
                self.battery_level = max(0.0, self.battery_level - self.battery_drain_rate)
                
                self.status = VehicleStatus.MOVING
                self.stuck_counter = 0
                
                # Log movement - only once when starting movement
                if self.path_index == 1:  # First step of the path
                    total_steps = len(self.path)
                    if self.target_station is not None:
                        self.model.log_activity(
                            self.unique_id,
                            f"Moving to Station_{self.target_station} (total {total_steps} steps, battery: {self.battery_level:.1f}%)",
                            "info"
                        )
                    else:
                        self.model.log_activity(
                            self.unique_id,
                            f"Moving to exit (total {total_steps} steps, battery: {self.battery_level:.1f}%)",
                            "info"
                        )
                
                # Release old reservation
                reservation_table.release(old_pos, current_time, self.unique_id)
                
                # Check if reached goal
                if self.path_index >= len(self.path):
                    self.path = []
                    self.path_index = 0
                    if self.position == self.target_position:
                        # Check if exiting and reached exit
                        if self.status == VehicleStatus.EXITING:
                            self.status = VehicleStatus.COMPLETED
                            self.model.log_activity(
                                self.unique_id,
                                f"Reached exit at {self.position}, cycle complete!",
                                "action"
                            )
                        else:
                            self.status = VehicleStatus.IDLE
            else:
                # Path blocked, increment stuck counter
                self.stuck_counter += 1
                if self.stuck_counter >= self.max_stuck_time:
                    self._replan()
                    self.stuck_counter = 0
    
    def _plan_path_to_target(self):
        """Plan path to target position using A*."""
        if not self.target_position:
            return
        
        grid: Grid = self.model.grid
        reservation_table = self.model.reservation_table
        current_time = self.model.schedule.steps
        
        # Get blocked cells from reservation table
        blocked = reservation_table.get_blocked_cells(
            current_time + 1,
            exclude_vehicle=self.unique_id
        )
        
        # Plan path
        path, cost = self.planner.plan(
            start=self.position,
            goal=self.target_position,
            is_walkable=grid.is_walkable,
            get_neighbors=grid.get_neighbors,
            blocked_cells=blocked
        )
        
        if path:
            self.path = path[1:]  # Exclude current position
            self.path_index = 0
            self.status = VehicleStatus.MOVING
            
            # Log path planning
            self.model.log_activity(
                self.unique_id,
                f"Planned path to Station_{self.target_station} ({len(self.path)} steps)",
                "action"
            )
            
            # Try to reserve the path
            if not reservation_table.reserve_path(self.path, current_time + 1, self.unique_id):
                # Couldn't reserve full path, will reserve step by step
                pass
        else:
            # No path found
            self.status = VehicleStatus.STUCK
            self.stuck_counter += 1
            
            # Log stuck vehicle
            if self.stuck_counter == 1:  # Only log first time stuck
                self.model.log_activity(
                    self.unique_id,
                    f"Cannot find path to Station_{self.target_station}",
                    "warning"
                )
    
    def _replan(self):
        """Replan path due to obstacle or conflict."""
        # Release future reservations
        reservation_table = self.model.reservation_table
        current_time = self.model.schedule.steps
        reservation_table.release_future(self.unique_id, current_time)
        
        # Clear current path
        self.path = []
        self.path_index = 0
        
        # Plan new path
        self._plan_path_to_target()
        self.num_replans += 1
        
        # Record metric
        if hasattr(self.model, 'metrics'):
            self.model.metrics.record_replan(self.unique_id)
    
    def _complete_charging(self):
        """Complete charging and head to exit."""
        grid: Grid = self.model.grid
        station = grid.get_station_at(self.position)
        
        if station:
            station.release(self.unique_id)
        
        # Check if exit is configured
        if grid.exit_position:
            # Head to exit
            self.status = VehicleStatus.EXITING
            self.target_station = None
            self.target_position = grid.exit_position
            self.path = []
            self.path_index = 0
            
            # Log exiting
            self.model.log_activity(
                self.unique_id,
                f"Charging complete (battery: {self.battery_level:.1f}%), heading to exit at {grid.exit_position}",
                "action"
            )
        else:
            # No exit, just go idle
            self.status = VehicleStatus.IDLE
            self.target_station = None
            self.target_position = None
            
            # Log completion
            self.model.log_activity(
                self.unique_id,
                f"Charging complete (battery: {self.battery_level:.1f}%), returning to idle",
                "action"
            )
        
        # Send completion message
        msg = ChargingCompleteMessage(
            sender_id=self.unique_id,
            receiver_id=str(self.model.orchestrator.unique_id),  # Convert to string
            timestamp=self.model.schedule.steps,
            final_battery=self.battery_level,
            charging_duration=self.model.schedule.steps - self.charging_start_time
        )
        self.model.message_queue.append(msg)
    
    def _report_status(self):
        """Send status update to orchestrator."""
        msg = StatusUpdateMessage(
            sender_id=self.unique_id,
            receiver_id=str(self.model.orchestrator.unique_id),  # Convert to string
            timestamp=self.model.schedule.steps,
            position=self.position,
            battery_level=self.battery_level,
            status=self.status,
            target_station=self.target_station
        )
        self.model.message_queue.append(msg)
        
        # Record metrics
        if hasattr(self.model, 'metrics'):
            self.model.metrics.record_vehicle_step(
                self.unique_id,
                self.battery_level,
                self.position
            )
            
            if self.status == VehicleStatus.CHARGING:
                self.model.metrics.record_charging(self.unique_id)
            elif self.status == VehicleStatus.MOVING:
                self.model.metrics.record_moving(self.unique_id)
    
    def receive_assignment(self, assignment: AssignmentMessage):
        """Receive station assignment from orchestrator."""
        self.target_station = assignment.station_id
        self.target_position = assignment.station_position
        self.status = VehicleStatus.PLANNING
        
        # Log received assignment
        self.model.log_activity(
            self.unique_id,
            f"Received assignment to Station_{assignment.station_id} at {assignment.station_position}, planning path",
            "action"
        )
        
        # Plan path immediately
        self._plan_path_to_target()
        
        # Record metric
        if hasattr(self.model, 'metrics'):
            self.model.metrics.record_assignment(self.unique_id)
    
    def get_state(self) -> Dict[str, Any]:
        """Get current state as dictionary."""
        return {
            'id': self.unique_id,
            'position': self.position,
            'battery_level': self.battery_level,
            'status': self.status.value,
            'target_station': self.target_station,
            'path_length': len(self.path) - self.path_index if self.path else 0,
            'total_distance': self.total_distance,
            'num_replans': self.num_replans,
        }
