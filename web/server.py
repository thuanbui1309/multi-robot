import asyncio
import uvicorn
from typing import Dict, Optional, Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager

from sim.model import ChargingSimulationModel
from sim.scenarios import get_scenario, list_scenarios

# Global state
simulation_model: Optional[ChargingSimulationModel] = None
simulation_running = False
simulation_paused = False
simulation_speed = 2.0
active_connections: Set[WebSocket] = set()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager."""
    yield
    for ws in list(active_connections):
        await ws.close()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def get():
    """Serve the main HTML page."""
    return HTMLResponse(HTML_TEMPLATE)


@app.get("/api/scenarios")
async def get_scenarios():
    """Get list of available scenarios."""
    return {"scenarios": list_scenarios()}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time communication."""
    await websocket.accept()
    active_connections.add(websocket)
    
    try:
        # Send initial state
        if simulation_model:
            state = simulation_model.get_state()
            await websocket.send_json(state)
        
        # Handle incoming messages
        while True:
            data = await websocket.receive_json()
            await handle_message(data, websocket)
            
    except WebSocketDisconnect:
        active_connections.discard(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        active_connections.discard(websocket)


async def handle_message(data: dict, websocket: WebSocket):
    """Handle incoming WebSocket messages."""
    global simulation_model, simulation_running, simulation_paused, simulation_speed
    
    msg_type = data.get("type")
    
    if msg_type == "start":
        scenario = data.get("scenario", "scenario_1_simple")
        simulation_speed = data.get("speed", 2.0)
        
        # Create new simulation from scenario config
        scenario_config = get_scenario(scenario)
        simulation_model = ChargingSimulationModel(
            grid=scenario_config.grid,
            initial_vehicle_positions=scenario_config.vehicle_positions,
            initial_battery_levels=scenario_config.vehicle_batteries,
            scenario_name=scenario_config.name,
            scenario_description=scenario_config.description,
            step_delay=scenario_config.step_delay
        )
        
        simulation_running = True
        simulation_paused = False
        
        # Start simulation loop
        asyncio.create_task(run_simulation())
        
        # Send initial state
        await broadcast_state()
        
    elif msg_type == "pause":
        simulation_paused = True
        
    elif msg_type == "resume":
        simulation_paused = False
        
    elif msg_type == "reset":
        scenario = data.get("scenario", "scenario_1_simple")
        scenario_config = get_scenario(scenario)
        simulation_model = ChargingSimulationModel(
            grid=scenario_config.grid,
            initial_vehicle_positions=scenario_config.vehicle_positions,
            initial_battery_levels=scenario_config.vehicle_batteries,
            scenario_name=scenario_config.name,
            scenario_description=scenario_config.description,
            step_delay=scenario_config.step_delay
        )
        simulation_running = False
        simulation_paused = False
        await broadcast_state()
        simulation_paused = False
        await broadcast_state()
        
    elif msg_type == "set_speed":
        simulation_speed = data.get("speed", 2.0)
        
    elif msg_type == "add_vehicle":
        if simulation_model:
            x = data.get("x", 1)
            y = data.get("y", 1)
            battery = data.get("battery", 50.0)
            simulation_model.add_vehicle((x, y), battery)
            await broadcast_state()


async def run_simulation():
    """Main simulation loop."""
    global simulation_running, simulation_paused
    
    while simulation_running:
        if not simulation_paused and simulation_model:
            try:
                # Step the simulation
                simulation_model.step()
                
                # Broadcast state IMMEDIATELY after each step
                await broadcast_state()
                
            except Exception as e:
                print(f"Simulation error: {e}")
                import traceback
                traceback.print_exc()
                simulation_running = False
        
        # Use the scenario's step delay for better observation
        if simulation_model and hasattr(simulation_model, 'step_delay'):
            await asyncio.sleep(simulation_model.step_delay)
        else:
            await asyncio.sleep(0.3)  # Default delay


async def broadcast_state():
    """Broadcast current state to all connected clients."""
    if not simulation_model:
        return
    
    state = simulation_model.get_state()
    
    # Send to all connected clients
    disconnected = set()
    for ws in active_connections:
        try:
            await ws.send_json(state)
        except Exception:
            disconnected.add(ws)
    
    # Remove disconnected clients
    active_connections.difference_update(disconnected)


# HTML Template with Canvas Visualization
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Multi-Robot Charging Simulation</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #0a0a0a;
            color: #e0e0e0;
            overflow: hidden;
        }
        
        .container {
            display: flex;
            flex-direction: column;
            height: 100vh;
        }
        
        /* Header */
        header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 15px 30px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.5);
        }
        
        header h1 {
            font-size: 24px;
            margin-bottom: 5px;
        }
        
        header p {
            font-size: 14px;
            opacity: 0.9;
        }
        
        /* Logs Section - Top Priority */
        .logs-section {
            background: #1a1a1a;
            border-bottom: 2px solid #333;
            padding: 10px 20px;
            max-height: 180px;
            overflow-y: auto;
        }
        
        .logs-title {
            font-size: 14px;
            font-weight: bold;
            color: #4fc3f7;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .log-entry {
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 11px;
            padding: 4px 8px;
            margin: 2px 0;
            border-left: 3px solid transparent;
            background: rgba(255,255,255,0.03);
            border-radius: 3px;
        }
        
        .log-orchestrator {
            border-left-color: #4fc3f7;
        }
        
        .log-vehicle {
            border-left-color: #ffd43b;
        }
        
        .log-vehicle-0 {
            border-left-color: #ffd43b;
        }
        
        .log-vehicle-1 {
            border-left-color: #51cf66;
        }
        
        .log-vehicle-2 {
            border-left-color: #ff6b9d;
        }
        
        .log-system {
            border-left-color: #9c27b0;
        }
        
        .log-timestamp {
            color: #666;
            margin-right: 6px;
        }
        
        .log-agent {
            font-weight: bold;
            margin-right: 6px;
        }
        
        .log-orchestrator .log-agent {
            color: #4fc3f7;
        }
        
        .log-vehicle .log-agent {
            color: #ffd43b;
        }
        
        .log-vehicle-0 .log-agent {
            color: #ffd43b;
        }
        
        .log-vehicle-1 .log-agent {
            color: #51cf66;
        }
        
        .log-vehicle-2 .log-agent {
            color: #ff6b9d;
        }
        
        .log-system .log-agent {
            color: #9c27b0;
        }
            color: #ffd43b;
        }
        
        .log-action { color: #51cf66; }
        .log-warning { color: #ff9800; }
        .log-error { color: #ff6b6b; }
        
        /* Main Content - Horizontal Layout */
        .main-content {
            flex: 1;
            display: grid;
            grid-template-columns: 1fr 350px;
            gap: 0;
            overflow: hidden;
        }
        
        /* Canvas Area */
        .canvas-area {
            background: #000;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 20px;
            position: relative;
            overflow: auto;  /* Enable scrolling for large maps */
        }
        
        #simulationCanvas {
            border: 2px solid #4fc3f7;
            box-shadow: 0 0 20px rgba(79, 195, 247, 0.3);
            image-rendering: pixelated;
        }
        
        .canvas-legend {
            position: absolute;
            top: 30px;
            right: 30px;
            background: rgba(0,0,0,0.8);
            padding: 15px;
            border-radius: 8px;
            border: 1px solid #333;
        }
        
        .legend-title {
            font-size: 12px;
            font-weight: bold;
            color: #4fc3f7;
            margin-bottom: 10px;
        }
        
        .legend-item {
            display: flex;
            align-items: center;
            gap: 10px;
            margin: 6px 0;
            font-size: 11px;
        }
        
        .legend-color {
            width: 20px;
            height: 20px;
            border-radius: 3px;
        }
        
        /* Control Panel */
        .control-panel {
            background: #1a1a1a;
            border-left: 2px solid #333;
            padding: 20px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }
        
        .panel-section {
            background: #252525;
            padding: 15px;
            border-radius: 8px;
            border: 1px solid #333;
        }
        
        .section-title {
            font-size: 13px;
            font-weight: bold;
            color: #4fc3f7;
            margin-bottom: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        /* Controls */
        .control-group {
            margin-bottom: 12px;
        }
        
        label {
            display: block;
            font-size: 11px;
            color: #aaa;
            margin-bottom: 5px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        select, input[type="number"] {
            width: 100%;
            padding: 8px;
            background: #1a1a1a;
            border: 1px solid #444;
            border-radius: 4px;
            color: #fff;
            font-size: 12px;
        }
        
        input[type="range"] {
            width: 100%;
        }
        
        .speed-value {
            color: #4fc3f7;
            font-weight: bold;
        }
        
        button {
            width: 100%;
            padding: 10px;
            margin: 5px 0;
            border: none;
            border-radius: 4px;
            font-size: 12px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .btn-start {
            background: linear-gradient(135deg, #51cf66, #40c057);
            color: #fff;
        }
        
        .btn-pause {
            background: linear-gradient(135deg, #ffd43b, #ffa94d);
            color: #000;
        }
        
        .btn-reset {
            background: linear-gradient(135deg, #ff6b6b, #ff5252);
            color: #fff;
        }
        
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }
        
        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
        }
        
        /* Status Grid */
        .status-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }
        
        .status-item {
            background: #1a1a1a;
            padding: 10px;
            border-radius: 4px;
            text-align: center;
        }
        
        .status-label {
            font-size: 10px;
            color: #888;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .status-value {
            font-size: 20px;
            font-weight: bold;
            color: #4fc3f7;
            margin-top: 5px;
        }
        
        /* Vehicles List - Compact */
        .entity-list {
            display: flex;
            flex-direction: column;
            gap: 8px;
            max-height: 250px;
            overflow-y: auto;
        }
        
        .vehicle-card {
            background: #1a1a1a;
            padding: 10px;
            border-radius: 4px;
            border-left: 3px solid #ffd43b;
        }
        
        .station-card {
            background: #1a1a1a;
            padding: 10px;
            border-radius: 4px;
            border-left: 3px solid #51cf66;
        }
        
        .entity-header {
            font-size: 12px;
            font-weight: bold;
            margin-bottom: 6px;
        }
        
        .entity-info {
            font-size: 10px;
            color: #aaa;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 4px;
        }
        
        .battery-bar {
            height: 4px;
            background: #333;
            border-radius: 2px;
            margin-top: 6px;
            overflow: hidden;
        }
        
        .battery-fill {
            height: 100%;
            transition: width 0.3s;
        }
        
        .battery-high { background: #51cf66; }
        .battery-medium { background: #ffd43b; }
        .battery-low { background: #ff6b6b; }
        
        /* Connection Status */
        .connection-status {
            position: fixed;
            top: 10px;
            right: 10px;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 11px;
            font-weight: bold;
            z-index: 1000;
        }
        
        .connected {
            background: #51cf66;
            color: #000;
        }
        
        .disconnected {
            background: #ff6b6b;
            color: #fff;
        }
        
        /* Scrollbar */
        ::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }
        
        ::-webkit-scrollbar-track {
            background: #1a1a1a;
        }
        
        ::-webkit-scrollbar-thumb {
            background: #444;
            border-radius: 4px;
        }
        
        ::-webkit-scrollbar-thumb:hover {
            background: #555;
        }
    </style>
</head>
<body>
    <div class="connection-status" id="connectionStatus">Connecting...</div>
    
    <div class="container">
        <!-- Header -->
        <header>
            <h1>Multi-Robot Charging Simulation</h1>
        </header>
        
        <!-- Agent Logs - Top Priority -->
        <div class="logs-section">
            <div class="logs-title">
                <span>Agent Activity Logs</span>
                <span style="font-size: 10px; color: #666;">(Agent thinking process)</span>
            </div>
            <div id="logsList"></div>
        </div>
        
        <!-- Main Content -->
        <div class="main-content">
            <!-- Canvas Visualization -->
            <div class="canvas-area">
                <canvas id="simulationCanvas"></canvas>
                
                <!-- Legend (dynamically populated) -->
                <div class="canvas-legend" id="canvasLegend">
                    <div class="legend-title">Legend</div>
                </div>
            </div>
            
            <!-- Control Panel -->
            <div class="control-panel">
                <!-- Scenario Description -->
                <div class="panel-section" id="scenarioDescription" style="display: none;">
                    <div class="section-title">Current Scenario</div>
                    <div style="font-size: 11px; color: #ccc; line-height: 1.6; max-height: 200px; overflow-y: auto; white-space: pre-line;" id="scenarioDescText"></div>
                </div>
                
                <!-- Controls -->
                <div class="panel-section">
                    <div class="section-title">Controls</div>
                    
                    <div class="control-group">
                        <label>Scenario</label>
                        <select id="scenario">
                            <option value="scenario_1_simple">Scenario 1: Standard - Simple 1 Agent</option>
                            <option value="scenario_2_multiple">Scenario 2: Multiple Agents - Concurrent</option>
                            <option value="scenario_3_conflict">Scenario 3: Path Conflict - Head-On Avoidance</option>
                            <option value="scenario_4_contention">Scenario 4: Station Contention - Resource Allocation</option>
                            <option value="scenario_5_negotiation">Scenario 5: Assignment Negotiation</option>
                        </select>
                    </div>
                    
                    <div class="control-group">
                        <label>Speed: <span class="speed-value" id="speedValue">2.0</span> steps/sec</label>
                        <input type="range" id="speed" min="0.5" max="5" step="0.5" value="2">
                    </div>
                    
                    <button id="startBtn" class="btn-start">Start</button>
                    <button id="pauseBtn" class="btn-pause" disabled>Pause</button>
                    <button id="resetBtn" class="btn-reset">Reset</button>
                </div>
                
                <!-- Status -->
                <div class="panel-section">
                    <div class="section-title">Status</div>
                    <div class="status-grid">
                        <div class="status-item">
                            <div class="status-label">Tick</div>
                            <div class="status-value" id="tick">0</div>
                        </div>
                        <div class="status-item">
                            <div class="status-label">Vehicles</div>
                            <div class="status-value" id="vehicleCount">0</div>
                        </div>
                    </div>
                </div>
                
                <!-- Vehicles -->
                <div class="panel-section">
                    <div class="section-title">Vehicles</div>
                    <div class="entity-list" id="vehiclesList"></div>
                </div>
                
                <!-- Stations -->
                <div class="panel-section">
                    <div class="section-title">Charging Stations</div>
                    <div class="entity-list" id="stationsList"></div>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        // Global state
        let ws = null;
        let isPaused = false;
        const logs = [];
        const maxLogs = 30;
        
        // Canvas
        const canvas = document.getElementById('simulationCanvas');
        const ctx = canvas.getContext('2d');
        const cellSize = 25;
        
        // UI Elements
        const logsListEl = document.getElementById('logsList');
        const tickEl = document.getElementById('tick');
        const vehicleCountEl = document.getElementById('vehicleCount');
        const vehiclesListEl = document.getElementById('vehiclesList');
        const stationsListEl = document.getElementById('stationsList');
        const connectionStatusEl = document.getElementById('connectionStatus');
        
        const scenarioSelect = document.getElementById('scenario');
        const speedInput = document.getElementById('speed');
        const speedValueEl = document.getElementById('speedValue');
        const startBtn = document.getElementById('startBtn');
        const pauseBtn = document.getElementById('pauseBtn');
        const resetBtn = document.getElementById('resetBtn');
        
        // WebSocket Connection
        function connect() {
            ws = new WebSocket(`ws://${window.location.host}/ws`);
            
            ws.onopen = () => {
                console.log('WebSocket connected');
                connectionStatusEl.textContent = 'Connected';
                connectionStatusEl.className = 'connection-status connected';
            };
            
            ws.onmessage = (event) => {
                const state = JSON.parse(event.data);
                updateVisualization(state);
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
        
        function send(message) {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify(message));
            }
        }
        
        // Visualization
        function updateVisualization(state) {
            // Process logs - show in order (newest at bottom)
            if (state.logs && state.logs.length > 0) {
                state.logs.forEach(log => {
                    addLog(state.tick, log.agent, log.message, log.type);
                });
            }
            
            // Draw canvas
            drawSimulation(state);
            
            // Update legend based on current scenario
            updateLegend(state);
            
            // Update scenario info
            if (state.scenario_name) {
                document.getElementById('scenarioDescription').style.display = 'block';
                document.getElementById('scenarioDescText').textContent = state.scenario_description || '';
            }
            
            // Update UI
            tickEl.textContent = state.tick;
            vehicleCountEl.textContent = state.vehicles.length;
            
            // Update vehicles list
            vehiclesListEl.innerHTML = state.vehicles.map(v => {
                const batteryClass = v.battery_level > 60 ? 'battery-high' : 
                                    v.battery_level > 30 ? 'battery-medium' : 'battery-low';
                return `
                    <div class="vehicle-card">
                        <div class="entity-header" style="color: #ffd43b;">${v.id}</div>
                        <div class="entity-info">
                            <span>Pos: (${v.position[0]},${v.position[1]})</span>
                            <span>Status: ${v.status}</span>
                            <span>Battery: ${v.battery_level.toFixed(1)}%</span>
                            ${v.target_station !== null ? `<span>→ Station ${v.target_station}</span>` : '<span>-</span>'}
                        </div>
                        <div class="battery-bar">
                            <div class="battery-fill ${batteryClass}" style="width: ${v.battery_level}%"></div>
                        </div>
                    </div>
                `;
            }).join('');
            
            // Update stations
            stationsListEl.innerHTML = state.stations.map(s => `
                <div class="station-card">
                    <div class="entity-header" style="color: #51cf66;">Station ${s.id}</div>
                    <div class="entity-info">
                        <span>Pos: (${s.position[0]},${s.position[1]})</span>
                        <span>Load: ${(s.load * 100).toFixed(0)}%</span>
                        <span>Occupied: ${s.occupied}/${s.capacity}</span>
                    </div>
                </div>
            `).join('');
        }
        
        function drawSimulation(state) {
            // Parse grid
            const lines = state.grid_string.split('\\n');
            const gridHeight = lines.length;
            const gridWidth = lines[0] ? lines[0].length : 0;
            
            // Resize canvas
            canvas.width = gridWidth * cellSize;
            canvas.height = gridHeight * cellSize;
            
            // Clear
            ctx.fillStyle = '#000';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            
            // Draw grid cells
            for (let y = 0; y < gridHeight; y++) {
                for (let x = 0; x < gridWidth; x++) {
                    const char = lines[y][x];
                    const px = x * cellSize;
                    const py = y * cellSize;
                    
                    // Cell background
                    if (char === '#') {
                        ctx.fillStyle = '#ff6b6b';
                        ctx.fillRect(px, py, cellSize, cellSize);
                    } else if (char === 'C') {
                        ctx.fillStyle = '#51cf66';
                        ctx.fillRect(px, py, cellSize, cellSize);
                    } else {
                        ctx.fillStyle = '#1a1a1a';
                        ctx.fillRect(px, py, cellSize, cellSize);
                    }
                    
                    // Grid lines
                    ctx.strokeStyle = '#333';
                    ctx.lineWidth = 1;
                    ctx.strokeRect(px, py, cellSize, cellSize);
                }
            }
            
            // Draw exit if exists
            if (state.grid_exit) {
                const [ex, ey] = state.grid_exit;
                ctx.fillStyle = 'rgba(33, 150, 243, 0.3)';
                ctx.fillRect(ex * cellSize, ey * cellSize, cellSize, cellSize);
                ctx.strokeStyle = '#2196F3';
                ctx.lineWidth = 2;
                ctx.strokeRect(ex * cellSize, ey * cellSize, cellSize, cellSize);
            }
            
            // Draw trails and paths for each vehicle
            state.vehicles.forEach((v, idx) => {
                // Vehicle-specific colors
                const vehicleColors = [
                    { main: '#ffd43b', trail: 'rgba(255, 212, 59, 0.5)', path: 'rgba(255, 212, 59, 0.7)' },  // Yellow
                    { main: '#51cf66', trail: 'rgba(81, 207, 102, 0.5)', path: 'rgba(81, 207, 102, 0.7)' },  // Green
                    { main: '#ff6b9d', trail: 'rgba(255, 107, 157, 0.5)', path: 'rgba(255, 107, 157, 0.7)' }  // Pink
                ];
                const colors = vehicleColors[idx % vehicleColors.length];
                
                // Draw trail (past positions)
                if (v.trail && v.trail.length > 0) {
                    ctx.fillStyle = colors.trail;
                    v.trail.forEach(([x, y]) => {
                        ctx.fillRect(x * cellSize + 5, y * cellSize + 5, cellSize - 10, cellSize - 10);
                    });
                }
                
                // Draw future path
                if (v.current_path && v.current_path.length > 0) {
                    ctx.strokeStyle = colors.path;
                    ctx.lineWidth = 3;
                    ctx.beginPath();
                    
                    // Start from current position
                    const [startX, startY] = v.position;
                    ctx.moveTo(startX * cellSize + cellSize / 2, startY * cellSize + cellSize / 2);
                    
                    // Draw path
                    for (let i = v.path_index; i < v.current_path.length; i++) {
                        const [px, py] = v.current_path[i];
                        ctx.lineTo(px * cellSize + cellSize / 2, py * cellSize + cellSize / 2);
                    }
                    
                    ctx.stroke();
                    
                    // Draw waypoints
                    ctx.fillStyle = colors.path.replace('0.7', '0.5');
                    for (let i = v.path_index; i < v.current_path.length; i++) {
                        const [px, py] = v.current_path[i];
                        ctx.fillRect(px * cellSize + 8, py * cellSize + 8, cellSize - 16, cellSize - 16);
                    }
                }
                
                // Draw vehicle
                const [vx, vy] = v.position;
                ctx.fillStyle = colors.main;
                ctx.fillRect(vx * cellSize + 3, vy * cellSize + 3, cellSize - 6, cellSize - 6);
                
                // Vehicle label
                ctx.fillStyle = '#000';
                ctx.font = 'bold 10px Arial';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(v.id.replace('vehicle_', ''), vx * cellSize + cellSize / 2, vy * cellSize + cellSize / 2);
            });
        }
        
        function updateLegend(state) {
            const legendEl = document.getElementById('canvasLegend');
            
            // Define vehicle colors
            const vehicleColors = [
                { color: '#ffd43b', name: 'Yellow' },
                { color: '#51cf66', name: 'Green' },
                { color: '#ff6b9d', name: 'Pink' },
                { color: '#4fc3f7', name: 'Cyan' },
                { color: '#9c27b0', name: 'Purple' },
                { color: '#ff9800', name: 'Orange' }
            ];
            
            // Build legend HTML
            let legendHtml = '<div class="legend-title">Legend</div>';
            
            // Add obstacles
            legendHtml += `
                <div class="legend-item">
                    <div class="legend-color" style="background: #ff6b6b;"></div>
                    <span>Obstacle</span>
                </div>
            `;
            
            // Add charging stations
            legendHtml += `
                <div class="legend-item">
                    <div class="legend-color" style="background: #51cf66;"></div>
                    <span>Charging Station</span>
                </div>
            `;
            
            // Add vehicles dynamically based on actual number
            state.vehicles.forEach((v, idx) => {
                const colorInfo = vehicleColors[idx % vehicleColors.length];
                const vehicleNum = v.id.split('_')[1] || idx;
                legendHtml += `
                    <div class="legend-item">
                        <div class="legend-color" style="background: ${colorInfo.color};"></div>
                        <span>Vehicle ${vehicleNum} (${colorInfo.name})</span>
                    </div>
                `;
            });
            
            // Add exit zone if it exists
            if (state.grid_exit) {
                legendHtml += `
                    <div class="legend-item">
                        <div class="legend-color" style="background: #2196F3; opacity: 0.3;"></div>
                        <span>Exit Zone</span>
                    </div>
                `;
            }
            
            legendEl.innerHTML = legendHtml;
        }
        
        function addLog(tick, agent, message, type = 'info') {
            let agentClass = 'log-vehicle';
            if (agent === 'Orchestrator') {
                agentClass = 'log-orchestrator';
            } else if (agent === 'System') {
                agentClass = 'log-system';
            } else if (agent.startsWith('vehicle_')) {
                // Extract vehicle number and add specific class
                const vehicleNum = agent.split('_')[1];
                agentClass = `log-vehicle log-vehicle-${vehicleNum}`;
            }
            
            const typeClass = type === 'action' ? 'log-action' : 
                             type === 'warning' ? 'log-warning' : 
                             type === 'error' ? 'log-error' : '';
            
            const logHtml = `
                <div class="log-entry ${agentClass}" style="animation: slideIn 0.3s ease-out;">
                    <span class="log-agent">${agent}:</span>
                    <span class="${typeClass}">${message}</span>
                </div>
            `;
            
            // Add to end (newest at bottom)
            logs.push(logHtml);
            if (logs.length > maxLogs) logs.shift();  // Remove oldest from start
            
            logsListEl.innerHTML = logs.join('');
            
            // Auto-scroll to bottom (newest logs)
            logsListEl.parentElement.scrollTop = logsListEl.parentElement.scrollHeight;
        }
        
        // Add CSS animation for new logs
        const style = document.createElement('style');
        style.textContent = `
            @keyframes slideIn {
                from {
                    opacity: 0;
                    transform: translateX(-10px);
                }
                to {
                    opacity: 1;
                    transform: translateX(0);
                }
            }
        `;
        document.head.appendChild(style);
        
        // Event Listeners
        speedInput.addEventListener('input', (e) => {
            speedValueEl.textContent = e.target.value;
            send({ type: 'set_speed', speed: parseFloat(e.target.value) });
        });
        
        startBtn.addEventListener('click', () => {
            if (isPaused) {
                send({ type: 'resume' });
                isPaused = false;
                pauseBtn.textContent = 'Pause';
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
                pauseBtn.textContent = 'Pause';
            } else {
                send({ type: 'pause' });
                pauseBtn.textContent = 'Resume';
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
            pauseBtn.textContent = 'Pause';
            logs.length = 0;
            logsListEl.innerHTML = '';
        });
        
        // Initialize
        connect();
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    print("MULTI-ROBOT CHARGING SIMULATION - VISUAL PATH PLANNING\n")
    print("\nStarting web server...")
    print("Server will be available at: http://localhost:8000")
    print("Press Ctrl+C to stop\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")