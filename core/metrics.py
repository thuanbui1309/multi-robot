"""Metrics collection for simulation analysis."""

from typing import Dict, List, Any
from dataclasses import dataclass, field
from collections import defaultdict
import time


@dataclass
class VehicleMetrics:
    """Metrics for a single vehicle."""
    vehicle_id: str
    total_distance: float = 0.0
    total_charging_time: int = 0
    total_waiting_time: int = 0
    total_moving_time: int = 0
    num_replans: int = 0
    num_assignments: int = 0
    battery_history: List[float] = field(default_factory=list)
    position_history: List[tuple] = field(default_factory=list)
    
    def add_step(self, battery: float, position: tuple):
        """Record a step."""
        self.battery_history.append(battery)
        self.position_history.append(position)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'vehicle_id': self.vehicle_id,
            'total_distance': self.total_distance,
            'total_charging_time': self.total_charging_time,
            'total_waiting_time': self.total_waiting_time,
            'total_moving_time': self.total_moving_time,
            'num_replans': self.num_replans,
            'num_assignments': self.num_assignments,
            'avg_battery': sum(self.battery_history) / len(self.battery_history) if self.battery_history else 0,
            'min_battery': min(self.battery_history) if self.battery_history else 0,
        }


class SimulationMetrics:
    """Collect and analyze simulation metrics."""
    
    def __init__(self):
        """Initialize metrics collector."""
        self.start_time = time.time()
        self.vehicle_metrics: Dict[str, VehicleMetrics] = {}
        self.station_usage: Dict[int, List[int]] = defaultdict(list)  # station_id -> [usage_count per tick]
        self.tick_count = 0
        self.total_assignments = 0
        self.total_conflicts = 0
        self.total_replans = 0
    
    def get_or_create_vehicle_metrics(self, vehicle_id: str) -> VehicleMetrics:
        """Get or create metrics for a vehicle."""
        if vehicle_id not in self.vehicle_metrics:
            self.vehicle_metrics[vehicle_id] = VehicleMetrics(vehicle_id)
        return self.vehicle_metrics[vehicle_id]
    
    def record_vehicle_step(
        self,
        vehicle_id: str,
        battery: float,
        position: tuple,
        distance_moved: float = 0.0
    ):
        """Record a vehicle step."""
        metrics = self.get_or_create_vehicle_metrics(vehicle_id)
        metrics.add_step(battery, position)
        metrics.total_distance += distance_moved
    
    def record_charging(self, vehicle_id: str):
        """Record charging time."""
        metrics = self.get_or_create_vehicle_metrics(vehicle_id)
        metrics.total_charging_time += 1
    
    def record_moving(self, vehicle_id: str):
        """Record moving time."""
        metrics = self.get_or_create_vehicle_metrics(vehicle_id)
        metrics.total_moving_time += 1
    
    def record_waiting(self, vehicle_id: str):
        """Record waiting time."""
        metrics = self.get_or_create_vehicle_metrics(vehicle_id)
        metrics.total_waiting_time += 1
    
    def record_replan(self, vehicle_id: str):
        """Record a replan event."""
        metrics = self.get_or_create_vehicle_metrics(vehicle_id)
        metrics.num_replans += 1
        self.total_replans += 1
    
    def record_assignment(self, vehicle_id: str):
        """Record an assignment event."""
        metrics = self.get_or_create_vehicle_metrics(vehicle_id)
        metrics.num_assignments += 1
        self.total_assignments += 1
    
    def record_conflict(self):
        """Record a conflict event."""
        self.total_conflicts += 1
    
    def record_station_usage(self, station_id: int, usage_count: int):
        """Record station usage for current tick."""
        self.station_usage[station_id].append(usage_count)
    
    def increment_tick(self):
        """Increment tick counter."""
        self.tick_count += 1
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics."""
        elapsed_time = time.time() - self.start_time
        
        # Calculate vehicle statistics
        vehicle_stats = [m.to_dict() for m in self.vehicle_metrics.values()]
        
        # Calculate station statistics
        station_stats = {}
        for station_id, usage_list in self.station_usage.items():
            station_stats[station_id] = {
                'avg_usage': sum(usage_list) / len(usage_list) if usage_list else 0,
                'max_usage': max(usage_list) if usage_list else 0,
                'total_charges': sum(usage_list),
            }
        
        return {
            'simulation_time': elapsed_time,
            'total_ticks': self.tick_count,
            'total_vehicles': len(self.vehicle_metrics),
            'total_assignments': self.total_assignments,
            'total_conflicts': self.total_conflicts,
            'total_replans': self.total_replans,
            'vehicles': vehicle_stats,
            'stations': station_stats,
        }
    
    def print_summary(self):
        """Print summary to console."""
        summary = self.get_summary()
        
        print("\n" + "="*60)
        print("SIMULATION METRICS SUMMARY")
        print("="*60)
        print(f"Simulation Time: {summary['simulation_time']:.2f}s")
        print(f"Total Ticks: {summary['total_ticks']}")
        print(f"Total Vehicles: {summary['total_vehicles']}")
        print(f"Total Assignments: {summary['total_assignments']}")
        print(f"Total Conflicts: {summary['total_conflicts']}")
        print(f"Total Replans: {summary['total_replans']}")
        
        print("\n" + "-"*60)
        print("VEHICLE METRICS")
        print("-"*60)
        for v_stat in summary['vehicles']:
            print(f"\nVehicle {v_stat['vehicle_id']}:")
            print(f"  Total Distance: {v_stat['total_distance']:.1f}")
            print(f"  Avg Battery: {v_stat['avg_battery']:.1f}%")
            print(f"  Min Battery: {v_stat['min_battery']:.1f}%")
            print(f"  Charging Time: {v_stat['total_charging_time']} ticks")
            print(f"  Moving Time: {v_stat['total_moving_time']} ticks")
            print(f"  Replans: {v_stat['num_replans']}")
        
        print("\n" + "-"*60)
        print("STATION METRICS")
        print("-"*60)
        for station_id, s_stat in summary['stations'].items():
            print(f"\nStation {station_id}:")
            print(f"  Avg Usage: {s_stat['avg_usage']:.2f}")
            print(f"  Max Usage: {s_stat['max_usage']}")
            print(f"  Total Charges: {s_stat['total_charges']}")
        
        print("\n" + "="*60 + "\n")
