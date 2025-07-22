import numpy as np
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

class ThermalModel:
    """Thermal model for room simulation with HVAC control"""
    
    def __init__(self):
        # Room properties
        self.room_area = 10.0  # m²
        self.room_height = 2.0  # m
        self.room_volume = self.room_area * self.room_height  # m³
        self.wall_thickness = 0.1  # m
        
        # Thermal properties
        self.air_density = 1.225  # kg/m³
        self.air_specific_heat = 1005  # J/(kg·K)
        self.concrete_conductivity = 1.7  # W/(m·K)
        self.wall_area = 4 * np.sqrt(self.room_area) * self.room_height  # m²
        
        # Initial conditions
        self.room_temperature = 20.0  # °C
        self.room_humidity = 50.0  # %
        self.outside_temperature = 25.0  # °C
        self.outside_humidity = 60.0  # %
        
        # HVAC properties
        self.fan_speed = 0  # 0-100%
        self.chiller_on = False
        self.chiller_capacity = 20000  # W ( cooling capacity)
        self.max_air_flow = 0.1  # m³/s at 100% fan speed
        
        # Humidity model parameters
        self.humidity_generation_rate = 0.001  # %/s (from occupants, etc.)
        self.dehumidification_rate = 0.02  # %/s when chiller is on
        
        logger.info("Thermal model initialized")
    
    def set_outside_conditions(self, temperature: float, humidity: float):
        """Set outside weather conditions"""
        self.outside_temperature = temperature
        self.outside_humidity = humidity
    
    def set_fan_speed(self, speed: int):
        """Set fan speed (0-100%)"""
        self.fan_speed = max(0, min(100, speed))
    
    def set_chiller_state(self, on: bool):
        """Set chiller on/off state"""
        self.chiller_on = on
    
    def calculate_heat_transfer(self, dt: float) -> float:
        """Calculate heat transfer through walls"""
        # Simplified steady-state heat transfer through walls
        thermal_resistance = self.wall_thickness / (self.concrete_conductivity * self.wall_area)
        heat_transfer = (self.outside_temperature - self.room_temperature) / thermal_resistance
        return heat_transfer * dt
    
    def calculate_ventilation_effect(self, dt: float) -> Tuple[float, float]:
        """Calculate the effect of ventilation on temperature and humidity"""
        if self.fan_speed == 0:
            return 0.0, 0.0
        
        # Air flow rate based on fan speed
        air_flow_rate = self.max_air_flow * (self.fan_speed / 100.0)
        
        # Mass flow rate
        mass_flow_rate = air_flow_rate * self.air_density
        
        # Temperature change due to ventilation
        room_air_mass = self.room_volume * self.air_density
        temp_change_rate = (mass_flow_rate / room_air_mass) * (self.outside_temperature - self.room_temperature)
        temp_change = temp_change_rate * dt
        
        # Humidity change due to ventilation
        humidity_change_rate = (mass_flow_rate / room_air_mass) * (self.outside_humidity - self.room_humidity)
        humidity_change = humidity_change_rate * dt * 0.5  # Damping factor for humidity
        
        return temp_change, humidity_change
    
    def calculate_chiller_effect(self, dt: float) -> Tuple[float, float]:
        """Calculate the cooling and dehumidification effect of the chiller"""
        if not self.chiller_on:
            return 0.0, 0.0
        
        # Cooling effect
        room_thermal_mass = self.room_volume * self.air_density * self.air_specific_heat
        temp_change = -(self.chiller_capacity * dt) / room_thermal_mass
        
        # Dehumidification effect
        humidity_change = -self.dehumidification_rate * dt
        
        return temp_change, humidity_change
    
    def calculate_internal_gains(self, dt: float) -> Tuple[float, float]:
        """Calculate internal heat and humidity gains"""
        # Small heat gain from equipment, lighting, etc.
        heat_gain = 100  # W
        room_thermal_mass = self.room_volume * self.air_density * self.air_specific_heat
        temp_change = (heat_gain * dt) / room_thermal_mass
        
        # Humidity generation
        humidity_change = self.humidity_generation_rate * dt
        
        return temp_change, humidity_change
    
    def step(self, dt: float):
        """Step the simulation forward by dt seconds"""
        # Calculate all effects
        wall_heat = self.calculate_heat_transfer(dt)
        vent_temp, vent_humidity = self.calculate_ventilation_effect(dt)
        chiller_temp, chiller_humidity = self.calculate_chiller_effect(dt)
        internal_temp, internal_humidity = self.calculate_internal_gains(dt)
        
        # Convert wall heat transfer to temperature change
        room_thermal_mass = self.room_volume * self.air_density * self.air_specific_heat
        wall_temp_change = wall_heat / room_thermal_mass
        
        # Update room temperature
        total_temp_change = wall_temp_change + vent_temp + chiller_temp + internal_temp
        self.room_temperature += total_temp_change
        
        # Update room humidity
        total_humidity_change = vent_humidity + chiller_humidity + internal_humidity
        self.room_humidity += total_humidity_change
        
        # Clamp humidity to realistic values
        self.room_humidity = max(20.0, min(90.0, self.room_humidity))
        
        # Log significant changes
        if abs(total_temp_change) > 0.1 or abs(total_humidity_change) > 1.0:
            logger.debug(f"Step: ΔT={total_temp_change:.3f}°C, ΔH={total_humidity_change:.1f}%")
    
    def get_room_conditions(self) -> Tuple[float, float]:
        """Get current room temperature and humidity"""
        return self.room_temperature, self.room_humidity
    
    def get_energy_consumption(self) -> float:
        """Calculate current energy consumption in Watts"""
        energy = 0.0
        
        # Fan energy (simplified model)
        if self.fan_speed > 0:
            energy += 50 * (self.fan_speed / 100.0)  # 50W at full speed
        
        # Chiller energy
        if self.chiller_on:
            energy += self.chiller_capacity / 3  # Assuming COP of 3
        
        return energy