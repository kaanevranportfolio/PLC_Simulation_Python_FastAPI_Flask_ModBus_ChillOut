// HVAC Control System Frontend Application
const API_URL = 'http://localhost:8000';
let updateInterval = null;
let systemRunning = false;

// DOM Elements
const elements = {
    connectionStatus: document.getElementById('connection-status'),
    systemToggle: document.getElementById('system-toggle'),
    tempSetpoint: document.getElementById('temp-setpoint'),
    tempSetpointValue: document.getElementById('temp-setpoint-value'),
    humiditySetpoint: document.getElementById('humidity-setpoint'),
    humiditySetpointValue: document.getElementById('humidity-setpoint-value'),
    indoorTemp: document.getElementById('indoor-temp'),
    indoorHumidity: document.getElementById('indoor-humidity'),
    outdoorTemp: document.getElementById('outdoor-temp'),
    outdoorHumidity: document.getElementById('outdoor-humidity'),
    fanSpeed: document.getElementById('fan-speed'),
    chillerStatus: document.getElementById('chiller-status'),
    weatherTemp: document.getElementById('weather-temp'),
    weatherHumidity: document.getElementById('weather-humidity'),
    updateWeather: document.getElementById('update-weather'),
    logContainer: document.getElementById('log-container'),
    fanIndicator: document.getElementById('fan-indicator'),
    chillerIndicator: document.getElementById('chiller-indicator')
};

// Initialize application
document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
    startStatusUpdates();
    addLog('System initialized', 'info');
});

// Event Listeners
function setupEventListeners() {
    // System toggle
    elements.systemToggle.addEventListener('click', toggleSystem);
    
    // Temperature setpoint
    elements.tempSetpoint.addEventListener('input', (e) => {
        elements.tempSetpointValue.textContent = `${e.target.value}°C`;
    });
    
    elements.tempSetpoint.addEventListener('change', (e) => {
        updateSetpoint('temperature', parseFloat(e.target.value));
    });
    
    // Humidity setpoint
    elements.humiditySetpoint.addEventListener('input', (e) => {
        elements.humiditySetpointValue.textContent = `${e.target.value}%`;
    });
    
    elements.humiditySetpoint.addEventListener('change', (e) => {
        updateSetpoint('humidity', parseFloat(e.target.value));
    });
    
    // Weather update
    elements.updateWeather.addEventListener('click', updateWeatherConditions);
}

// System Control Functions
async function toggleSystem() {
    try {
        const command = systemRunning ? 'stop' : 'start';
        const response = await fetch(`${API_URL}/api/control`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ command })
        });
        if (response.ok) {
            const data = await response.json();
            systemRunning = !systemRunning;
            updateSystemButton();
            addLog(data.message, 'success');
            // Do NOT reset outside temperature or humidity here
        } else {
            throw new Error('Failed to toggle system');
        }
    } catch (error) {
        addLog(`Error: ${error.message}`, 'error');
    }
}

async function updateSetpoint(type, value) {
    try {
        const command = type === 'temperature' ? 'set_temperature' : 'set_humidity';
        const response = await fetch(`${API_URL}/api/control`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ command, value })
        });
        
        if (response.ok) {
            const data = await response.json();
            addLog(data.message, 'info');
        } else {
            throw new Error(`Failed to update ${type} setpoint`);
        }
    } catch (error) {
        addLog(`Error: ${error.message}`, 'error');
    }
}

async function updateWeatherConditions() {
    try {
        const temperature = parseFloat(elements.weatherTemp.value);
        const humidity = parseFloat(elements.weatherHumidity.value);
        
        const response = await fetch(`${API_URL}/api/weather`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ temperature, humidity })
        });
        
        if (response.ok) {
            addLog(`Weather updated: ${temperature}°C, ${humidity}%`, 'info');
        } else {
            throw new Error('Failed to update weather');
        }
    } catch (error) {
        addLog(`Error: ${error.message}`, 'error');
    }
}

// Status Update Functions
function startStatusUpdates() {
    updateStatus(); // Initial update
    updateInterval = setInterval(updateStatus, 2000); // Update every 2 seconds
}

