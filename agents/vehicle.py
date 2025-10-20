from typing import Optional, List, Tuple, Dict, Any
from mesa import Agent
from core.messages import (
    VehicleStatus, StatusUpdateMessage, AssignmentMessage,
    ChargingCompleteMessage, AssignmentRejectionMessage,
    AssignmentCounterProposalMessage
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
        charge_rate: float = 2.0,
        enable_negotiation: bool = False
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
            enable_negotiation: Whether vehicle can negotiate assignments
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
        
        # Collision avoidance - Priority based on vehicle ID
        self.priority = self._extract_priority(unique_id)
        self.waiting_for_vehicle: Optional[str] = None
        self.wait_counter = 0
        self.max_wait_time = 10  # Maximum ticks to wait before replanning
        
        # Negotiation capabilities
        self.enable_negotiation = enable_negotiation
        self.max_acceptable_distance = 10  # Max distance willing to travel (reduced from 15)
        self.critical_battery_threshold = 25.0  # Below this, very selective
        self.distance_preference_factor = 0.2  # Reject if alternative is 20% closer (more aggressive)
        self.battery_safety_margin = 2.0  # Require 2x battery for distance (more conservative)
        
        # Statistics
        self.total_distance = 0.0
        self.num_replans = 0
        self.charging_start_time: Optional[int] = None
        
        # Charging request tracking
        self.has_requested_charging = False
    
    def _extract_priority(self, vehicle_id: str) -> int:
        """
        Extract priority from vehicle ID.
        Lower ID number = Higher priority (goes first in conflicts).
        
        Args:
            vehicle_id: Vehicle identifier (e.g., "vehicle_0", "vehicle_1")
        
        Returns:
            Integer priority (lower number = higher priority)
        """
        try:
            # Extract number from "vehicle_N" format
            return int(vehicle_id.split('_')[1])
        except (IndexError, ValueError):
            # Fallback: use hash if format is unexpected
            return hash(vehicle_id) % 1000
    
    @property
    def needs_charging(self) -> bool:
        """Check if vehicle needs charging."""
        return self.battery_level < self.battery_threshold
    
    def _detect_collision_threat(self, next_pos: Tuple[int, int]) -> Optional[str]:
        """
        Detect if moving to next_pos would cause collision with another vehicle.
        Implements priority-based detection from the algorithm.
        
        Args:
            next_pos: Position we want to move to
            
        Returns:
            ID of threatening vehicle if collision detected, None otherwise
        """
        # Check all other vehicles
        for vehicle_id, vehicle in self.model.vehicles.items():
            if vehicle_id == self.unique_id:
                continue
            
            # Skip completed vehicles
            if vehicle.status == VehicleStatus.COMPLETED:
                continue
                
            # Check if other vehicle is at our target position
            if vehicle.position == next_pos:
                return vehicle_id
            
            # Check if other vehicle is heading to same position (head-on)
            if (hasattr(vehicle, 'path') and vehicle.path and 
                vehicle.path_index < len(vehicle.path)):
                other_next = vehicle.path[vehicle.path_index]
                
                # Head-on collision: we go to their position, they come to ours
                if other_next == self.position and next_pos == vehicle.position:
                    return vehicle_id
                
                # Same target next step
                if other_next == next_pos:
                    return vehicle_id
        
        return None
    
    def _should_yield(self, other_vehicle_id: str) -> bool:
        """
        Determine if this vehicle should yield to another based on priority.
        Lower ID = Higher priority (proceeds first).
        Higher ID = Lower priority (yields).
        
        Args:
            other_vehicle_id: ID of the other vehicle
            
        Returns:
            True if this vehicle should yield (wait), False if it has priority
        """
        other_priority = self._extract_priority(other_vehicle_id)
        
        # Lower priority value = higher priority
        # If our priority is higher (lower number), we don't yield
        # If our priority is lower (higher number), we yield
        should_yield = self.priority > other_priority
        
        if should_yield and self.waiting_for_vehicle != other_vehicle_id:
            # Log yielding behavior with detailed priority info
            self.model.log_activity(
                self.unique_id,
                f"CONFLICT DETECTED with {other_vehicle_id} - Yielding (my priority={self.priority}, their priority={other_priority})",
                "warning"
            )
            self.waiting_for_vehicle = other_vehicle_id
            self.wait_counter = 0
        elif not should_yield and other_vehicle_id:
            # Log when we have priority
            if not hasattr(self, '_logged_priority_for') or self._logged_priority_for != other_vehicle_id:
                self.model.log_activity(
                    self.unique_id,
                    f"CONFLICT DETECTED with {other_vehicle_id} - Proceeding (my priority={self.priority} > their priority={other_priority})",
                    "info"
                )
                self._logged_priority_for = other_vehicle_id
        
        return should_yield
    
    def step(self):
        """Execute one step of the vehicle's behavior."""
        # If already completed, don't do anything
        if self.status == VehicleStatus.COMPLETED:
            return
        
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
            
            # COLLISION DETECTION: Check for potential collision with other vehicles
            threatening_vehicle = self._detect_collision_threat(next_pos)
            
            if threatening_vehicle:
                # Collision threat detected - check priority
                if self._should_yield(threatening_vehicle):
                    # We have lower priority - WAIT
                    self.wait_counter += 1
                    
                    # Log waiting (only once or when exceeding max wait)
                    if self.wait_counter == 1:
                        self.model.log_activity(
                            self.unique_id,
                            f"WAITING for {threatening_vehicle} to pass (conflict at {next_pos}, wait_count=1)",
                            "warning"
                        )
                    elif self.wait_counter % 3 == 0:  # Log every 3 ticks while waiting
                        self.model.log_activity(
                            self.unique_id,
                            f"⏳ Still waiting for {threatening_vehicle} (wait_count={self.wait_counter})",
                            "warning"
                        )
                    
                    # If waited too long, try replanning
                    if self.wait_counter >= self.max_wait_time:
                        self.model.log_activity(
                            self.unique_id,
                            f"Waited {self.wait_counter} ticks - attempting replan",
                            "warning"
                        )
                        self._replan()
                        self.waiting_for_vehicle = None
                        self.wait_counter = 0
                    
                    return  # Don't move this tick
                # else: We have higher priority, proceed with movement
            else:
                # No collision threat - clear waiting state
                if self.waiting_for_vehicle:
                    self.model.log_activity(
                        self.unique_id,
                        f"{self.waiting_for_vehicle} has passed - Path clear, resuming movement",
                        "action"
                    )
                    self.waiting_for_vehicle = None
                    self.wait_counter = 0
                    # Clear the priority log tracker
                    if hasattr(self, '_logged_priority_for'):
                        delattr(self, '_logged_priority_for')
            
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
                
                # Only change status to MOVING if not already EXITING
                if self.status != VehicleStatus.EXITING:
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
                                f"Successfully exited at {self.position}",
                                "success"
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
            # Only change status to MOVING if not already EXITING
            if self.status != VehicleStatus.EXITING:
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
        
        station_id = station.station_id if station else None
        
        if station:
            station.release(self.unique_id)
            # Log station release
            self.model.log_activity(
                self.unique_id,
                f"Finished charging at Station_{station_id} (battery: {self.battery_level:.1f}%) - Station now available",
                "action"
            )
        
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
                f"Heading to exit at {grid.exit_position}",
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
                f"Returning to idle state",
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
        # Log that assignment was received
        self.model.log_activity(
            self.unique_id,
            f"Received assignment to Station_{assignment.station_id} at {assignment.station_position} (negotiation_enabled={self.enable_negotiation})",
            "info"
        )
        
        # If negotiation is disabled, accept immediately
        if not self.enable_negotiation:
            self._accept_assignment(assignment)
            return
        
        # Evaluate assignment with negotiation logic
        should_accept, reason = self._evaluate_assignment(assignment)
        
        if should_accept:
            self._accept_assignment(assignment)
        else:
            # Reject and try to negotiate
            self._negotiate_assignment(assignment, reason)
    
    def _accept_assignment(self, assignment: AssignmentMessage):
        """Accept an assignment and proceed."""
        self.target_station = assignment.station_id
        self.target_position = assignment.station_position
        self.status = VehicleStatus.PLANNING
        
        # Log received assignment
        self.model.log_activity(
            self.unique_id,
            f"Accepted assignment to Station_{assignment.station_id} at {assignment.station_position}, planning path",
            "action"
        )
        
        # Plan path immediately
        self._plan_path_to_target()
        
        # Record metric
        if hasattr(self.model, 'metrics'):
            self.model.metrics.record_assignment(self.unique_id)
    
    def _evaluate_assignment(self, assignment: AssignmentMessage) -> Tuple[bool, str]:
        """
        Evaluate if assignment is acceptable.
        
        Returns:
            (should_accept, reason_if_not)
        """
        grid: Grid = self.model.grid
        assigned_station_pos = assignment.station_position
        
        # Calculate distance to assigned station
        distance_to_assigned = abs(self.position[0] - assigned_station_pos[0]) + \
                               abs(self.position[1] - assigned_station_pos[1])
        
        # Log evaluation
        self.model.log_activity(
            self.unique_id,
            f"Evaluating assignment to Station_{assignment.station_id} (distance={distance_to_assigned}, battery={self.battery_level:.1f}%)",
            "info"
        )
        
        # Check if distance exceeds max acceptable distance
        if distance_to_assigned > self.max_acceptable_distance:
            return False, f"distance_too_far (distance={distance_to_assigned} > max_acceptable={self.max_acceptable_distance}, battery={self.battery_level:.1f}%)"
        
        # Check if distance is too far for current battery (use safety margin)
        estimated_battery_cost = distance_to_assigned * self.battery_drain_rate * self.battery_safety_margin
        if self.battery_level - estimated_battery_cost < 10.0:  # Need at least 10% buffer
            return False, f"insufficient_battery (distance={distance_to_assigned}, cost={estimated_battery_cost:.1f}%, current={self.battery_level:.1f}%, margin={self.battery_safety_margin}x)"
        
        # For critical battery, be VERY selective - always prefer the absolute closest
        if self.battery_level < self.critical_battery_threshold:
            # Find ALL stations and their distances (not just available ones)
            min_distance = distance_to_assigned
            closest_station = None
            
            for station in grid.charging_stations:
                if station.station_id == assignment.station_id:
                    continue
                dist = abs(self.position[0] - station.position[0]) + \
                       abs(self.position[1] - station.position[1])
                if dist < min_distance:
                    min_distance = dist
                    closest_station = station
            
            # If there's a closer station (even if currently occupied), reject
            if closest_station:
                distance_diff = distance_to_assigned - min_distance
                return False, f"battery_critical_prefer_closer (assigned_dist={distance_to_assigned}, closer_Station_{closest_station.station_id}_dist={min_distance:.1f}, diff={distance_diff:.1f}, will_wait_if_needed)"
        
        # For non-critical battery, still check for significantly better alternatives
        # Only consider available stations
        for station in grid.charging_stations:
            if station.station_id == assignment.station_id:
                continue
            if station.is_available():  # Only consider available stations
                dist = abs(self.position[0] - station.position[0]) + \
                       abs(self.position[1] - station.position[1])
                
                # If alternative is significantly closer (> 30% closer)
                if dist < distance_to_assigned * (1 - self.distance_preference_factor):
                    distance_diff = distance_to_assigned - dist
                    return False, f"prefer_alternative_closer (assigned_dist={distance_to_assigned}, alternative_Station_{station.station_id}_dist={dist:.1f}, diff={distance_diff:.1f})"
        
        # Assignment is acceptable
        self.model.log_activity(
            self.unique_id,
            f"Assignment acceptable, will proceed to Station_{assignment.station_id}",
            "info"
        )
        return True, ""
    
    def _negotiate_assignment(self, assignment: AssignmentMessage, reason: str):
        """
        Negotiate with orchestrator about assignment.
        """
        grid: Grid = self.model.grid
        
        # Log rejection
        self.model.log_activity(
            self.unique_id,
            f"Rejecting assignment to Station_{assignment.station_id} - Reason: {reason}",
            "warning"
        )
        
        # Find alternative station proposal
        best_alternative = None
        best_distance = float('inf')
        
        for station in grid.charging_stations:
            if station.station_id == assignment.station_id:
                continue
            if station.is_available():
                dist = abs(self.position[0] - station.position[0]) + \
                       abs(self.position[1] - station.position[1])
                if dist < best_distance:
                    best_distance = dist
                    best_alternative = station
        
        if best_alternative:
            # Send counter-proposal
            self.model.log_activity(
                self.unique_id,
                f"Counter-proposal: Prefer Station_{best_alternative.station_id} at {best_alternative.position} (distance={best_distance:.1f} vs {abs(self.position[0] - assignment.station_position[0]) + abs(self.position[1] - assignment.station_position[1]):.1f})",
                "info"
            )
            
            msg = AssignmentCounterProposalMessage(
                sender_id=self.unique_id,
                receiver_id=str(self.model.orchestrator.unique_id),
                timestamp=self.model.schedule.steps,
                rejected_station_id=assignment.station_id,
                proposed_station_id=best_alternative.station_id,
                reason=reason,
                current_position=self.position,
                battery_level=self.battery_level
            )
            self.model.message_queue.append(msg)
        else:
            # No alternative, send rejection only
            self.model.log_activity(
                self.unique_id,
                f"No suitable alternative found, sending rejection",
                "warning"
            )
            
            msg = AssignmentRejectionMessage(
                sender_id=self.unique_id,
                receiver_id=str(self.model.orchestrator.unique_id),
                timestamp=self.model.schedule.steps,
                rejected_station_id=assignment.station_id,
                reason=reason,
                current_position=self.position,
                battery_level=self.battery_level
            )
            self.model.message_queue.append(msg)
    
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
