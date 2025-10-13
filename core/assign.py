from typing import List, Tuple, Dict, Optional
import numpy as np
from scipy.optimize import linear_sum_assignment


class VehicleStationAssigner:
    """
    Assigns vehicles to charging stations optimally using Hungarian algorithm.
    Cost matrix considers distance, battery level, and station load.
    """
    
    def __init__(
        self,
        distance_weight: float = 1.0,
        battery_weight: float = 2.0,
        load_weight: float = 0.5
    ):
        """
        Initialize assigner with weights.
        
        Args:
            distance_weight: Weight for distance in cost function
            battery_weight: Weight for battery urgency in cost function
            load_weight: Weight for station load in cost function
        """
        self.distance_weight = distance_weight
        self.battery_weight = battery_weight
        self.load_weight = load_weight
    
    def assign(
        self,
        vehicles: List[Dict],
        stations: List[Dict]
    ) -> Dict[str, Optional[int]]:
        """
        Assign vehicles to stations optimally.
        
        Args:
            vehicles: List of vehicle dicts with keys: id, position, battery_level
            stations: List of station dicts with keys: id, position, load, capacity
        
        Returns:
            Dictionary mapping vehicle_id to station_id (or None if unassigned)
        """
        if not vehicles or not stations:
            return {}
        
        # Build cost matrix
        cost_matrix = self._build_cost_matrix(vehicles, stations)
        
        # Handle case where we have more vehicles than stations
        n_vehicles = len(vehicles)
        n_stations = len(stations)
        
        if n_vehicles > n_stations:
            # Pad with dummy stations (high cost)
            dummy_cost = np.max(cost_matrix) * 2 if cost_matrix.size > 0 else 1000.0
            padding = np.full((n_vehicles, n_vehicles - n_stations), dummy_cost)
            cost_matrix = np.hstack([cost_matrix, padding])
        
        # Apply Hungarian algorithm
        vehicle_indices, station_indices = linear_sum_assignment(cost_matrix)
        
        # Build assignment dictionary
        assignments = {}
        for v_idx, s_idx in zip(vehicle_indices, station_indices):
            vehicle_id = vehicles[v_idx]['id']
            
            # Check if this is a real station or dummy
            if s_idx < n_stations:
                station_id = stations[s_idx]['id']
                
                # Only assign if station has capacity
                station = stations[s_idx]
                if station['load'] < 1.0:  # Has available capacity
                    assignments[vehicle_id] = station_id
                else:
                    assignments[vehicle_id] = None
            else:
                assignments[vehicle_id] = None  # Dummy station
        
        return assignments
    
    def _build_cost_matrix(
        self,
        vehicles: List[Dict],
        stations: List[Dict]
    ) -> np.ndarray:
        """
        Build cost matrix for assignment problem.
        
        Cost = distance_weight * distance 
               + battery_weight * (100 - battery) / 100
               + load_weight * station_load
        
        Args:
            vehicles: List of vehicle information
            stations: List of station information
        
        Returns:
            Cost matrix of shape (n_vehicles, n_stations)
        """
        n_vehicles = len(vehicles)
        n_stations = len(stations)
        cost_matrix = np.zeros((n_vehicles, n_stations))
        
        for i, vehicle in enumerate(vehicles):
            v_pos = vehicle['position']
            v_battery = vehicle.get('battery_level', 50.0)
            
            for j, station in enumerate(stations):
                s_pos = station['position']
                s_load = station.get('load', 0.0)
                
                # Calculate distance (Manhattan)
                distance = abs(v_pos[0] - s_pos[0]) + abs(v_pos[1] - s_pos[1])
                
                # Calculate battery urgency (lower battery = higher urgency)
                battery_urgency = (100.0 - v_battery) / 100.0
                
                # Calculate total cost
                cost = (
                    self.distance_weight * distance +
                    self.battery_weight * battery_urgency * 10.0 +  # Scale up urgency
                    self.load_weight * s_load * 10.0  # Scale up load penalty
                )
                
                # If station is full, add huge penalty
                if s_load >= 1.0:
                    cost += 1000.0
                
                cost_matrix[i, j] = cost
        
        return cost_matrix
    
    def calculate_distance(
        self,
        pos1: Tuple[int, int],
        pos2: Tuple[int, int]
    ) -> float:
        """Calculate Manhattan distance between two positions."""
        return abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1])
