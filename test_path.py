#!/usr/bin/env python3
"""Quick test để xem path visualization"""

import sys
sys.path.insert(0, '.')

from sim.model import ChargingSimulationModel
from sim.scenarios import get_scenario

print("Creating simulation...")

grid, vehicle_positions, _ = get_scenario('simple')

model = ChargingSimulationModel(
    grid=grid,
    initial_vehicle_positions=vehicle_positions,
    initial_battery_levels=[25, 28, 26]  # All below 30% to trigger assignment
)

print("\nInitial state:")
print(f"Vehicles: {len(model.vehicles)}")
print(f"Stations: {len(model.grid.charging_stations)}")

# Run simulation for 50 ticks
for i in range(50):
    model.step()
    state = model.get_state()
    
    print(f"\n=== Tick {state['tick']} ===")
    for v in state['vehicles']:
        path_len = len(v.get('current_path', []))
        if path_len > 0:
            print(f"✅ {v['id']}: status={v['status']}, "
                  f"battery={v['battery_level']:.1f}%, "
                  f"target=Station_{v['target_station']}, "
                  f"path={path_len} waypoints")
        else:
            print(f"   {v['id']}: status={v['status']}, "
                  f"battery={v['battery_level']:.1f}%, "
                  f"no path yet")

print("\n✅ Path visualization test complete!")
print("If you see vehicles with paths above, visualization should work in browser.")
