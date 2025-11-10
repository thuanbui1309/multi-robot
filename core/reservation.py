from typing import Dict, Set, Tuple, Optional, List
from collections import defaultdict

class ReservationTable:
    """
    Maintains reservations for grid cells at specific time steps.
    Used to avoid collisions between multiple vehicles.
    """
    
    def __init__(self):
        """Initialize empty reservation table."""
        self.reservations: Dict[int, Dict[Tuple[int, int], str]] = defaultdict(dict)
        self.vehicle_reservations: Dict[str, Dict[int, Tuple[int, int]]] = defaultdict(dict)
    
    def reserve(
        self,
        position: Tuple[int, int],
        time_step: int,
        vehicle_id: str,
        duration: int = 1
    ) -> bool:
        """
        Try to reserve a position at a specific time step.
        
        Args:
            position: Grid position to reserve
            time_step: Time step for reservation
            vehicle_id: ID of the vehicle making reservation
            duration: How many time steps to reserve (default 1)
        
        Returns:
            True if reservation successful, False if conflict
        """
        # Check if position is already reserved at this time
        for t in range(time_step, time_step + duration):
            if position in self.reservations[t]:
                existing_id = self.reservations[t][position]
                if existing_id != vehicle_id:
                    return False  # Conflict with another vehicle
        
        # Make reservation
        for t in range(time_step, time_step + duration):
            self.reservations[t][position] = vehicle_id
            self.vehicle_reservations[vehicle_id][t] = position
        
        return True
    
    def reserve_path(
        self,
        path: List[Tuple[int, int]],
        start_time: int,
        vehicle_id: str
    ) -> bool:
        """
        Try to reserve entire path starting from start_time.
        
        Args:
            path: List of positions in the path
            start_time: Starting time step
            vehicle_id: ID of the vehicle
        
        Returns:
            True if entire path can be reserved, False otherwise
        """
        # First check if entire path is available
        for i, position in enumerate(path):
            time_step = start_time + i
            if position in self.reservations[time_step]:
                existing_id = self.reservations[time_step][position]
                if existing_id != vehicle_id:
                    return False
        
        # Reserve entire path
        for i, position in enumerate(path):
            time_step = start_time + i
            self.reservations[time_step][position] = vehicle_id
            self.vehicle_reservations[vehicle_id][time_step] = position
        
        return True
    
    def release(
        self,
        position: Tuple[int, int],
        time_step: int,
        vehicle_id: str
    ):
        """Release a specific reservation."""
        if time_step in self.reservations:
            if self.reservations[time_step].get(position) == vehicle_id:
                del self.reservations[time_step][position]
        
        if vehicle_id in self.vehicle_reservations:
            if time_step in self.vehicle_reservations[vehicle_id]:
                del self.vehicle_reservations[vehicle_id][time_step]
    
    def release_all(self, vehicle_id: str):
        """Release all reservations for a vehicle."""
        if vehicle_id not in self.vehicle_reservations:
            return
        
        # Get all time steps this vehicle has reserved
        time_steps = list(self.vehicle_reservations[vehicle_id].keys())
        
        for time_step in time_steps:
            position = self.vehicle_reservations[vehicle_id][time_step]
            if time_step in self.reservations:
                if self.reservations[time_step].get(position) == vehicle_id:
                    del self.reservations[time_step][position]
        
        del self.vehicle_reservations[vehicle_id]
    
    def release_future(self, vehicle_id: str, from_time: int):
        """Release all future reservations for a vehicle from a specific time."""
        if vehicle_id not in self.vehicle_reservations:
            return
        
        time_steps_to_release = [
            t for t in self.vehicle_reservations[vehicle_id].keys()
            if t >= from_time
        ]
        
        for time_step in time_steps_to_release:
            position = self.vehicle_reservations[vehicle_id][time_step]
            if time_step in self.reservations:
                if self.reservations[time_step].get(position) == vehicle_id:
                    del self.reservations[time_step][position]
            del self.vehicle_reservations[vehicle_id][time_step]
    
    def is_reserved(
        self,
        position: Tuple[int, int],
        time_step: int,
        exclude_vehicle: Optional[str] = None
    ) -> bool:
        """
        Check if a position is reserved at a time step.
        
        Args:
            position: Position to check
            time_step: Time step to check
            exclude_vehicle: Optionally exclude a specific vehicle from check
        
        Returns:
            True if reserved by another vehicle
        """
        if time_step not in self.reservations:
            return False
        
        if position not in self.reservations[time_step]:
            return False
        
        reserved_by = self.reservations[time_step][position]
        
        if exclude_vehicle and reserved_by == exclude_vehicle:
            return False
        
        return True
    
    def get_reserved_by(
        self,
        position: Tuple[int, int],
        time_step: int
    ) -> Optional[str]:
        """Get the vehicle ID that reserved a position at a time step."""
        if time_step in self.reservations:
            return self.reservations[time_step].get(position)
        return None
    
    def get_blocked_cells(
        self,
        time_step: int,
        exclude_vehicle: Optional[str] = None
    ) -> Set[Tuple[int, int]]:
        """
        Get all blocked cells at a specific time step.
        
        Args:
            time_step: Time step to check
            exclude_vehicle: Optionally exclude a specific vehicle
        
        Returns:
            Set of blocked positions
        """
        if time_step not in self.reservations:
            return set()
        
        blocked = set()
        for position, vehicle_id in self.reservations[time_step].items():
            if exclude_vehicle is None or vehicle_id != exclude_vehicle:
                blocked.add(position)
        
        return blocked
    
    def cleanup_old_reservations(self, current_time: int, keep_history: int = 10):
        """
        Clean up old reservations to save memory.
        
        Args:
            current_time: Current simulation time
            keep_history: How many past time steps to keep
        """
        cutoff_time = current_time - keep_history
        
        # Remove old time steps from main reservations
        old_times = [t for t in self.reservations.keys() if t < cutoff_time]
        for t in old_times:
            del self.reservations[t]
        
        # Remove old time steps from vehicle reservations
        for vehicle_id in list(self.vehicle_reservations.keys()):
            old_times = [
                t for t in self.vehicle_reservations[vehicle_id].keys()
                if t < cutoff_time
            ]
            for t in old_times:
                del self.vehicle_reservations[vehicle_id][t]
            
            # Remove vehicle entry if empty
            if not self.vehicle_reservations[vehicle_id]:
                del self.vehicle_reservations[vehicle_id]