async function updateStatus() {
    try {
        const response = await fetch(`${API_URL}/api/status`);
        
        if (response.ok) {
            const status = await response.json();
            updateUI(status);
            updateConnectionStatus(true);
        } else {
            throw new Error('Failed to fetch status');
        }
    } catch (error) {
        updateConnectionStatus(false);
        console.error('Status update error:', error);
    }
}

function updateUI(status) {
    console.log('Status received:', status); 
    // Update system state
    systemRunning = status.plc_running;
    updateSystemButton();
    
    // Update sensor readings
    elements.indoorTemp.textContent = `${status.room_temperature.toFixed(1)}°C`;
    elements.indoorHumidity.textContent = `${status.room_humidity.toFixed(0)}%`;
    elements.outdoorTemp.textContent = `${status.outside_temperature.toFixed(1)}°C`;
    elements.outdoorHumidity.textContent = `${status.outside_humidity.toFixed(0)}%`;
    
    // Update actuator status
    elements.fanSpeed.textContent = `${status.fan_speed}%`;
    elements.chillerStatus.textContent = status.chiller_status ? 'ON' : 'OFF';
    
    // Update visual indicators
    updateFanAnimation(status.fan_speed);
    updateChillerIndicator(status.chiller_status);
    
    // Update room color based on temperature
    updateRoomTemperatureColor(status.room_temperature);
}

function updateSystemButton() {
    if (systemRunning) {
        elements.systemToggle.innerHTML = '<i class="fas fa-stop"></i> Stop System';
        elements.systemToggle.classList.add('active');
    } else {
        elements.systemToggle.innerHTML = '<i class="fas fa-play"></i> Start System';
        elements.systemToggle.classList.remove('active');
    }
}

function updateConnectionStatus(connected) {
    if (connected) {
        elements.connectionStatus.innerHTML = '<i class="fas fa-circle"></i> Connected';
        elements.connectionStatus.classList.add('connected');
        elements.connectionStatus.classList.remove('disconnected');
    } else {
        elements.connectionStatus.innerHTML = '<i class="fas fa-circle"></i> Disconnected';
        elements.connectionStatus.classList.add('disconnected');
        elements.connectionStatus.classList.remove('connected');
    }
}

// Visual Updates
function updateFanAnimation(speed) {
    const fanGroup = elements.fanIndicator;

    if (speed > 0) {
        // Calculate the duration
        const duration = 3 - (speed / 100) * 2.5;

        // Set the CSS variable on the fan group element
        fanGroup.style.setProperty('--rotation-duration', duration + 's');
        
        // Add the class to start the animation and turn blades green
        fanGroup.classList.add('is-rotating');

    } else {
        // Remove the class to stop the animation
        fanGroup.classList.remove('is-rotating');
        
        // The CSS will automatically handle changing the blade color back to #666
        // because the condition `#fan-indicator.is-rotating .fan-blade` is no longer met.
    }
}

function updateChillerIndicator(isOn) {
    const rect = elements.chillerIndicator.querySelector('rect');
    if (isOn) {
        rect.style.fill = '#2196F3';
        rect.style.opacity = '0.8';
    } else {
        rect.style.fill = '#2196F3';
        rect.style.opacity = '0.3';
    }
}

function updateRoomTemperatureColor(temperature) {
    const roomRect = document.querySelector('#room-svg rect:nth-child(2)');
    const hue = 200 - ((temperature - 15) / 15) * 60; // Blue to red gradient
    roomRect.style.fill = `hsl(${hue}, 70%, 85%)`;
}

// Logging Functions
function addLog(message, type = 'info') {
    const timestamp = new Date().toLocaleTimeString();
    const logEntry = document.createElement('div');
    logEntry.className = `log-entry log-${type}`;
    logEntry.innerHTML = `
        <span class="log-time">${timestamp}</span>
        <span class="log-message">${message}</span>
    `;
    
    elements.logContainer.insertBefore(logEntry, elements.logContainer.firstChild);
    
    // Keep only last 50 logs
    while (elements.logContainer.children.length > 50) {
        elements.logContainer.removeChild(elements.logContainer.lastChild);
    }
}

// CSS Animation Keyframes (added dynamically)
const style = document.createElement('style');
style.textContent = `
    @keyframes rotate {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
    }
`;
document.head.appendChild(style);