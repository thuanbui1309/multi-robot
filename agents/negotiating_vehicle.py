"""Negotiating vehicle with queue-based assignment and negotiation capabilities."""

from typing import Tuple, Optional, List
from agents.vehicle import VehicleAgent, VehicleStatus
from core.messages import (
    MessageType, QueueAssignmentMessage, QueueNegotiationMessage,
    AssignmentAcceptedMessage, ConsensusReachedMessage
)


class NegotiatingVehicle(VehicleAgent):
    """Vehicle with queue negotiation and consensus waiting."""
    
    def __init__(self, unique_id, model, start_pos, battery_level=100.0):
        super().__init__(unique_id, model, position=start_pos, battery_level=battery_level)
        
        self.assigned_queue_position = None
        self.assigned_station = None
        self.all_assignments = {}
        self.consensus_reached = False
        self.waiting_for_consensus = False
        
        self.processed_message_ids = set()
        
        self.max_acceptable_wait = 1
        self.urgency_multiplier = 1.5
        
    def step(self):
        """Process negotiation messages then execute normal vehicle behavior."""
        self._process_negotiation_messages()
        
        # If waiting for consensus, don't move
        if self.waiting_for_consensus:
            self.model.log_activity(
                self.unique_id,
                f"Waiting for consensus (battery={self.battery_level:.1f}%)",
                "info"
            )
            return
            
        super().step()
    
    def _detect_collision_threat(self, next_pos):
        """Manage station access based on queue position (only position 0 can enter station)."""
        grid = self.model.grid
        station = grid.get_station_at(next_pos)
        
        if station and hasattr(self, 'target_station') and station.station_id == self.target_station:
            my_queue_pos = getattr(self, 'assigned_queue_position', None)
            if my_queue_pos is not None and my_queue_pos != 0:
                return -1
            
            my_queue_pos = getattr(self, 'assigned_queue_position', None)
            
            for vid, vehicle in self.model.vehicles.items():
                if vid == self.unique_id:
                    continue
                
                if (hasattr(vehicle, 'target_station') and vehicle.target_station == self.target_station):
                    other_queue_pos = getattr(vehicle, 'assigned_queue_position', None)
                    
                    if my_queue_pos is None:
                        if other_queue_pos is not None:
                            if vehicle.status not in [VehicleStatus.EXITING, VehicleStatus.COMPLETED]:
                                return vid
                    
                    elif other_queue_pos is not None:
                        if other_queue_pos < my_queue_pos:
                            if vehicle.status not in [VehicleStatus.EXITING, VehicleStatus.COMPLETED]:
                                return vid
                        elif (other_queue_pos > my_queue_pos and vehicle.position == next_pos):
                            continue
                    
                    if vehicle.position == next_pos and other_queue_pos is None:
                        if my_queue_pos is not None:
                            continue
                        else:
                            return vid
        
        for vehicle_id, vehicle in self.model.vehicles.items():
            if vehicle_id == self.unique_id:
                continue
            
            if vehicle.status == VehicleStatus.COMPLETED:
                continue
            
            if vehicle.position == next_pos and not station:
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
        """Use queue positions for priority when both vehicles target same station."""
        if hasattr(self, 'target_station'):
            other_vehicle = self.model.vehicles.get(other_vehicle_id)
            if other_vehicle and hasattr(other_vehicle, 'target_station'):
                if other_vehicle.target_station == self.target_station:
                    my_queue_pos = getattr(self, 'assigned_queue_position', None)
                    other_queue_pos = getattr(other_vehicle, 'assigned_queue_position', None)
                    
                    if my_queue_pos is None and other_queue_pos is not None:
                        return True
                    elif my_queue_pos is not None and other_queue_pos is None:
                        return False
                    elif my_queue_pos is not None and other_queue_pos is not None:
                        return my_queue_pos > other_queue_pos
        
        return super()._should_yield(other_vehicle_id)
        
    def _sense(self):
        """Handle charging completion and queue-based station access."""
        grid = self.model.grid
        
        if self.status == VehicleStatus.CHARGING and self.battery_level >= 90:
            self._complete_charging()
            self.charging_complete = True
            return
        
        if self.status == VehicleStatus.CHARGING:
            if hasattr(self, 'assigned_queue_position'):
                for vid, vehicle in self.model.vehicles.items():
                    if vid == self.unique_id:
                        continue
                    
                    if (hasattr(vehicle, 'target_station') and vehicle.target_station == self.target_station and
                        hasattr(vehicle, 'assigned_queue_position') and
                        vehicle.assigned_queue_position < self.assigned_queue_position):
                        if vehicle.status not in [VehicleStatus.EXITING, VehicleStatus.COMPLETED]:
                            station = grid.get_station_at(self.position)
                            if station:
                                station.release(self.unique_id)
                            self.status = VehicleStatus.IDLE
                            self.path = []
                            self.path_index = 0
                            self.model.log_activity(
                                self.unique_id,
                                f"Yielding station to higher-priority {vid}",
                                "info"
                            )
                            return
        
        station = grid.get_station_at(self.position)
        if station:
            # Check if this is target station
            if station.station_id == self.target_station:
                if hasattr(self, 'charging_complete') and self.charging_complete:
                    return
                
                if not self._check_can_proceed():
                    if self.status != VehicleStatus.CHARGING:
                        station_pos = station.position
                        adjacent_cells = [
                            (station_pos[0] + dx, station_pos[1] + dy)
                            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]
                            if grid.is_valid_position(station_pos[0] + dx, station_pos[1] + dy)
                        ]
                        
                        for adj_pos in adjacent_cells:
                            occupied = False
                            for vid, v in self.model.vehicles.items():
                                if vid != self.unique_id and v.position == adj_pos:
                                    occupied = True
                                    break
                            if not occupied and not grid.get_station_at(adj_pos):
                                self.position = adj_pos
                                self.model.log_activity(
                                    self.unique_id,
                                    f"Moved to {adj_pos} to wait for queue position {self.assigned_queue_position}",
                                    "info"
                                )
                                return
                        
                        self.model.log_activity(
                            self.unique_id,
                            f"At station but waiting for queue position {self.assigned_queue_position} to be ready",
                            "info"
                        )
                    return
                
                if station.occupy(self.unique_id):
                    self.status = VehicleStatus.CHARGING
                    self.charging_start_time = self.model.schedule.steps
                    self.model.log_activity(
                        self.unique_id,
                        f"Started charging at Station_{station.station_id} (Battery: {self.battery_level:.1f}%)",
                        "success"
                    )
                    return
        
    def _process_negotiation_messages(self):
        """Process queue assignment and consensus messages."""
        messages_for_me = [
            msg for msg in self.model.message_queue
            if msg.receiver_id == self.unique_id
        ]
        
        for msg in messages_for_me:
            msg_id = (msg.msg_type, msg.timestamp, msg.sender_id)
            if msg_id in self.processed_message_ids:
                continue
                
            self.processed_message_ids.add(msg_id)
            
            if msg.msg_type == MessageType.QUEUE_ASSIGNMENT:
                self._handle_queue_assignment(msg)
            elif msg.msg_type == MessageType.CONSENSUS_REACHED:
                self._handle_consensus(msg)
                
    def _handle_queue_assignment(self, msg: QueueAssignmentMessage):
        """Handle queue assignment from orchestrator."""
        if self.consensus_reached:
            old_pos = self.assigned_queue_position
            self.assigned_station = msg.station_id
            self.assigned_queue_position = msg.queue_position
            self.all_assignments = msg.all_assignments
            
            if msg.queue_position == 0 and old_pos != 0:
                for station in self.model.grid.charging_stations:
                    if station.station_id == msg.station_id:
                        self.target_position = station.position
                        break
            
            if old_pos != msg.queue_position:
                self.model.log_activity(
                    self.unique_id,
                    f"Queue position updated: {old_pos} → {msg.queue_position}" + 
                    (" - My turn! Moving to station..." if msg.queue_position == 0 else " (still waiting)"),
                    "success" if msg.queue_position == 0 else "info"
                )
            return
        
        # Initial assignment - proceed with negotiation process
        self.assigned_station = msg.station_id
        self.assigned_queue_position = msg.queue_position
        self.all_assignments = msg.all_assignments
        self.waiting_for_consensus = True
        
        self.model.log_activity(
            self.unique_id,
            f"Received assignment: Station_{msg.station_id}, Position {msg.queue_position} (out of {msg.total_in_queue} vehicles)",
            "info"
        )
        
        # Evaluate if we should accept or negotiate
        should_accept, reason = self._evaluate_assignment(msg)
        
        if should_accept:
            self._send_acceptance(msg.station_id, msg.queue_position)
        else:
            self._send_negotiation(msg, reason)
            
    def _evaluate_assignment(self, msg: QueueAssignmentMessage) -> Tuple[bool, str]:
        """
        Evaluate if assignment is acceptable.
        
        Returns:
            (should_accept, reason)
        """
        station_id = msg.station_id
        queue_pos = msg.queue_position
        station_pos = msg.station_position
        
        distance = abs(self.position[0] - station_pos[0]) + abs(self.position[1] - station_pos[1])
        urgency = self._calculate_urgency()

        if self.battery_level < 20.0 and queue_pos > 0:
            return False, f"critical_battery (battery={self.battery_level:.1f}%, need position 0)"
            
        if distance <= 2 and queue_pos > 2:
            return False, f"closer_position (distance={distance}, should be earlier)"
            
        if urgency >= 8.0 and queue_pos > self.max_acceptable_wait:
            return False, f"urgent_task (urgency={urgency:.1f}, position {queue_pos} too late)"
            
        for vid, (sid, qpos) in self.all_assignments.items():
            if sid != station_id:
                other_station_pos = None
                for station in self.model.grid.charging_stations:
                    if station.station_id == sid:
                        other_station_pos = station.position
                        break
                        
                if other_station_pos:
                    other_distance = abs(self.position[0] - other_station_pos[0]) + abs(self.position[1] - other_station_pos[1])
                    other_queue_length = sum(1 for v, (s, q) in self.all_assignments.items() if s == sid)
                    
                    if other_distance < distance - 2 and other_queue_length < msg.total_in_queue:
                        return False, f"better_alternative (Station_{sid} is closer with shorter queue)"
                        
        return True, "acceptable"
        
    def _calculate_urgency(self) -> float:
        """
        Calculate urgency score (0-10).
        
        Based on:
        - Battery level (lower = more urgent)
        - Distance to nearest station
        """
        battery_urgency = (100.0 - self.battery_level) / 10.0
        
        if self.battery_level < 20.0:
            battery_urgency *= self.urgency_multiplier
            
        return min(10.0, battery_urgency)
        
    def _send_acceptance(self, station_id: int, queue_pos: int):
        """Send acceptance message."""
        msg = AssignmentAcceptedMessage(
            sender_id=self.unique_id,
            receiver_id=str(self.model.orchestrator.unique_id),
            timestamp=self.model.schedule.steps,
            station_id=station_id,
            queue_position=queue_pos
        )
        self.model.message_queue.append(msg)
        
        self.model.log_activity(
            self.unique_id,
            f"Accepted assignment: Station_{station_id}, Position {queue_pos}",
            "success"
        )
        
    def _send_negotiation(self, msg: QueueAssignmentMessage, reason: str):
        """Send negotiation message."""
        urgency = self._calculate_urgency()

        if self.battery_level < 20.0:
            desired_pos = 0
        elif urgency >= 7.0:
            desired_pos = max(0, msg.queue_position - 1)
        else:
            desired_pos = max(0, msg.queue_position - 1)
            
        neg_msg = QueueNegotiationMessage(
            sender_id=self.unique_id,
            receiver_id=str(self.model.orchestrator.unique_id),
            timestamp=self.model.schedule.steps,
            station_id=msg.station_id,
            current_queue_position=msg.queue_position,
            desired_queue_position=desired_pos,
            reason=reason,
            urgency_score=urgency
        )
        self.model.message_queue.append(neg_msg)
        
        self.model.log_activity(
            self.unique_id,
            f"Negotiating: want position {desired_pos} (reason: {reason}, urgency={urgency:.1f})",
            "warning"
        )
        
    def _handle_consensus(self, msg: ConsensusReachedMessage):
        """Handle consensus reached message."""
        self.all_assignments = msg.final_assignments
        
        # Get our assignment from the message
        if self.unique_id in msg.final_assignments:
            station_id, queue_pos = msg.final_assignments[self.unique_id]

            if self.consensus_reached:
                old_pos = self.assigned_queue_position
                self.assigned_station = station_id
                self.assigned_queue_position = queue_pos
                
                if queue_pos == 0 and old_pos != 0:
                    for station in self.model.grid.charging_stations:
                        if station.station_id == station_id:
                            self.target_position = station.position
                            break
                
                if old_pos != queue_pos:
                    self.model.log_activity(
                        self.unique_id,
                        f"Queue position updated: {old_pos} → {queue_pos}" +
                        (" - Now my turn! Moving to station..." if queue_pos == 0 else ""),
                        "success" if queue_pos == 0 else "info"
                    )
                return
            
            self.waiting_for_consensus = False
            self.consensus_reached = True
            self.assigned_station = station_id
            self.assigned_queue_position = queue_pos
            
            self.model.log_activity(
                self.unique_id,
                f"Consensus reached! Final assignment: Station_{station_id}, Position {queue_pos}",
                "success"
            )
            
            for station in self.model.grid.charging_stations:
                if station.station_id == station_id:
                    self.target_station = station_id
                    
                    if queue_pos == 0:
                        self.target_position = station.position
                        self.model.log_activity(
                            self.unique_id,
                            f"First in queue! Can proceed to Station_{station_id} at {station.position}",
                            "info"
                        )
                    else:
                        station_pos = station.position
                        grid = self.model.grid
                        adjacent_cells = [
                            (station_pos[0] + dx, station_pos[1] + dy)
                            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]
                            if grid.is_valid_position(station_pos[0] + dx, station_pos[1] + dy)
                        ]
                        
                        best_wait_pos = None
                        min_dist = float('inf')
                        for adj_pos in adjacent_cells:
                            if grid.get_station_at(adj_pos):
                                continue

                            dist = abs(self.position[0] - adj_pos[0]) + abs(self.position[1] - adj_pos[1])
                            if dist < min_dist:
                                min_dist = dist
                                best_wait_pos = adj_pos
                        
                        self.target_position = best_wait_pos if best_wait_pos else station.position
                        self.model.log_activity(
                            self.unique_id,
                            f"Position {queue_pos} in queue. Moving to wait at {self.target_position}...",
                            "info"
                        )
                    break
                    
    def _check_can_proceed(self) -> bool:
        """
        Check if vehicle can proceed based on queue position.
        
        Returns True if:
        - We're position 0 (first)
        - All vehicles ahead of us have completed charging (exited or completed status)
        """
        if self.assigned_queue_position == 0:
            return True
            
        for vid, (sid, qpos) in self.all_assignments.items():
            if sid == self.assigned_station and qpos < self.assigned_queue_position:
                if vid in self.model.vehicles:
                    other_vehicle = self.model.vehicles[vid]
                    if other_vehicle.status not in [VehicleStatus.EXITING, VehicleStatus.COMPLETED]:
                        return False
                        
        return True