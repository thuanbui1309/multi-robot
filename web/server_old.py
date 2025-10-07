"""FastAPI server with WebSocket support for real-time simulation."""

from typing import Dict, Any, List, Optional
import asyncio
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

from sim.model import ChargingSimulationModel
from sim.scenarios import get_scenario


# Request/Response models
class AddVehicleRequest(BaseModel):
    x: int
    y: int
    battery: float = 50.0


class SimulationConfig(BaseModel):
    scenario: str = "simple"
    speed: float = 2.0


# Global simulation state
simulation_model: Optional[ChargingSimulationModel] = None
websocket_clients: List[WebSocket] = []
simulation_task: Optional[asyncio.Task] = None
simulation_running: bool = False
simulation_paused: bool = False


# Create FastAPI app
app = FastAPI(title="Multi-Robot Charging Simulation")


# HTML frontend
HTML_CONTENT = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Multi-Robot Charging Simulation</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #1e1e1e;
            color: #ffffff;
            padding: 20px;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        
        header {
            text-align: center;
            margin-bottom: 30px;
        }
        
        h1 {
            color: #4fc3f7;
            margin-bottom: 10px;
        }
        
        .main-content {
            display: grid;
            grid-template-columns: 1fr 350px;
            gap: 20px;
        }
        
        .grid-container {
            background: #2d2d2d;
            border-radius: 8px;
            padding: 20px;
        }
        
        #grid {
            display: inline-block;
            font-family: 'Courier New', monospace;
            font-size: 16px;
            line-height: 20px;
            background: #000;
            padding: 15px;
            border-radius: 4px;
            border: 2px solid #4fc3f7;
        }
        
        .grid-cell {
            display: inline-block;
            width: 20px;
            text-align: center;
        }
        
        .cell-empty { color: #555; }
        .cell-obstacle { color: #ff6b6b; font-weight: bold; }
        .cell-station { color: #51cf66; font-weight: bold; }
        .cell-vehicle { color: #ffd43b; font-weight: bold; animation: pulse 1s infinite; }
        .cell-path { color: #00bcd4; font-weight: bold; opacity: 0.7; }
        .cell-trail { color: #9c27b0; font-weight: bold; opacity: 0.5; }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.6; }
        }
        
        /* Agent Logs Panel */
        .agent-logs {
            background: #1e1e1e;
            border-radius: 4px;
            padding: 15px;
            margin-top: 20px;
            max-height: 300px;
            overflow-y: auto;
            font-family: 'Courier New', monospace;
            font-size: 12px;
        }
        
        .log-entry {
            padding: 5px 0;
            border-bottom: 1px solid #333;
        }
        
        .log-entry:last-child {
            border-bottom: none;
        }
        
        .log-timestamp {
            color: #888;
            margin-right: 8px;
        }
        
        .log-orchestrator {
            color: #4fc3f7;
            font-weight: bold;
        }
        
        .log-vehicle {
            color: #ffd43b;
            font-weight: bold;
        }
        
        .log-action {
            color: #51cf66;
        }
        
        .log-warning {
            color: #ff9800;
        }
        
        .log-error {
            color: #ff6b6b;
        }
        
        .sidebar {
            background: #2d2d2d;
            border-radius: 8px;
            padding: 20px;
            max-height: 90vh;
            overflow-y: auto;
        }
        
        .controls {
            margin-bottom: 20px;
        }
        
        .control-group {
            margin-bottom: 15px;
        }
        
        label {
            display: block;
            margin-bottom: 5px;
            color: #aaa;
            font-size: 14px;
        }
        
        input, select, button {
            width: 100%;
            padding: 10px;
            border-radius: 4px;
            border: 1px solid #555;
            background: #1e1e1e;
            color: #fff;
            font-size: 14px;
        }
        
        button {
            cursor: pointer;
            background: #4fc3f7;
            color: #000;
            font-weight: bold;
            transition: background 0.3s;
        }
        
        button:hover {
            background: #29b6f6;
        }
        
        button:disabled {
            background: #555;
            cursor: not-allowed;
        }
        
        .btn-danger {
            background: #ff6b6b;
            color: #fff;
        }
        
        .btn-danger:hover {
            background: #ff5252;
        }
        
        .btn-success {
            background: #51cf66;
        }
        
        .btn-success:hover {
            background: #40c057;
        }
        
        .status {
            background: #1e1e1e;
            padding: 15px;
            border-radius: 4px;
            margin-bottom: 20px;
        }
        
        .status-item {
            display: flex;
            justify-content: space-between;
            margin-bottom: 8px;
            font-size: 14px;
        }
        
        .status-label {
            color: #aaa;
        }
        
        .status-value {
            color: #4fc3f7;
            font-weight: bold;
        }
        
        .vehicles-list, .stations-list {
            margin-top: 20px;
        }
        
        .vehicle-item, .station-item {
            background: #1e1e1e;
            padding: 12px;
            border-radius: 4px;
            margin-bottom: 10px;
            font-size: 13px;
        }
        
        .vehicle-header {
            font-weight: bold;
            color: #ffd43b;
            margin-bottom: 5px;
        }
        
        .station-header {
            font-weight: bold;
            color: #51cf66;
            margin-bottom: 5px;
        }
        
        .battery-bar {
            width: 100%;
            height: 8px;
            background: #333;
            border-radius: 4px;
            overflow: hidden;
            margin-top: 5px;
        }
        
        .battery-fill {
            height: 100%;
            transition: width 0.3s;
        }
        
        .battery-high { background: #51cf66; }
        .battery-medium { background: #ffd43b; }
        .battery-low { background: #ff6b6b; }
        
        h3 {
            color: #4fc3f7;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #555;
        }
        
        .legend {
            background: #1e1e1e;
            padding: 15px;
            border-radius: 4px;
            margin-bottom: 20px;
        }
        
        .legend-item {
            display: flex;
            align-items: center;
            margin-bottom: 8px;
            font-size: 14px;
        }
        
        .legend-symbol {
            font-family: 'Courier New', monospace;
            font-weight: bold;
            margin-right: 10px;
            width: 20px;
            text-align: center;
        }
        
        .connection-status {
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 10px 20px;
            border-radius: 4px;
            font-weight: bold;
        }
        
        .connected {
            background: #51cf66;
            color: #000;
        }
        
        .disconnected {
            background: #ff6b6b;
            color: #fff;
        }
    </style>
</head>
<body>
    <div class="connection-status" id="connectionStatus">Connecting...</div>
    
    <div class="container">
        <header>
            <h1>🤖 Multi-Robot Charging Simulation</h1>
            <p>Autonomous vehicles navigating to charging stations using A* pathfinding</p>
        </header>
        
        <div class="main-content">
            <div class="grid-container">
                <h3>Simulation Grid</h3>
                <pre id="grid">Loading...</pre>
            </div>
            
            <div class="sidebar">
                <div class="controls">
                    <h3>Controls</h3>
                    
                    <div class="control-group">
                        <label>Scenario</label>
                        <select id="scenario">
                            <option value="simple">Simple (10x10)</option>
                            <option value="medium">Medium (20x16)</option>
                            <option value="large">Large (30x20)</option>
                            <option value="stress">Stress Test</option>
                        </select>
                    </div>
                    
                    <div class="control-group">
                        <label>Simulation Speed</label>
                        <input type="range" id="speed" min="0.5" max="5" step="0.5" value="2">
                        <span id="speedValue">2.0</span> steps/sec
                    </div>
                    
                    <button id="startBtn" class="btn-success">▶ Start</button>
                    <button id="pauseBtn" disabled>⏸ Pause</button>
                    <button id="resetBtn" class="btn-danger">↻ Reset</button>
                </div>
                
                <div class="legend">
                    <h3>Legend</h3>
                    <div class="legend-item">
                        <span class="legend-symbol cell-empty">.</span>
                        <span>Empty Space</span>
                    </div>
                    <div class="legend-item">
                        <span class="legend-symbol cell-obstacle">#</span>
                        <span>Obstacle</span>
                    </div>
                    <div class="legend-item">
                        <span class="legend-symbol cell-station">C</span>
                        <span>Charging Station</span>
                    </div>
                    <div class="legend-item">
                        <span class="legend-symbol cell-vehicle">V</span>
                        <span>Vehicle</span>
                    </div>
                    <div class="legend-item">
                        <span class="legend-symbol cell-trail">•</span>
                        <span>Trail (Past)</span>
                    </div>
                    <div class="legend-item">
                        <span class="legend-symbol cell-path">·</span>
                        <span>Path (Future)</span>
                    </div>
                </div>
                
                <div class="status">
                    <h3>Status</h3>
                    <div class="status-item">
                        <span class="status-label">Tick:</span>
                        <span class="status-value" id="tick">0</span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Vehicles:</span>
                        <span class="status-value" id="vehicleCount">0</span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Stations:</span>
                        <span class="status-value" id="stationCount">0</span>
                    </div>
                </div>
                
                <div class="control-group">
                    <h3>Add Vehicle</h3>
                    <label>Position X</label>
                    <input type="number" id="newVehicleX" value="1" min="0">
                    <label>Position Y</label>
                    <input type="number" id="newVehicleY" value="1" min="0">
                    <label>Battery Level</label>
                    <input type="number" id="newVehicleBattery" value="30" min="0" max="100">
                    <button id="addVehicleBtn">➕ Add Vehicle</button>
                </div>
                
                <div class="vehicles-list">
                    <h3>Vehicles</h3>
                    <div id="vehiclesList"></div>
                </div>
                
                <div class="stations-list">
                    <h3>Charging Stations</h3>
                    <div id="stationsList"></div>
                </div>
                
                <div class="agent-logs">
                    <h3 style="margin-top: 0;">Agent Activity Logs</h3>
                    <div id="logsList"></div>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        let ws = null;
        let isPaused = false;
        const maxLogs = 50; // Keep last 50 log entries
        const logs = [];
        
        // UI Elements
        const gridEl = document.getElementById('grid');
        const tickEl = document.getElementById('tick');
        const vehicleCountEl = document.getElementById('vehicleCount');
        const stationCountEl = document.getElementById('stationCount');
        const vehiclesListEl = document.getElementById('vehiclesList');
        const stationsListEl = document.getElementById('stationsList');
        const logsListEl = document.getElementById('logsList');
        const connectionStatusEl = document.getElementById('connectionStatus');
        
        const scenarioSelect = document.getElementById('scenario');
        const speedInput = document.getElementById('speed');
        const speedValueEl = document.getElementById('speedValue');
        const startBtn = document.getElementById('startBtn');
        const pauseBtn = document.getElementById('pauseBtn');
        const resetBtn = document.getElementById('resetBtn');
        const addVehicleBtn = document.getElementById('addVehicleBtn');
        
        // Connect to WebSocket
        function connect() {
            ws = new WebSocket(`ws://${window.location.host}/ws`);
            
            ws.onopen = () => {
                console.log('WebSocket connected');
                connectionStatusEl.textContent = 'Connected';
                connectionStatusEl.className = 'connection-status connected';
            };
            
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                updateUI(data);
            };
            
            ws.onclose = () => {
                console.log('WebSocket disconnected');
                connectionStatusEl.textContent = 'Disconnected';
                connectionStatusEl.className = 'connection-status disconnected';
                setTimeout(connect, 2000);
            };
            
            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
            };
        }
        
        // Send message to server
        function send(message) {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify(message));
            }
        }
        
        // Add log entry
        function addLog(tick, agent, message, type = 'info') {
            const timestamp = `T${tick}`;
            logs.unshift({ timestamp, agent, message, type });
            
            // Keep only last maxLogs entries
            if (logs.length > maxLogs) {
                logs.pop();
            }
            
            updateLogsDisplay();
        }
        
        // Update logs display
        function updateLogsDisplay() {
            logsListEl.innerHTML = logs.map(log => {
                const agentClass = log.agent === 'Orchestrator' ? 'log-orchestrator' : 'log-vehicle';
                const typeClass = log.type === 'action' ? 'log-action' : 
                                 log.type === 'warning' ? 'log-warning' : 
                                 log.type === 'error' ? 'log-error' : '';
                return `
                    <div class="log-entry">
                        <span class="log-timestamp">[${log.timestamp}]</span>
                        <span class="${agentClass}">${log.agent}:</span>
                        <span class="${typeClass}">${log.message}</span>
                    </div>
                `;
            }).join('');
        }
        
        // Update UI with simulation state
        function updateUI(state) {
            // Process logs from state if available
            if (state.logs && state.logs.length > 0) {
                state.logs.forEach(logEntry => {
                    addLog(state.tick, logEntry.agent, logEntry.message, logEntry.type);
                });
            }
            
            // Create a 2D map to track paths
            const gridWithPaths = createGridWithPaths(state);
            
            // Update grid with paths
            gridEl.innerHTML = formatGridWithPaths(gridWithPaths);
            
            // Update status
            tickEl.textContent = state.tick;
            vehicleCountEl.textContent = state.vehicles.length;
            stationCountEl.textContent = state.stations.length;
            
            // Update vehicles list
            vehiclesListEl.innerHTML = state.vehicles.map(v => {
                const batteryClass = v.battery_level > 60 ? 'battery-high' : 
                                    v.battery_level > 30 ? 'battery-medium' : 'battery-low';
                const pathInfo = v.current_path && v.current_path.length > 0 ? 
                    `<div>Path to Station ${v.target_station}: ${v.current_path.length - v.path_index} steps</div>` : '';
                return `
                    <div class="vehicle-item">
                        <div class="vehicle-header">${v.id}</div>
                        <div>Position: (${v.position[0]}, ${v.position[1]})</div>
                        <div>Status: ${v.status}</div>
                        ${v.target_station !== null ? `<div>Target: Station ${v.target_station}</div>` : ''}
                        ${pathInfo}
                        <div>Battery: ${v.battery_level.toFixed(1)}%</div>
                        <div class="battery-bar">
                            <div class="battery-fill ${batteryClass}" style="width: ${v.battery_level}%"></div>
                        </div>
                    </div>
                `;
            }).join('');
            
            // Update stations list
            stationsListEl.innerHTML = state.stations.map(s => `
                <div class="station-item">
                    <div class="station-header">Station ${s.id}</div>
                    <div>Position: (${s.position[0]}, ${s.position[1]})</div>
                    <div>Occupied: ${s.occupied}/${s.capacity}</div>
                    <div>Load: ${(s.load * 100).toFixed(0)}%</div>
                </div>
            `).join('');
        }
        
        // Create grid with paths and trails overlaid
        function createGridWithPaths(state) {
            // Parse grid string into 2D array
            const lines = state.grid_string.split('\\n');
            const grid = lines.map(line => line.split(''));
            
            // Mark all vehicle trails (past positions)
            state.vehicles.forEach(vehicle => {
                if (vehicle.trail && vehicle.trail.length > 0) {
                    vehicle.trail.forEach(([x, y], idx) => {
                        if (y >= 0 && y < grid.length && x >= 0 && x < grid[y].length) {
                            // Don't overwrite current vehicle position, stations, or obstacles
                            if (grid[y][x] === '.' && idx < vehicle.trail.length - 1) {
                                grid[y][x] = '•';  // trail marker (recent past)
                            }
                        }
                    });
                }
            });
            
            // Mark all vehicle paths (future planned path)
            state.vehicles.forEach(vehicle => {
                if (vehicle.current_path && vehicle.current_path.length > 0) {
                    // Mark future path (from current index onwards)
                    for (let i = vehicle.path_index; i < vehicle.current_path.length; i++) {
                        const [x, y] = vehicle.current_path[i];
                        if (y >= 0 && y < grid.length && x >= 0 && x < grid[y].length) {
                            // Don't overwrite vehicles, stations, obstacles, or trails
                            if (grid[y][x] === '.') {
                                grid[y][x] = '·';  // path marker (future)
                            }
                        }
                    }
                }
            });
            
            return grid;
        }
        
        // Format grid with paths
        function formatGridWithPaths(grid) {
            return grid.map(line => 
                line.map(char => {
                    const className = char === '.' ? 'cell-empty' :
                                     char === '#' ? 'cell-obstacle' :
                                     char === 'C' ? 'cell-station' :
                                     char === 'V' ? 'cell-vehicle' :
                                     char === '·' ? 'cell-path' :
                                     char === '•' ? 'cell-trail' : '';
                    return `<span class="grid-cell ${className}">${char}</span>`;
                }).join('')
            ).join('\\n');
        }
        
        // Event listeners
        speedInput.addEventListener('input', (e) => {
            speedValueEl.textContent = e.target.value;
            send({ type: 'set_speed', speed: parseFloat(e.target.value) });
        });
        
        startBtn.addEventListener('click', () => {
            if (isPaused) {
                send({ type: 'resume' });
                isPaused = false;
                pauseBtn.textContent = '⏸ Pause';
            } else {
                send({ 
                    type: 'start',
                    scenario: scenarioSelect.value,
                    speed: parseFloat(speedInput.value)
                });
            }
            startBtn.disabled = true;
            pauseBtn.disabled = false;
        });
        
        pauseBtn.addEventListener('click', () => {
            if (isPaused) {
                send({ type: 'resume' });
                pauseBtn.textContent = '⏸ Pause';
            } else {
                send({ type: 'pause' });
                pauseBtn.textContent = '▶ Resume';
            }
            isPaused = !isPaused;
        });
        
        resetBtn.addEventListener('click', () => {
            send({ 
                type: 'reset',
                scenario: scenarioSelect.value
            });
            startBtn.disabled = false;
            pauseBtn.disabled = true;
            isPaused = false;
            pauseBtn.textContent = '⏸ Pause';
        });
        
        addVehicleBtn.addEventListener('click', () => {
            const x = parseInt(document.getElementById('newVehicleX').value);
            const y = parseInt(document.getElementById('newVehicleY').value);
            const battery = parseFloat(document.getElementById('newVehicleBattery').value);
            
            send({ 
                type: 'add_vehicle',
                x: x,
                y: y,
                battery: battery
            });
        });
        
        // Initialize
        connect();
    </script>
</body>
</html>
"""


@app.get("/")
async def get_home():
    """Serve the main HTML page."""
    return HTMLResponse(content=HTML_CONTENT)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time communication."""
    await websocket.accept()
    websocket_clients.append(websocket)
    
    # Send initial state
    if simulation_model:
        state = simulation_model.get_state()
        await websocket.send_json(state)
    
    try:
        while True:
            data = await websocket.receive_json()
            await handle_message(data, websocket)
    except WebSocketDisconnect:
        websocket_clients.remove(websocket)


async def handle_message(data: Dict[str, Any], websocket: WebSocket):
    """Handle incoming WebSocket message."""
    global simulation_model, simulation_task, simulation_running, simulation_paused
    
    msg_type = data.get('type')
    
    if msg_type == 'start':
        # Create new simulation
        scenario_name = data.get('scenario', 'simple')
        speed = data.get('speed', 2.0)
        
        grid, vehicle_positions, _ = get_scenario(scenario_name)
        simulation_model = ChargingSimulationModel(grid, vehicle_positions)
        
        # Start simulation loop
        simulation_running = True
        simulation_paused = False
        simulation_task = asyncio.create_task(run_simulation(speed))
        
    elif msg_type == 'pause':
        simulation_paused = True
            
    elif msg_type == 'resume':
        simulation_paused = False
            
    elif msg_type == 'reset':
        # Stop current simulation
        simulation_running = False
        if simulation_task:
            simulation_task.cancel()
        
        # Create new simulation
        scenario_name = data.get('scenario', 'simple')
        grid, vehicle_positions, _ = get_scenario(scenario_name)
        simulation_model = ChargingSimulationModel(grid, vehicle_positions)
        
        # Send initial state
        await broadcast_state()
        
    elif msg_type == 'add_vehicle':
        if simulation_model:
            x = data.get('x', 0)
            y = data.get('y', 0)
            battery = data.get('battery', 50.0)
            
            simulation_model.add_vehicle((x, y), battery)
            await broadcast_state()
            
    elif msg_type == 'set_speed':
        # Speed change will be handled by the simulation loop
        pass


async def run_simulation(speed: float = 2.0):
    """Run simulation loop."""
    global simulation_model, simulation_running, simulation_paused
    
    delay = 1.0 / speed
    
    try:
        while simulation_running:
            if not simulation_paused and simulation_model:
                simulation_model.step()
                await broadcast_state()
            
            await asyncio.sleep(delay)
    except asyncio.CancelledError:
        simulation_running = False
        pass


async def broadcast_state():
    """Broadcast current state to all connected clients."""
    if simulation_model and websocket_clients:
        state = simulation_model.get_state()
        
        # Debug: Log vehicle paths
        for v in state['vehicles']:
            if v.get('current_path') and len(v['current_path']) > 0:
                print(f"[DEBUG] {v['id']}: path={len(v['current_path'])} waypoints, "
                      f"status={v['status']}, target={v['target_station']}")
        
        # Send to all connected clients
        disconnected = []
        for client in websocket_clients:
            try:
                await client.send_json(state)
            except:
                disconnected.append(client)
        
        # Remove disconnected clients
        for client in disconnected:
            websocket_clients.remove(client)


def start_server(host: str = "0.0.0.0", port: int = 8000):
    """Start the web server."""
    print(f"Starting server at http://{host}:{port}")
    print(f"Open http://localhost:{port} in your browser")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start_server()
