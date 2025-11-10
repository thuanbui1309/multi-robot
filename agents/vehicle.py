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
    """Autonomous vehicle with A* pathfinding, collision avoidance, and charging."""
    
    def __init__(
        self,
        unique_id: str,
        model,
        position: Tuple[int, int],
        battery_level: float = 100.0,
        battery_drain_rate: float = 0.5,
        charge_rate: float = 5.0,
        enable_negotiation: bool = False
    ):
        super().__init__(model)
        self.unique_id = unique_id
        
        self.position = position
        self.path: List[Tuple[int, int]] = []
        self.path_index = 0
        
        self.battery_level = battery_level
        self.battery_drain_rate = battery_drain_rate
        self.charge_rate = charge_rate
        self.battery_threshold = 30.0
        
        self.status = VehicleStatus.IDLE
        self.target_station: Optional[int] = None
        self.target_position: Optional[Tuple[int, int]] = None
        
        self.planner = AStarPlanner()
        self.stuck_counter = 0
        self.max_stuck_time = 5
        
        self.priority = self._extract_priority(unique_id)
        self.waiting_for_vehicle: Optional[str] = None
        self.wait_counter = 0
        self.max_wait_time = 10
        
        self.enable_negotiation = enable_negotiation
        self.max_acceptable_distance = 10
        self.critical_battery_threshold = 25.0
        self.distance_preference_factor = 0.2
        self.battery_safety_margin = 2.0
        
        self.total_distance = 0.0
        self.num_replans = 0
        self.charging_start_time: Optional[int] = None
        
        self.has_requested_charging = False
    
    def _extract_priority(self, vehicle_id: str) -> int:
        """Extract priority from vehicle ID (lower number = higher priority)."""
        try:
            return int(vehicle_id.split('_')[1])
        except (IndexError, ValueError):
            return hash(vehicle_id) % 1000
    
    @property
    def needs_charging(self) -> bool:
        return self.battery_level < self.battery_threshold
    
    def _detect_collision_threat(self, next_pos: Tuple[int, int]) -> Optional[str]:
        """Check if moving to next_pos would collide with another vehicle."""
        for vehicle_id, vehicle in self.model.vehicles.items():
            if vehicle_id == self.unique_id:
                continue
            
            if vehicle.status == VehicleStatus.COMPLETED:
                continue
                
            if vehicle.position == next_pos:
                return vehicle_id
            
            if (hasattr(vehicle, 'path') and vehicle.path and 
                vehicle.path_index < len(vehicle.path)):
                other_next = vehicle.path[vehicle.path_index]
                
                if other_next == self.position and next_pos == vehicle.position:
                    return vehicle_id
                
                if other_next == next_pos:
                    return vehicle_id
        
        return None
    
    def _should_yield(self, other_vehicle_id: str) -> bool:
        """
        Determine if should yield based on priority.
        Priority: EXITING vehicles yield > Lower queue position > Lower ID.
        """
        other_vehicle = self.model.vehicles.get(other_vehicle_id)
        if not other_vehicle:
            return False
        
        if self.status == VehicleStatus.EXITING and other_vehicle.status != VehicleStatus.EXITING:
            should_yield = True
            if self.waiting_for_vehicle != other_vehicle_id:
                self.model.log_activity(
                    self.unique_id,
                    f"CONFLICT DETECTED with {other_vehicle_id} - Yielding (I'm EXITING, they need to charge)",
                    "warning"
                )
                self.waiting_for_vehicle = other_vehicle_id
                self.wait_counter = 0
            return True
        
        if other_vehicle.status == VehicleStatus.EXITING and self.status != VehicleStatus.EXITING:
            if not hasattr(self, '_logged_priority_for') or self._logged_priority_for != other_vehicle_id:
                self.model.log_activity(
                    self.unique_id,
                    f"CONFLICT DETECTED with {other_vehicle_id} - Proceeding (They're EXITING, I need to charge)",
                    "info"
                )
                self._logged_priority_for = other_vehicle_id
            return False
        
        other_priority = self._extract_priority(other_vehicle_id)
        should_yield = self.priority > other_priority
        
        if should_yield and self.waiting_for_vehicle != other_vehicle_id:
            self.model.log_activity(
                self.unique_id,
                f"CONFLICT DETECTED with {other_vehicle_id} - Yielding (my priority={self.priority}, their priority={other_priority})",
                "warning"
            )
            self.waiting_for_vehicle = other_vehicle_id
            self.wait_counter = 0
        elif not should_yield and other_vehicle_id:
            if not hasattr(self, '_logged_priority_for') or self._logged_priority_for != other_vehicle_id:
                self.model.log_activity(
                    self.unique_id,
                    f"CONFLICT DETECTED with {other_vehicle_id} - Proceeding (my priority={self.priority} > their priority={other_priority})",
                    "info"
                )
                self._logged_priority_for = other_vehicle_id
        
        return should_yield
    
    def step(self):
        """Execute vehicle behavior: sense, plan, act, report."""
        if self.status == VehicleStatus.COMPLETED:
            return
        
        self._sense()
        
        if self.needs_charging and not self.has_requested_charging and self.status == VehicleStatus.IDLE:
            self._request_charging()
        
        self._plan()
        self._act()
        self._report_status()
    
    def _sense(self):
        """Update status based on environment."""
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
        
    def _plan(self):
        """Plan next action based on current state."""
        if self.status == VehicleStatus.CHARGING:
            # Do nothing, just charge
            return
        
        if self.status == VehicleStatus.IDLE:
            # If we have a target, transition to planning
            if self.target_position and self.target_station is not None:
                self.status = VehicleStatus.PLANNING
                self.model.log_activity(
                    self.unique_id,
                    f"Received target assignment, starting to plan path to Station_{self.target_station}",
                    "action"
                )
            else:
                return
        
        if self.status == VehicleStatus.EXITING and self.target_position and not self.path:
            self._plan_path_to_target()
        
        if self.target_position and not self.path:
            self._plan_path_to_target()
        
        if self.path and self.path_index < len(self.path):
            next_pos = self.path[self.path_index]
            grid: Grid = self.model.grid
            
            if not grid.is_walkable(next_pos[0], next_pos[1]):
                self._replan()
    
    def _act(self):
        """Execute planned action."""
        if self.status == VehicleStatus.CHARGING:
            # Charge battery
            self.battery_level = min(100.0, self.battery_level + self.charge_rate)
            return
        
        if self.status == VehicleStatus.IDLE:
            old_battery = self.battery_level
            self.battery_level = max(0.0, self.battery_level - 0.1)
            
            if old_battery > 20 and self.battery_level <= 20:
                self.model.log_activity(
                    self.unique_id,
                    f"Battery critically low: {self.battery_level:.1f}%, waiting for assignment",
                    "warning"
                )
            return
        
        if self.path and self.path_index < len(self.path):
            next_pos = self.path[self.path_index]
            
            threatening_vehicle = self._detect_collision_threat(next_pos)
            
            if threatening_vehicle:
                if self._should_yield(threatening_vehicle):
                    self.wait_counter += 1
                    
                    if self.wait_counter == 1:
                        self.model.log_activity(
                            self.unique_id,
                            f"WAITING for {threatening_vehicle} to pass (conflict at {next_pos}, wait_count=1)",
                            "warning"
                        )
                    elif self.wait_counter % 3 == 0:
                        self.model.log_activity(
                            self.unique_id,
                            f"Still waiting for {threatening_vehicle} (wait_count={self.wait_counter})",
                            "warning"
                        )
                    
                    if self.wait_counter >= self.max_wait_time:
                        self.model.log_activity(
                            self.unique_id,
                            f"Waited {self.wait_counter} ticks - attempting replan",
                            "warning"
                        )
                        self._replan()
                        self.waiting_for_vehicle = None
                        self.wait_counter = 0
                    
                    return
            else:
                if self.waiting_for_vehicle:
                    self.model.log_activity(
                        self.unique_id,
                        f"{self.waiting_for_vehicle} has passed - Path clear, resuming movement",
                        "action"
                    )
                    self.waiting_for_vehicle = None
                    self.wait_counter = 0
                    if hasattr(self, '_logged_priority_for'):
                        delattr(self, '_logged_priority_for')
            
            reservation_table = self.model.reservation_table
            current_time = self.model.schedule.steps
            
            if reservation_table.reserve(next_pos, current_time + 1, self.unique_id):
                old_pos = self.position
                self.position = next_pos
                self.path_index += 1
                
                distance = abs(next_pos[0] - old_pos[0]) + abs(next_pos[1] - old_pos[1])
                self.total_distance += distance
                self.battery_level = max(0.0, self.battery_level - self.battery_drain_rate)
                
                if self.status != VehicleStatus.EXITING:
                    self.status = VehicleStatus.MOVING
                self.stuck_counter = 0
                
                if self.path_index == 1:
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
                
                reservation_table.release(old_pos, current_time, self.unique_id)
                
                if self.path_index >= len(self.path):
                    self.path = []
                    self.path_index = 0
                    if self.position == self.target_position:
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
                self.stuck_counter += 1
                if self.stuck_counter >= self.max_stuck_time:
                    self._replan()
                    self.stuck_counter = 0
    
    def _plan_path_to_target(self):
        """Plan A* path to target position."""
        if not self.target_position:
            return
        
        grid: Grid = self.model.grid
        reservation_table = self.model.reservation_table
        current_time = self.model.schedule.steps
        
        blocked = reservation_table.get_blocked_cells(
            current_time + 1,
            exclude_vehicle=self.unique_id
        )
        
        path, cost = self.planner.plan(
            start=self.position,
            goal=self.target_position,
            is_walkable=grid.is_walkable,
            get_neighbors=grid.get_neighbors,
            blocked_cells=blocked
        )
        
        if path:
            self.path = path[1:]
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
        
        self.path = []
        self.path_index = 0
        
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
        
        station_pos = self.position
        moved_away = False
        exit_pos = grid.exit_position if grid.exit_position else None
        directions = [(0, 1), (0, -1), (-1, 0), (1, 0)]  # down, up, left, right
        
        if exit_pos:
            def exit_distance(direction):
                dx, dy = direction
                new_pos = (station_pos[0] + dx, station_pos[1] + dy)
                return abs(new_pos[0] - exit_pos[0]) + abs(new_pos[1] - exit_pos[1])
            directions = sorted(directions, key=exit_distance)
        
        for dx, dy in directions:
            new_x = station_pos[0] + dx
            new_y = station_pos[1] + dy
            
            # Check if position is valid and walkable
            if (0 <= new_x < grid.width and 
                0 <= new_y < grid.height and
                grid.is_walkable(new_x, new_y)):
                
                # Check if no other vehicle is there OR planning to go there
                occupied = False
                for other_vehicle in self.model.vehicles.values():
                    if other_vehicle.unique_id == self.unique_id:
                        continue
                    
                    # Check current position
                    if other_vehicle.position == (new_x, new_y):
                        occupied = True
                        break
                    
                    # Check if this is on their path (next step)
                    if (hasattr(other_vehicle, 'path') and 
                        other_vehicle.path and 
                        other_vehicle.path_index < len(other_vehicle.path)):
                        next_pos = other_vehicle.path[other_vehicle.path_index]
                        if next_pos == (new_x, new_y):
                            occupied = True
                            break
                
                if not occupied:
                    # Move to this position
                    old_pos = self.position
                    self.position = (new_x, new_y)
                    moved_away = True
                    self.model.log_activity(
                        self.unique_id,
                        f"Moved away from station {old_pos} → {self.position} to clear path",
                        "info"
                    )
                    break
        
        if not moved_away:
            self.model.log_activity(
                self.unique_id,
                f"Could not move away from station - all adjacent cells blocked/occupied",
                "warning"
            )
        
        # Check if exit is configured
        if grid.exit_position:
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
        
        for station in grid.charging_stations:
            if station.station_id == assignment.station_id:
                continue
            if station.is_available():  # Only consider available stations
                dist = abs(self.position[0] - station.position[0]) + \
                       abs(self.position[1] - station.position[1])
                
                if dist < distance_to_assigned * (1 - self.distance_preference_factor):
                    distance_diff = distance_to_assigned - dist
                    return False, f"prefer_alternative_closer (assigned_dist={distance_to_assigned}, alternative_Station_{station.station_id}_dist={dist:.1f}, diff={distance_diff:.1f})"
        
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
        
        self.model.log_activity(
            self.unique_id,
            f"Rejecting assignment to Station_{assignment.station_id} - Reason: {reason}",
            "warning"
        )
        
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