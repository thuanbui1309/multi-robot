from enum import Enum
from typing import List, Tuple, Set, Optional
import numpy as np

class CellType(Enum):
    """Types of cells in the grid."""
    EMPTY = "."
    OBSTACLE = "#"
    CHARGING_STATION = "C"
    VEHICLE = "V"


class Cell:
    """Represents a single cell in the grid."""
    
    def __init__(self, x: int, y: int, cell_type: CellType = CellType.EMPTY):
        self.x = x
        self.y = y
        self.cell_type = cell_type
        self.occupied_by: Optional[str] = None  # Vehicle ID if occupied
    
    @property
    def position(self) -> Tuple[int, int]:
        """Return position as tuple."""
        return (self.x, self.y)
    
    def is_walkable(self) -> bool:
        """Check if cell can be traversed."""
        return self.cell_type in [CellType.EMPTY, CellType.CHARGING_STATION]
    
    def __repr__(self) -> str:
        return f"Cell({self.x}, {self.y}, {self.cell_type.value})"


class ChargingStation:
    """Represents a charging station."""
    
    def __init__(self, station_id: int, position: Tuple[int, int], capacity: int = 1):
        self.station_id = station_id
        self.position = position
        self.capacity = capacity
        self.occupied_slots: Set[str] = set()  # Vehicle IDs currently charging
        self.queue: List[str] = []  # Waiting vehicles
    
    def is_available(self) -> bool:
        """Check if station has available slots."""
        return len(self.occupied_slots) < self.capacity
    
    def get_load(self) -> float:
        """Return current load percentage."""
        return len(self.occupied_slots) / self.capacity
    
    def occupy(self, vehicle_id: str) -> bool:
        """Try to occupy a slot."""
        if self.is_available():
            self.occupied_slots.add(vehicle_id)
            return True
        return False
    
    def release(self, vehicle_id: str):
        """Release a slot."""
        self.occupied_slots.discard(vehicle_id)
    
    def __repr__(self) -> str:
        return f"Station({self.station_id}, {self.position}, {len(self.occupied_slots)}/{self.capacity})"


class Grid:
    """2D grid environment for the simulation."""
    
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.cells = [[Cell(x, y) for y in range(height)] for x in range(width)]
        self.charging_stations: List[ChargingStation] = []
        self.obstacles: Set[Tuple[int, int]] = set()
        self.exit_position: Optional[Tuple[int, int]] = None  # Exit point for completed vehicles
    
    def get_cell(self, x: int, y: int) -> Optional[Cell]:
        """Get cell at position."""
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.cells[x][y]
        return None
    
    def set_obstacle(self, x: int, y: int):
        """Set cell as obstacle."""
        cell = self.get_cell(x, y)
        if cell:
            cell.cell_type = CellType.OBSTACLE
            self.obstacles.add((x, y))
    
    def add_charging_station(self, x: int, y: int, capacity: int = 1) -> ChargingStation:
        """Add a charging station."""
        cell = self.get_cell(x, y)
        if cell:
            cell.cell_type = CellType.CHARGING_STATION
            station_id = len(self.charging_stations)
            station = ChargingStation(station_id, (x, y), capacity)
            self.charging_stations.append(station)
            return station
        raise ValueError(f"Invalid position: ({x}, {y})")
    
    def set_exit(self, x: int, y: int):
        """Set exit position for vehicles to leave."""
        if self.is_valid_position(x, y):
            self.exit_position = (x, y)
    
    def get_station_at(self, position: Tuple[int, int]) -> Optional[ChargingStation]:
        """Get charging station at position."""
        for station in self.charging_stations:
            if station.position == position:
                return station
        return None
    
    def is_valid_position(self, x: int, y: int) -> bool:
        """Check if position is within grid bounds."""
        return 0 <= x < self.width and 0 <= y < self.height
    
    def is_walkable(self, x: int, y: int) -> bool:
        """Check if position is walkable."""
        cell = self.get_cell(x, y)
        return cell is not None and cell.is_walkable()
    
    def get_neighbors(self, x: int, y: int) -> List[Tuple[int, int]]:
        """Get valid neighboring positions (4-directional)."""
        neighbors = []
        directions = [(0, 1), (1, 0), (0, -1), (-1, 0)]  # N, E, S, W
        
        for dx, dy in directions:
            nx, ny = x + dx, y + dy
            if self.is_valid_position(nx, ny) and self.is_walkable(nx, ny):
                neighbors.append((nx, ny))
        
        return neighbors
    
    def to_string(self, vehicle_positions: Optional[dict] = None) -> str:
        """Convert grid to string representation."""
        lines = []
        for y in range(self.height):
            row = []
            for x in range(self.width):
                # Check if there's a vehicle at this position
                if vehicle_positions and (x, y) in vehicle_positions:
                    row.append('V')
                else:
                    cell = self.cells[x][y]
                    row.append(cell.cell_type.value)
            lines.append(''.join(row))
        return '\n'.join(lines)
    
    def to_array(self) -> np.ndarray:
        """Convert grid to numpy array."""
        arr = np.zeros((self.height, self.width), dtype=int)
        for x in range(self.width):
            for y in range(self.height):
                cell = self.cells[x][y]
                if cell.cell_type == CellType.OBSTACLE:
                    arr[y, x] = 1
                elif cell.cell_type == CellType.CHARGING_STATION:
                    arr[y, x] = 2
        return arr
    
    @classmethod
    def from_string(cls, grid_str: str) -> 'Grid':
        """Create grid from string representation."""
        lines = grid_str.strip().split('\n')
        height = len(lines)
        width = len(lines[0]) if lines else 0
        
        grid = cls(width, height)
        
        for y, line in enumerate(lines):
            for x, char in enumerate(line):
                if char == '#':
                    grid.set_obstacle(x, y)
                elif char == 'C':
                    grid.add_charging_station(x, y)
        
        return grid
