from typing import Dict, List, Optional, Set
from mesa import Agent
from core.assign import VehicleStationAssigner
from core.messages import (
    VehicleStatus, AssignmentMessage, StatusUpdateMessage,
    ChargingCompleteMessage
)
from core.grid import Grid, ChargingStation

class OrchestratorAgent(Agent):
    """
    Central orchestrator that:
    - Monitors all vehicles and stations
    - Assigns vehicles to optimal charging stations
    - Handles conflicts and re-assignments
    """
    
    def __init__(self, unique_id: str, model):
        """
        Initialize orchestrator agent.
        
        Args:
            unique_id: Unique identifier
            model: Mesa model reference
        """
        super().__init__(model)
        
        # Assignment system
        self.assigner = VehicleStationAssigner(
            distance_weight=1.0,
            battery_weight=2.0,
            load_weight=0.5
        )
        
        # Tracking
        self.vehicle_states: Dict[str, Dict] = {}
        self.station_states: Dict[int, Dict] = {}
        self.active_assignments: Dict[str, int] = {}  # vehicle_id -> station_id
        self.station_assignments: Dict[int, str] = {}  # station_id -> vehicle_id
        self.pending_assignments: Set[str] = set()
        
        # Configuration
        self.battery_threshold = 30.0  # Assign charging when battery < 30%
        self.assignment_interval = 1  # Reassign every tick for immediate response
        self.last_assignment_time = -1  # Start at -1 to trigger assignment on first tick
    
    def step(self):
        """Execute one step of orchestrator behavior."""
        current_time = self.model.schedule.steps
        
        # 1. Process incoming messages
        self._process_messages()
        
        # 2. Update station states
        self._update_station_states()
        
        # 3. Check if it's time to make assignments
        if current_time - self.last_assignment_time >= self.assignment_interval:
            self._make_assignments()
            self.last_assignment_time = current_time
        
        # 4. Monitor for issues
        self._monitor_vehicles()
    
    def _process_messages(self):
        """Process incoming messages from vehicles."""
        for msg in self.model.message_queue:
            if msg.receiver_id != str(self.unique_id):  # Compare with string
                continue
            
            if isinstance(msg, StatusUpdateMessage):
                # Update vehicle state
                self.vehicle_states[msg.sender_id] = {
                    'id': msg.sender_id,  # Add vehicle ID
                    'position': msg.position,
                    'battery_level': msg.battery_level,
                    'status': msg.status,
                    'target_station': msg.target_station,
                    'last_update': msg.timestamp
                }
                
            elif isinstance(msg, ChargingCompleteMessage):
                # Vehicle finished charging, remove assignment
                if msg.sender_id in self.active_assignments:
                    station_id = self.active_assignments[msg.sender_id]
                    del self.active_assignments[msg.sender_id]
                    
                    # Only delete if exists in station_assignments
                    if station_id in self.station_assignments:
                        del self.station_assignments[station_id]
                    
                    # Log completion
                    self.model.log_activity(
                        "Orchestrator",
                        f"{msg.sender_id} completed charging at Station_{station_id}",
                        "action"
                    )
                    
            elif isinstance(msg, PathRequestMessage):
                # Handle path request (for future use)
                pass
    
    def _handle_status_update(self, msg: StatusUpdateMessage):
        """Handle vehicle status update."""
        self.vehicle_states[msg.sender_id] = {
            'id': msg.sender_id,
            'position': msg.position,
            'battery_level': msg.battery_level,
            'status': msg.status,
            'target_station': msg.target_station,
            'last_update': msg.timestamp,
        }
    
    def _handle_charging_complete(self, msg: ChargingCompleteMessage):
        """Handle charging completion."""
        vehicle_id = msg.sender_id
        
        # Remove from assigned vehicles
        if vehicle_id in self.active_assignments:
            del self.active_assignments[vehicle_id]
        
        # Remove from pending
        self.pending_assignments.discard(vehicle_id)
    
    def _update_station_states(self):
        """Update states of all charging stations."""
        grid: Grid = self.model.grid
        
        for station in grid.charging_stations:
            self.station_states[station.station_id] = {
                'id': station.station_id,
                'position': station.position,
                'capacity': station.capacity,
                'occupied': len(station.occupied_slots),
                'load': station.get_load(),
            }
            
            # Record metrics
            if hasattr(self.model, 'metrics'):
                self.model.metrics.record_station_usage(
                    station.station_id,
                    len(station.occupied_slots)
                )
    
    def _make_assignments(self):
        """Check for vehicles needing charging and assign stations."""
        # Find vehicles needing charging
        vehicles_needing_charge = []
        for vehicle_id, state in self.vehicle_states.items():
            # Skip if already assigned or not needing charge
            if vehicle_id in self.active_assignments:
                continue
            if state['status'] != VehicleStatus.IDLE:
                continue  
            if state['battery_level'] >= self.battery_threshold:
                continue
                
            vehicles_needing_charge.append(state)
        
        if not vehicles_needing_charge:
            return
        
        # Log assignment check - only when we have vehicles needing charge
        for vehicle in vehicles_needing_charge:
            self.model.log_activity(
                "Orchestrator",
                f"Received charging request from {vehicle['id']} at {vehicle['position']} with {vehicle['battery_level']:.1f}% battery",
                "info"
            )
        
        # Get available stations
        available_stations = [
            sid for sid, sstate in self.station_states.items()
            if sid not in self.station_assignments and sstate['occupied'] < sstate['capacity']
        ]
        
        if not available_stations:
            self.model.log_activity(
                "Orchestrator",
                "No available stations",
                "warning"
            )
            return
        
        # Use Hungarian algorithm for assignment
        assignments = self.assigner.assign(
            vehicles_needing_charge,
            [self.station_states[sid] for sid in available_stations]
        )
        
        # Send assignments
        for vehicle_id, station_id in assignments.items():
            if station_id is not None:
                self._send_assignment(vehicle_id, station_id)
                self.station_assignments[station_id] = vehicle_id
    
    def _send_assignment(self, vehicle_id: str, station_id: int):
        """Send assignment to a vehicle."""
        station = self.station_states.get(station_id)
        if not station:
            return
        
        # Log assignment
        vehicle_state = self.vehicle_states.get(vehicle_id)
        battery_info = f" (battery: {vehicle_state['battery_level']:.1f}%)" if vehicle_state else ""
        
        self.model.log_activity(
            "Orchestrator",
            f"Assigning {vehicle_id} to Station_{station_id} at {station['position']}{battery_info}",
            "action"
        )
        
        # Create assignment message
        msg = AssignmentMessage(
            sender_id=str(self.unique_id),  # Convert to string
            receiver_id=vehicle_id,
            timestamp=self.model.schedule.steps,
            station_id=station_id,
            station_position=station['position']
        )
        
        # Add to model's outbox for delivery
        self.model.message_queue.append(msg)
        
        # Track assignment
        self.active_assignments[vehicle_id] = station_id
        self.pending_assignments.add(vehicle_id)
        
        # Deliver directly to vehicle
        for agent in self.model.schedule.agents:
            if hasattr(agent, 'unique_id') and agent.unique_id == vehicle_id:
                if hasattr(agent, 'receive_assignment'):
                    agent.receive_assignment(msg)
                break
    
    def _monitor_vehicles(self):
        """Monitor vehicles for issues."""
        for vehicle_id, state in self.vehicle_states.items():
            # Check for stuck vehicles
            if state['status'] == VehicleStatus.STUCK:
                # Could implement recovery logic here
                pass
            
            # Check for critically low battery
            if state['battery_level'] < 10.0:
                # Priority assignment
                if vehicle_id not in self.active_assignments:
                    self._assign_priority_vehicle(vehicle_id)
    
    def _assign_priority_vehicle(self, vehicle_id: str):
        """Assign a priority vehicle immediately."""
        state = self.vehicle_states.get(vehicle_id)
        if not state:
            return
        
        # Find nearest available station
        min_distance = float('inf')
        best_station = None
        
        for station in self.station_states.values():
            if station['load'] >= 1.0:
                continue
            
            distance = self.assigner.calculate_distance(
                state['position'],
                station['position']
            )
            
            if distance < min_distance:
                min_distance = distance
                best_station = station
        
        if best_station:
            self._send_assignment(vehicle_id, best_station['id'])
    
    def get_state(self) -> Dict:
        """Get orchestrator state."""
        return {
            'assigned_vehicles': len(self.active_assignments),
            'pending_assignments': len(self.pending_assignments),
            'vehicles_tracked': len(self.vehicle_states),
            'stations_tracked': len(self.station_states),
        }
