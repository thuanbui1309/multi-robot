"""
Queue-based negotiating orchestrator for Scenario 5.

This orchestrator implements a consensus-based assignment protocol where:
1. Collects all charging requests
2. Creates initial queue assignments using Hungarian algorithm
3. Waits for all agents to accept or negotiate
4. Processes negotiations and updates queues
5. Only allows movement when consensus is reached
"""

from typing import Dict, List, Tuple, Optional
from mesa import Agent
from core.messages import (
    Message, MessageType, VehicleStatus,
    StatusUpdateMessage, QueueAssignmentMessage,
    QueueNegotiationMessage, AssignmentAcceptedMessage,
    ConsensusReachedMessage
)
from core.assign import VehicleStationAssigner


class StationQueue:
    """Manages a queue for a charging station."""
    
    def __init__(self, station_id: int, capacity: int):
        self.station_id = station_id
        self.capacity = capacity
        self.queue: List[str] = []  # Ordered list of vehicle_ids
        
    def add_vehicle(self, vehicle_id: str, position: Optional[int] = None):
        """Add vehicle to queue at specific position or end."""
        if position is None or position >= len(self.queue):
            self.queue.append(vehicle_id)
        else:
            self.queue.insert(position, vehicle_id)
            
    def remove_vehicle(self, vehicle_id: str):
        """Remove vehicle from queue."""
        if vehicle_id in self.queue:
            self.queue.remove(vehicle_id)
            
    def get_position(self, vehicle_id: str) -> Optional[int]:
        """Get vehicle's position in queue."""
        try:
            return self.queue.index(vehicle_id)
        except ValueError:
            return None
            
    def swap_positions(self, vehicle1_id: str, vehicle2_id: str) -> bool:
        """Swap two vehicles in queue."""
        try:
            pos1 = self.queue.index(vehicle1_id)
            pos2 = self.queue.index(vehicle2_id)
            self.queue[pos1], self.queue[pos2] = self.queue[pos2], self.queue[pos1]
            return True
        except ValueError:
            return False
            
    def is_full(self) -> bool:
        """Check if queue is at capacity."""
        return len(self.queue) >= self.capacity
        
    def __repr__(self):
        return f"StationQueue({self.station_id}, queue={self.queue})"


