"""
Negotiating vehicle agent for Scenario 5.

This vehicle can:
1. Receive queue-based assignments
2. Evaluate if assignment is acceptable
3. Negotiate for better queue position
4. Wait for consensus before moving
"""

from typing import Tuple, Optional, List
from agents.vehicle import VehicleAgent, VehicleStatus
from core.messages import (
    MessageType, QueueAssignmentMessage, QueueNegotiationMessage,
    AssignmentAcceptedMessage, ConsensusReachedMessage
)


class NegotiatingVehicle(VehicleAgent):
    """
    Vehicle agent with queue negotiation capabilities.
    
    Extends VehicleAgent with:
    - Queue assignment evaluation
    - Negotiation decision-making
    - Consensus waiting
    """
    
    def __init__(self, unique_id, model, start_pos, battery_level=100.0):
        super().__init__(unique_id, model, position=start_pos, battery_level=battery_level)
        
        # Negotiation state
        self.assigned_queue_position = None
        self.assigned_station = None
        self.all_assignments = {}
        self.consensus_reached = False
        self.waiting_for_consensus = False
        
        # Message tracking (to avoid reprocessing)
        self.processed_message_ids = set()
        
        # Negotiation parameters
        self.max_acceptable_wait = 1  # Max acceptable queue position
        self.urgency_multiplier = 1.5  # How urgency affects negotiation
        
    def step(self):
        """Override step to handle consensus waiting and queue management."""
        # Process messages first
        self._process_negotiation_messages()
        
        # If waiting for consensus, don't move
        if self.waiting_for_consensus:
            self.model.log_activity(
                self.unique_id,
                f"⏳ Waiting for consensus (battery={self.battery_level:.1f}%)",
                "info"
            )
            return
            
        # After consensus, all vehicles can move to the station immediately
        # Queue management happens AT the station (only pos 0 can charge first)
        # This optimizes waiting time - vehicles travel concurrently instead of sequentially
                    
        # Otherwise execute normal vehicle logic
        super().step()
    
    def _detect_collision_threat(self, next_pos):
        """Override to allow multiple vehicles at charging stations.
        
        If the next position is a charging station, and another vehicle is there
        IDLE (waiting for queue), we should not treat it as a collision.
        Multiple vehicles can queue at the same station.
        """
        grid = self.model.grid
        station = grid.get_station_at(next_pos)
        
        # Check all other vehicles
        for vehicle_id, vehicle in self.model.vehicles.items():
            if vehicle_id == self.unique_id:
                continue
            
            # Skip completed vehicles
            if vehicle.status == VehicleStatus.COMPLETED:
                continue
            
            # Check if other vehicle is at our target position
            if vehicle.position == next_pos:
                # SPECIAL CASE: If next_pos is a charging station and the vehicle
                # there is IDLE (waiting for queue), allow us to approach
                if station and vehicle.status == VehicleStatus.IDLE:
                    # Check if it's their target station (they're waiting in queue)
                    if hasattr(vehicle, 'target_station') and vehicle.target_station == station.station_id:
                        continue  # Not a collision - they're waiting, we can approach
                
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
                    # Again, if it's a station and we're both going there for queue, allow it
                    if station and hasattr(self, 'target_station') and self.target_station == station.station_id:
                        if hasattr(vehicle, 'target_station') and vehicle.target_station == station.station_id:
                            continue  # Both queueing at same station - not a collision
                    
                    return vehicle_id
        
        return None
        
    def _sense(self):
        """Override sense to check queue position before attempting to charge.
        
        This ensures vehicles respect the queue order at the station.
        Only vehicles at position 0 in the queue can charge.
        Others must wait even if at the station.
        """
        grid = self.model.grid
        station = grid.get_station_at(self.position)
        
        # FIRST: Check if we're done charging (this must come before trying to occupy)
        if self.status == VehicleStatus.CHARGING and self.battery_level >= 90:
            # Use parent's _complete_charging() which handles station release AND exit setup
            self._complete_charging()
            # Mark that we've completed charging at this station
            self.charging_complete = True
            return
        
        # If at a station
        if station:
            # Check if this is our target station
            if station.station_id == self.target_station:
                # Skip if we already completed charging here
                if hasattr(self, 'charging_complete') and self.charging_complete:
                    return
                
                # Check if we have a queue position assigned
                if hasattr(self, 'assigned_queue_position'):
                    # Check if we can proceed (all vehicles ahead are done)
                    if not self._check_can_proceed():
                        # We must wait - set status to IDLE and clear path to prevent movement
                        self.status = VehicleStatus.IDLE
                        self.path = []
                        self.path_index = 0
                        self.target_position = None  # Also clear target to prevent replanning
                        return
                
                # Either no queue position or we can proceed - try to occupy
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
            # Create unique message ID
            msg_id = (msg.msg_type, msg.timestamp, msg.sender_id)
            
            # Skip if already processed
            if msg_id in self.processed_message_ids:
                continue
                
            # Mark as processed
            self.processed_message_ids.add(msg_id)
            
            # Process message
            if msg.msg_type == MessageType.QUEUE_ASSIGNMENT:
                self._handle_queue_assignment(msg)
            elif msg.msg_type == MessageType.CONSENSUS_REACHED:
                self._handle_consensus(msg)
                
    def _handle_queue_assignment(self, msg: QueueAssignmentMessage):
        """Handle queue assignment from orchestrator."""
        self.assigned_station = msg.station_id
        self.assigned_queue_position = msg.queue_position
        self.all_assignments = msg.all_assignments
        self.waiting_for_consensus = True
        
        self.model.log_activity(
            self.unique_id,
            f"📨 Received assignment: Station_{msg.station_id}, Queue Position {msg.queue_position}/{msg.total_in_queue}",
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
        
        # Calculate distance to station
        distance = abs(self.position[0] - station_pos[0]) + abs(self.position[1] - station_pos[1])
        
        # Calculate battery urgency (0-10 scale)
        urgency = self._calculate_urgency()
        
        # Decision rules:
        
        # Rule 1: If critically low battery (< 20%) and not first in queue
        if self.battery_level < 20.0 and queue_pos > 0:
            return False, f"critical_battery (battery={self.battery_level:.1f}%, need position 0)"
            
        # Rule 2: If very close to station but assigned late position
        if distance <= 3 and queue_pos > 1:
            return False, f"closer_position (distance={distance}, should be earlier)"
            
        # Rule 3: If battery urgency high and queue position too late
        if urgency >= 7.0 and queue_pos > self.max_acceptable_wait:
            return False, f"urgent_task (urgency={urgency:.1f}, position {queue_pos} too late)"
            
        # Rule 4: Check if another station has shorter queue and is closer
        for vid, (sid, qpos) in self.all_assignments.items():
            if sid != station_id:
                other_station_pos = None
                # Find station position from model
                for station in self.model.grid.charging_stations:
                    if station.station_id == sid:
                        other_station_pos = station.position
                        break
                        
                if other_station_pos:
                    other_distance = abs(self.position[0] - other_station_pos[0]) + abs(self.position[1] - other_station_pos[1])
                    other_queue_length = sum(1 for v, (s, q) in self.all_assignments.items() if s == sid)
                    
                    # If other station is closer AND has shorter queue
                    if other_distance < distance - 2 and other_queue_length < msg.total_in_queue:
                        return False, f"better_alternative (Station_{sid} is closer with shorter queue)"
                        
        # Accept assignment
        return True, "acceptable"
        
    def _calculate_urgency(self) -> float:
        """
        Calculate urgency score (0-10).
        
        Based on:
        - Battery level (lower = more urgent)
        - Distance to nearest station
        """
        # Battery component (0-10): 100% → 0, 0% → 10
        battery_urgency = (100.0 - self.battery_level) / 10.0
        
        # Apply multiplier for very low battery
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
            f"✅ Accepted assignment: Station_{station_id}, Position {queue_pos}",
            "success"
        )
        
    def _send_negotiation(self, msg: QueueAssignmentMessage, reason: str):
        """Send negotiation message."""
        # Determine desired position based on urgency
        urgency = self._calculate_urgency()
        
        # If critical battery, want position 0
        if self.battery_level < 20.0:
            desired_pos = 0
        # If urgent, want earlier position
        elif urgency >= 7.0:
            desired_pos = max(0, msg.queue_position - 1)
        # Otherwise, want one position earlier
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
            f"💬 Negotiating: want position {desired_pos} (reason: {reason}, urgency={urgency:.1f})",
            "warning"
        )
        
    def _handle_consensus(self, msg: ConsensusReachedMessage):
        """Handle consensus reached message."""
        self.all_assignments = msg.final_assignments
        self.waiting_for_consensus = False
        self.consensus_reached = True
        
        # Get our final assignment
        if self.unique_id in msg.final_assignments:
            station_id, queue_pos = msg.final_assignments[self.unique_id]
            self.assigned_station = station_id
            self.assigned_queue_position = queue_pos
            
            self.model.log_activity(
                self.unique_id,
                f"🚀 Consensus reached! Final assignment: Station_{station_id}, Position {queue_pos}",
                "success"
            )
            
            # Find station position and set as target
            for station in self.model.grid.charging_stations:
                if station.station_id == station_id:
                    self.target_station = station_id  # VehicleAgent expects this
                    self.target_position = station.position  # VehicleAgent expects this
                    
                    # If we're first in queue (position 0), we can start moving
                    # If we're not first, we still set targets but DON'T transition from IDLE
                    if queue_pos == 0:
                        # Status is already IDLE, VehicleAgent._plan() will detect target and transition to PLANNING
                        self.model.log_activity(
                            self.unique_id,
                            f"🎯 First in queue! Can proceed to Station_{station_id}",
                            "info"
                        )
                    else:
                        # Set targets but stay IDLE (will check queue in step())
                        self.model.log_activity(
                            self.unique_id,
                            f"⏸️  Position {queue_pos} in queue. Waiting for turn... (targets set)",
                            "info"
                        )
                    break
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
            
        # Check if all vehicles with lower queue position at our station have completed
        for vid, (sid, qpos) in self.all_assignments.items():
            if sid == self.assigned_station and qpos < self.assigned_queue_position:
                # Check if this vehicle is still active
                if vid in self.model.vehicles:
                    other_vehicle = self.model.vehicles[vid]
                    # Vehicle ahead must have EXITING or COMPLETED before we can proceed
                    # If they're still idle, planning, moving, or charging, we must wait
                    if other_vehicle.status not in [VehicleStatus.EXITING, VehicleStatus.COMPLETED]:
                        return False
                        
        # All vehicles ahead completed, we can go
        return True
