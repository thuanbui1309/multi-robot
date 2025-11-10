from typing import Dict, List, Optional, Set
from mesa import Agent
from core.assign import VehicleStationAssigner
from core.messages import (
    VehicleStatus, AssignmentMessage, StatusUpdateMessage,
    ChargingCompleteMessage, AssignmentRejectionMessage,
    AssignmentCounterProposalMessage
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
        self.active_assignments: Dict[str, int] = {}  
        self.station_assignments: Dict[int, str] = {}  
        self.pending_assignments: Set[str] = set()
        
        # Configuration
        self.battery_threshold = 30.0  
        self.assignment_interval = 1  
        self.last_assignment_time = -1 
    
    def step(self):
        """Execute one step of orchestrator behavior."""
        current_time = self.model.schedule.steps
        self._process_messages()
        self._update_station_states()

        if current_time - self.last_assignment_time >= self.assignment_interval:
            self._make_assignments()
            self.last_assignment_time = current_time
        
        self._monitor_vehicles()
    
    def _process_messages(self):
        """Process incoming messages from vehicles."""
        for msg in self.model.message_queue:
            if msg.receiver_id != str(self.unique_id): 
                continue
            
            if isinstance(msg, StatusUpdateMessage):
                self.vehicle_states[msg.sender_id] = {
                    'id': msg.sender_id,
                    'position': msg.position,
                    'battery_level': msg.battery_level,
                    'status': msg.status,
                    'target_station': msg.target_station,
                    'last_update': msg.timestamp
                }
                
            elif isinstance(msg, ChargingCompleteMessage):
                if msg.sender_id in self.active_assignments:
                    station_id = self.active_assignments[msg.sender_id]
                    del self.active_assignments[msg.sender_id]
                    
                    if station_id in self.station_assignments:
                        del self.station_assignments[station_id]
                    
                    self.model.log_activity(
                        "Orchestrator",
                        f"{msg.sender_id} completed charging at Station_{station_id}",
                        "action"
                    )
            
            elif isinstance(msg, AssignmentRejectionMessage):
                self._handle_assignment_rejection(msg)
                    
            elif isinstance(msg, AssignmentCounterProposalMessage):
                self._handle_counter_proposal(msg)
    
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
        
        if vehicle_id in self.active_assignments:
            del self.active_assignments[vehicle_id]

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
        vehicles_needing_charge = []
        for vehicle_id, state in self.vehicle_states.items():
            if vehicle_id in self.active_assignments:
                continue
            if state['status'] != VehicleStatus.IDLE:
                continue  
            if state['battery_level'] >= self.battery_threshold:
                continue
                
            vehicles_needing_charge.append(state)
        
        if not vehicles_needing_charge:
            return
        
        if len(vehicles_needing_charge) > 1:
            self.model.log_activity(
                "Orchestrator",
                f"Multiple vehicles requesting charging ({len(vehicles_needing_charge)} vehicles)",
                "info"
            )
            for vehicle in vehicles_needing_charge:
                self.model.log_activity(
                    "Orchestrator",
                    f"  Candidate: {vehicle['id']} at {vehicle['position']} with {vehicle['battery_level']:.1f}% battery",
                    "info"
                )
        else:
            vehicle = vehicles_needing_charge[0]
            self.model.log_activity(
                "Orchestrator",
                f"Received charging request from {vehicle['id']} at {vehicle['position']} with {vehicle['battery_level']:.1f}% battery",
                "info"
            )
        
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
        
        assignments = self.assigner.assign(
            vehicles_needing_charge,
            [self.station_states[sid] for sid in available_stations]
        )
        
        for vehicle_id, station_id in assignments.items():
            if station_id is not None:
                self._send_assignment(vehicle_id, station_id)
                self.station_assignments[station_id] = vehicle_id
    
    def _send_assignment(self, vehicle_id: str, station_id: int):
        """Send assignment to a vehicle."""
        station = self.station_states.get(station_id)
        if not station:
            return
        
        vehicle_state = self.vehicle_states.get(vehicle_id)
        if vehicle_state:
            distance = self.assigner.calculate_distance(
                vehicle_state['position'],
                station['position']
            )
            
            battery_level = vehicle_state['battery_level']
            
            self.model.log_activity(
                "Orchestrator",
                f"Assigning {vehicle_id} to Station_{station_id} at {station['position']} - Reason: distance={distance:.1f}, battery={battery_level:.1f}%",
                "action"
            )
        else:
            # Fallback if no vehicle state
            self.model.log_activity(
                "Orchestrator",
                f"Assigning {vehicle_id} to Station_{station_id} at {station['position']}",
                "action"
            )
        
        # Create assignment message
        msg = AssignmentMessage(
            sender_id=str(self.unique_id), 
            receiver_id=vehicle_id,
            timestamp=self.model.schedule.steps,
            station_id=station_id,
            station_position=station['position']
        )
        
        self.model.message_queue.append(msg)
        self.active_assignments[vehicle_id] = station_id
        self.pending_assignments.add(vehicle_id)
        
        for agent in self.model.schedule.agents:
            if hasattr(agent, 'unique_id') and agent.unique_id == vehicle_id:
                if hasattr(agent, 'receive_assignment'):
                    agent.receive_assignment(msg)
                break
    
    def _monitor_vehicles(self):
        """Monitor vehicles for issues."""
        for vehicle_id, state in self.vehicle_states.items():
            if state['status'] == VehicleStatus.STUCK:
                pass
            
            # Check for critically low battery
            if state['battery_level'] < 10.0:
                if vehicle_id not in self.active_assignments:
                    self._assign_priority_vehicle(vehicle_id)
    
    def _assign_priority_vehicle(self, vehicle_id: str):
        """Assign a priority vehicle immediately."""
        state = self.vehicle_states.get(vehicle_id)
        if not state:
            return
        
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
    
    def _handle_assignment_rejection(self, msg: AssignmentRejectionMessage):
        """Handle vehicle rejecting an assignment."""
        self.model.log_activity(
            "Orchestrator",
            f"Received rejection from {msg.sender_id} for Station_{msg.rejected_station_id}: {msg.reason}",
            "warning"
        )
        
        if msg.sender_id in self.active_assignments:
            del self.active_assignments[msg.sender_id]
        if msg.rejected_station_id in self.station_assignments:
            del self.station_assignments[msg.rejected_station_id]
        
        self.model.log_activity(
            "Orchestrator",
            f"Finding alternative assignment for {msg.sender_id}",
            "info"
        )
        
        vehicle_state = {
            'id': msg.sender_id,
            'position': msg.current_position,
            'battery_level': msg.battery_level,
            'status': VehicleStatus.IDLE
        }
        
        available_stations = [
            sid for sid, sstate in self.station_states.items()
            if sid != msg.rejected_station_id and 
               sid not in self.station_assignments and 
               sstate['occupied'] < sstate['capacity']
        ]
        
        if available_stations:
            assignments = self.assigner.assign(
                [vehicle_state],
                [self.station_states[sid] for sid in available_stations]
            )
            
            if msg.sender_id in assignments and assignments[msg.sender_id] is not None:
                station_id = assignments[msg.sender_id]
                self._send_assignment(msg.sender_id, station_id)
                self.station_assignments[station_id] = msg.sender_id
            else:
                self.model.log_activity(
                    "Orchestrator",
                    f"No suitable alternative found for {msg.sender_id}",
                    "warning"
                )
        else:
            self.model.log_activity(
                "Orchestrator",
                f"No available stations for {msg.sender_id} after rejection",
                "warning"
            )
    
    def _handle_counter_proposal(self, msg: AssignmentCounterProposalMessage):
        """Handle vehicle proposing alternative station."""
        self.model.log_activity(
            "Orchestrator",
            f"Received counter-proposal from {msg.sender_id}: reject Station_{msg.rejected_station_id}, prefer Station_{msg.proposed_station_id} - Reason: {msg.reason}",
            "info"
        )
        
        proposed_station = self.station_states.get(msg.proposed_station_id)
        
        if not proposed_station:
            self.model.log_activity(
                "Orchestrator",
                f"Proposed Station_{msg.proposed_station_id} does not exist",
                "warning"
            )
            self._handle_assignment_rejection(msg) 
            return
        
        if msg.proposed_station_id in self.station_assignments:
            self.model.log_activity(
                "Orchestrator",
                f"Proposed Station_{msg.proposed_station_id} already assigned to {self.station_assignments[msg.proposed_station_id]}",
                "warning"
            )
            self._handle_assignment_rejection(msg) 
            return
        
        if proposed_station['occupied'] >= proposed_station['capacity']:
            self.model.log_activity(
                "Orchestrator",
                f"Proposed Station_{msg.proposed_station_id} is at full capacity",
                "warning"
            )
            self._handle_assignment_rejection(msg) 
            return
        
        self.model.log_activity(
            "Orchestrator",
            f"Accepting counter-proposal: Reassigning {msg.sender_id} from Station_{msg.rejected_station_id} to Station_{msg.proposed_station_id}",
            "action"
        )
        
        if msg.sender_id in self.active_assignments:
            del self.active_assignments[msg.sender_id]
        if msg.rejected_station_id in self.station_assignments:
            del self.station_assignments[msg.rejected_station_id]
        
        self._send_assignment(msg.sender_id, msg.proposed_station_id)
        self.station_assignments[msg.proposed_station_id] = msg.sender_id
    
    def get_state(self) -> Dict:
        """Get orchestrator state."""
        return {
            'assigned_vehicles': len(self.active_assignments),
            'pending_assignments': len(self.pending_assignments),
            'vehicles_tracked': len(self.vehicle_states),
            'stations_tracked': len(self.station_states),
        }