class NegotiatingOrchestrator(Agent):
    """
    Orchestrator that manages queue-based assignments with negotiation.
    
    Workflow:
    1. COLLECTING: Gather charging requests from vehicles
    2. ASSIGNING: Create initial queue assignments
    3. NEGOTIATING: Wait for all responses (accept/negotiate)
    4. CONSENSUS: All accepted → broadcast go signal
    5. MONITORING: Track vehicles as they charge
    """
    
    def __init__(self, unique_id, model, battery_threshold=30.0):
        super().__init__(model)
        self.unique_id = unique_id
        self.battery_threshold = battery_threshold
        self.assigner = VehicleStationAssigner()
        
        # State tracking
        self.vehicle_states: Dict[str, Dict] = {}
        self.station_states: Dict[int, Dict] = {}
        self.station_queues: Dict[int, StationQueue] = {}
        
        # Negotiation state
        self.phase = "MONITORING"  # COLLECTING, ASSIGNING, NEGOTIATING, CONSENSUS, MONITORING
        self.pending_requests: List[str] = []  # Vehicle IDs needing assignment
        self.pending_responses: Dict[str, str] = {}  # {vehicle_id: "pending"/"accepted"/"negotiating"}
        self.negotiation_round = 0
        self.max_negotiation_rounds = 5
        
        # Message tracking (to avoid reprocessing)
        self.processed_message_ids = set()
        
        # Assignment tracking
        self.current_assignments: Dict[str, Tuple[int, int]] = {}  # {vehicle_id: (station_id, queue_pos)}
        self.consensus_reached = False
        
    def step(self):
        """Execute one step of orchestrator logic."""
        # Update station states from grid
        self._update_station_states()
        
        # Process incoming messages
        self._process_messages()
        
        # Execute phase-specific logic
        if self.phase == "COLLECTING":
            self._check_collection_complete()
        elif self.phase == "ASSIGNING":
            self._make_queue_assignments()
        elif self.phase == "NEGOTIATING":
            self._process_negotiations()
        elif self.phase == "CONSENSUS":
            self._broadcast_consensus()
        elif self.phase == "MONITORING":
            self._monitor_vehicles()
            self._check_for_new_requests()
            
    def _update_station_states(self):
        """Update states of all charging stations."""
        grid = self.model.grid
        
        for station in grid.charging_stations:
            self.station_states[station.station_id] = {
                'id': station.station_id,
                'position': station.position,
                'capacity': station.capacity,
                'occupied': len(station.occupied_slots),
                'load': station.get_load(),
            }
            
    def _process_messages(self):
        """Process messages from vehicles."""
        messages_to_process = [
            msg for msg in self.model.message_queue
            if msg.receiver_id == str(self.unique_id)
        ]
        
        for msg in messages_to_process:
            # Create unique message ID to avoid reprocessing
            msg_id = (msg.msg_type, msg.timestamp, msg.sender_id)
            
            # Skip if already processed
            if msg_id in self.processed_message_ids:
                continue
                
            # Mark as processed
            self.processed_message_ids.add(msg_id)
            
            # Process message
            if msg.msg_type == MessageType.STATUS_UPDATE:
                self._handle_status_update(msg)
            elif msg.msg_type == MessageType.QUEUE_NEGOTIATION:
                self._handle_negotiation(msg)
            elif msg.msg_type == MessageType.ASSIGNMENT_ACCEPTED:
                self._handle_acceptance(msg)
            elif msg.msg_type == MessageType.CHARGING_COMPLETE:
                self._handle_charging_complete(msg)
                
    def _handle_status_update(self, msg: StatusUpdateMessage):
        """Handle vehicle status update."""
        vehicle_id = msg.sender_id
        
        # Update vehicle state
        self.vehicle_states[vehicle_id] = {
            'id': vehicle_id,
            'position': msg.position,
            'battery_level': msg.battery_level,
            'status': msg.status,
            'target_station': msg.target_station
        }
        
        # Check if vehicle needs charging and we're in monitoring phase
        if (self.phase == "MONITORING" and 
            msg.status == VehicleStatus.IDLE and 
            msg.battery_level < self.battery_threshold and
            vehicle_id not in self.pending_requests and
            vehicle_id not in self.current_assignments):
            
            self.pending_requests.append(vehicle_id)
            self.model.log_activity(
                "Orchestrator",
                f"📥 Received charging request from {vehicle_id} (battery={msg.battery_level:.1f}%)",
                "info"
            )
            
    def _check_for_new_requests(self):
        """Check if we have new requests and should start collection phase."""
        if len(self.pending_requests) > 0 and self.phase == "MONITORING":
            # Any requests → start collection phase
            self.phase = "COLLECTING"
            self.model.log_activity(
                "Orchestrator",
                f"🔄 Starting collection phase with {len(self.pending_requests)} requests",
                "info"
            )
            # Wait a few steps to collect more requests
            self.collection_wait = 2
            
    def _check_collection_complete(self):
        """Check if collection phase is complete."""
        if hasattr(self, 'collection_wait'):
            self.collection_wait -= 1
            if self.collection_wait <= 0:
                self.phase = "ASSIGNING"
                self.model.log_activity(
                    "Orchestrator",
                    f"✅ Collection complete: {len(self.pending_requests)} vehicles need charging",
                    "info"
                )
                
    def _create_queue_assignments(self, vehicles: List[Dict], stations: List[Dict]) -> Dict[str, int]:
        """
        Create queue-based assignments that support station capacity > 1.
        
        Uses a greedy approach:
        1. Sort vehicles by urgency (battery level)
        2. For each vehicle, assign to nearest station with available queue space
        3. Allow multiple vehicles per station (up to capacity * 2 for queueing)
        
        Args:
            vehicles: List of vehicle state dicts
            stations: List of station state dicts
            
        Returns:
            Dict mapping vehicle_id to station_id
        """
        assignments = {}
        
        # Track how many vehicles assigned to each station
        station_queue_counts = {s['id']: 0 for s in stations}
        max_queue_per_station = {s['id']: s['capacity'] * 2 for s in stations}  # Allow 2x capacity in queue
        
        # For initial assignment, sort by distance to nearest station (not battery)
        # This creates opportunity for negotiation where closer vehicle gets priority
        # but more critical vehicle can negotiate to swap
        def distance_to_nearest_station(vehicle):
            vehicle_pos = vehicle['position']
            min_dist = float('inf')
            for station in stations:
                station_pos = station['position']
                dist = abs(vehicle_pos[0] - station_pos[0]) + abs(vehicle_pos[1] - station_pos[1])
                min_dist = min(min_dist, dist)
            return min_dist
            
        sorted_vehicles = sorted(vehicles, key=distance_to_nearest_station)
        
        for vehicle in sorted_vehicles:
            vehicle_id = vehicle['id']
            vehicle_pos = vehicle['position']
            
            # Find best station for this vehicle
            best_station = None
            best_score = float('inf')
            
            for station in stations:
                station_id = station['id']
                station_pos = station['position']
                
                # Check if station has queue space
                if station_queue_counts[station_id] >= max_queue_per_station[station_id]:
                    continue
                
                # Calculate distance
                distance = abs(vehicle_pos[0] - station_pos[0]) + abs(vehicle_pos[1] - station_pos[1])
                
                # Calculate score: prioritize distance and queue length
                queue_length = station_queue_counts[station_id]
                score = distance * 2 + queue_length * 5  # Weight distance more than queue length
                
                if score < best_score:
                    best_score = score
                    best_station = station_id
                    
            if best_station is not None:
                assignments[vehicle_id] = best_station
                station_queue_counts[best_station] += 1
            else:
                # No available station
                assignments[vehicle_id] = None
                
        return assignments
                
    def _make_queue_assignments(self):
        """Create initial queue assignments using Hungarian algorithm."""
        if not self.pending_requests:
            self.phase = "MONITORING"
            return
            
        # Get vehicles needing charge
        vehicles = [self.vehicle_states[vid] for vid in self.pending_requests]
        
        # Get available stations
        available_stations = [
            self.station_states[sid] 
            for sid in self.station_states.keys()
        ]
        
        if not available_stations:
            self.model.log_activity(
                "Orchestrator",
                "⚠️ No stations available for assignment",
                "warning"
            )
            self.phase = "MONITORING"
            return
            
        # Use greedy queue-based assignment (supports capacity > 1)
        assignments = self._create_queue_assignments(vehicles, available_stations)
        
        self.model.log_activity(
            "Orchestrator",
            f"📊 Queue assignment created for {len(assignments)} out of {len(vehicles)} vehicles",
            "info"
        )
        
        # Build station queues
        self.station_queues.clear()
        for sid in self.station_states.keys():
            capacity = self.station_states[sid]['capacity']
            self.station_queues[sid] = StationQueue(sid, capacity * 2)  # Allow queue to be 2x capacity
            
        # Assign vehicles to queues
        self.current_assignments.clear()
        for vehicle_id, station_id in assignments.items():
            if station_id is not None:
                queue = self.station_queues[station_id]
                queue.add_vehicle(vehicle_id)
                queue_pos = queue.get_position(vehicle_id)
                self.current_assignments[vehicle_id] = (station_id, queue_pos)
                
        # Log initial assignments
        self.model.log_activity(
            "Orchestrator",
            f"📋 Initial queue assignments created (Round {self.negotiation_round}):",
            "info"
        )
        for sid, queue in self.station_queues.items():
            if queue.queue:  # Only log non-empty queues
                self.model.log_activity(
                    "Orchestrator",
                    f"  Station_{sid}: {queue.queue}",
                    "info"
                )
            
        # Send queue assignments to all vehicles that got assignments
        self._send_queue_assignments()
        
        # Move to negotiation phase
        self.phase = "NEGOTIATING"
        # Only track vehicles that actually got assignments
        assigned_vehicles = [vid for vid in self.pending_requests if vid in self.current_assignments]
        self.pending_responses = {vid: "pending" for vid in assigned_vehicles}
        
        # Log vehicles that didn't get assignments
        unassigned = [vid for vid in self.pending_requests if vid not in self.current_assignments]
        if unassigned:
            self.model.log_activity(
                "Orchestrator",
                f"⚠️ {len(unassigned)} vehicles not assigned (no capacity): {', '.join(unassigned)}",
                "warning"
            )
        
        self.negotiation_round += 1
        
    def _send_queue_assignments(self):
        """Send queue assignment messages to all pending vehicles."""
        # Build full assignment dict for transparency
        all_assignments = {
            vid: (sid, qpos) 
            for vid, (sid, qpos) in self.current_assignments.items()
        }
        
        for vehicle_id in self.pending_requests:
            if vehicle_id in self.current_assignments:
                station_id, queue_pos = self.current_assignments[vehicle_id]
                station_pos = self.station_states[station_id]['position']
                
                msg = QueueAssignmentMessage(
                    sender_id=str(self.unique_id),
                    receiver_id=vehicle_id,
                    timestamp=self.model.schedule.steps,
                    station_id=station_id,
                    station_position=station_pos,
                    queue_position=queue_pos,
                    total_in_queue=len(self.station_queues[station_id].queue),
                    all_assignments=all_assignments
                )
                self.model.message_queue.append(msg)
                
                self.model.log_activity(
                    "Orchestrator",
                    f"📤 Sent queue assignment to {vehicle_id}: Station_{station_id}, Position {queue_pos}",
                    "info"
                )
                
    def _handle_negotiation(self, msg: QueueNegotiationMessage):
        """Handle negotiation message from vehicle."""
        vehicle_id = msg.sender_id
        self.pending_responses[vehicle_id] = "negotiating"
        
        self.model.log_activity(
            "Orchestrator",
            f"💬 {vehicle_id} negotiates: wants position {msg.desired_queue_position} at Station_{msg.station_id} (reason: {msg.reason}, urgency={msg.urgency_score})",
            "warning"
        )
        
        # Store negotiation for processing
        if not hasattr(self, 'negotiations'):
            self.negotiations = []
        self.negotiations.append(msg)
        
    def _handle_acceptance(self, msg: AssignmentAcceptedMessage):
        """Handle acceptance message from vehicle."""
        vehicle_id = msg.sender_id
        self.pending_responses[vehicle_id] = "accepted"
        
        self.model.log_activity(
            "Orchestrator",
            f"✅ {vehicle_id} accepted: Station_{msg.station_id}, Position {msg.queue_position}",
            "info"
        )
        
    def _process_negotiations(self):
        """Process all pending negotiations and update assignments."""
        # Check if all responses received
        if any(status == "pending" for status in self.pending_responses.values()):
            return  # Still waiting for responses
            
        # Check if all accepted
        if all(status == "accepted" for status in self.pending_responses.values()):
            self.phase = "CONSENSUS"
            self.model.log_activity(
                "Orchestrator",
                "🎉 Consensus reached! All vehicles accepted assignments.",
                "success"
            )
            return
            
        # Process negotiations
        if hasattr(self, 'negotiations') and self.negotiations:
            self.model.log_activity(
                "Orchestrator",
                f"🔄 Processing {len(self.negotiations)} negotiations...",
                "info"
            )
            
            # Simple strategy: sort by urgency and try to accommodate
            self.negotiations.sort(key=lambda n: n.urgency_score, reverse=True)
            
            for neg in self.negotiations:
                vehicle_id = neg.sender_id
                station_id = neg.station_id
                desired_pos = neg.desired_queue_position
                
                # Try to accommodate: swap with vehicle at desired position
                queue = self.station_queues[station_id]
                current_pos = queue.get_position(vehicle_id)
                
                if desired_pos < len(queue.queue):
                    other_vehicle = queue.queue[desired_pos]
                    if queue.swap_positions(vehicle_id, other_vehicle):
                        # Update assignments
                        self.current_assignments[vehicle_id] = (station_id, desired_pos)
                        self.current_assignments[other_vehicle] = (station_id, current_pos)
                        
                        self.model.log_activity(
                            "Orchestrator",
                            f"🔀 Swapped {vehicle_id} ↔ {other_vehicle} at Station_{station_id}",
                            "info"
                        )
                        
            self.negotiations.clear()
            
        # Check negotiation round limit
        if self.negotiation_round >= self.max_negotiation_rounds:
            self.phase = "CONSENSUS"
            self.model.log_activity(
                "Orchestrator",
                f"⏰ Max negotiation rounds ({self.max_negotiation_rounds}) reached. Forcing consensus.",
                "warning"
            )
        else:
            # Send updated assignments and wait for new responses
            self.model.log_activity(
                "Orchestrator",
                f"📤 Sending updated assignments (Round {self.negotiation_round + 1})...",
                "info"
            )
            self._send_queue_assignments()
            self.pending_responses = {vid: "pending" for vid in self.pending_requests}
            self.negotiation_round += 1
            
    def _broadcast_consensus(self):
        """Broadcast consensus message to all vehicles."""
        all_assignments = {
            vid: (sid, qpos) 
            for vid, (sid, qpos) in self.current_assignments.items()
        }
        
        for vehicle_id in self.pending_requests:
            msg = ConsensusReachedMessage(
                sender_id=str(self.unique_id),
                receiver_id=vehicle_id,
                timestamp=self.model.schedule.steps,
                final_assignments=all_assignments,
                can_proceed=True
            )
            self.model.message_queue.append(msg)
            
        self.model.log_activity(
            "Orchestrator",
            "🚀 CONSENSUS REACHED! All vehicles can now proceed to stations.",
            "success"
        )
        
        # Move to monitoring phase
        self.consensus_reached = True
        self.phase = "MONITORING"
        self.pending_requests.clear()
        self.pending_responses.clear()
        self.negotiation_round = 0
        
    def _handle_charging_complete(self, msg):
        """Handle vehicle charging completion."""
        vehicle_id = msg.sender_id
        
        # Remove from assignments and queues
        if vehicle_id in self.current_assignments:
            station_id, queue_pos = self.current_assignments[vehicle_id]
            self.station_queues[station_id].remove_vehicle(vehicle_id)
            del self.current_assignments[vehicle_id]
            
            self.model.log_activity(
                "Orchestrator",
                f"🔋 {vehicle_id} completed charging at Station_{station_id}",
                "info"
            )
            
    def _monitor_vehicles(self):
        """Monitor vehicle states during normal operation."""
        pass  # Handled by status updates
        
    def register_station(self, station_id: int, position: Tuple[int, int], capacity: int):
        """Register a charging station."""
        self.station_states[station_id] = {
            'id': station_id,
            'position': position,
            'capacity': capacity,
            'occupied': 0,
            'load': 0.0
        }
        
    def get_state(self) -> Dict:
        """Get orchestrator state."""
        return {
            'phase': self.phase,
            'assigned_vehicles': len(self.current_assignments),
            'pending_requests': len(self.pending_requests),
            'vehicles_tracked': len(self.vehicle_states),
            'stations_tracked': len(self.station_states),
            'negotiation_round': self.negotiation_round,
            'consensus_reached': self.consensus_reached,
        }
