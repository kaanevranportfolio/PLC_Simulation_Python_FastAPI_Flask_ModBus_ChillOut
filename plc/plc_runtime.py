import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
import time

logger = logging.getLogger(__name__)

@dataclass
class PLCMemory:
    """PLC memory storage for variables"""
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    internal: Dict[str, Any] = field(default_factory=dict)
    
    def get_value(self, name: str) -> Any:
        """Get variable value from appropriate memory area"""
        if name in self.inputs:
            return self.inputs[name]
        elif name in self.outputs:
            return self.outputs[name]
        elif name in self.internal:
            return self.internal[name]
        else:
            logger.warning(f"Variable {name} not found in memory")
            return None
    
    def set_value(self, name: str, value: Any, var_type: str = 'internal'):
        """Set variable value in appropriate memory area"""
        if var_type == 'input':
            self.inputs[name] = value
        elif var_type == 'output':
            self.outputs[name] = value
        else:
            self.internal[name] = value

class PLCRuntime:
    """Runtime engine for executing parsed ST programs"""
    
    def __init__(self, program=None):
        self.program = program
        self.memory = PLCMemory()
        self.cycle_count = 0
        self.last_cycle_time = 0
        self.system_enabled = False
        
        # Initialize memory from program variables
        if program:
            self._initialize_memory()
        else:
            # Default HVAC variables if no program loaded
            self._initialize_default_memory()
   
    def _initialize_memory(self):
        """Initialize memory from parsed program variables"""
        if not self.program:
            logger.error("No program object provided")
            return
        
        logger.debug(f"Program object: {self.program}")
        logger.debug(f"Program variables: {self.program.variables}")
        
        for var_name, var in self.program.variables.items():
            logger.debug(f"Processing variable: {var_name} - {var}")
            if var.is_input:
                self.memory.inputs[var_name] = self._get_default_value(var.type, var.initial_value)
            elif var.is_output:
                self.memory.outputs[var_name] = self._get_default_value(var.type, var.initial_value)
            else:
                self.memory.internal[var_name] = self._get_default_value(var.type, var.initial_value)
        
        logger.info(f"Initialized memory with {len(self.memory.inputs)} inputs, "
                f"{len(self.memory.outputs)} outputs, {len(self.memory.internal)} internal vars")
        
    def _initialize_default_memory(self):
        """Initialize default HVAC control memory"""
        # Inputs
        self.memory.inputs = {
            'SystemEnable': False,
            'RoomTemperature': 20.0,
            'RoomHumidity': 50.0,
            'SetpointTemp': 22.0,
            'SetpointHumidity': 45.0,
            'TempDeadband': 1.0,
            'HumidityDeadband': 5.0
        }
        
        # Outputs
        self.memory.outputs = {
            'FanSpeed': 0,  # 0-100%
            'ChillerOn': False,
            'SystemStatus': 0,  # 0=Off, 1=Cooling, 2=Idle
            'AlarmActive': False
        }
        
        # Internal variables
        self.memory.internal = {
            'TempError': 0.0,
            'HumidityError': 0.0,
            'CoolingRequired': False,
            'DehumidRequired': False
        }
        
        logger.info("Initialized default HVAC memory")
    
    def _get_default_value(self, type_name: str, initial_value: Any = None):
        """Get default value for a variable type"""
        if initial_value is not None:
            # Extract actual value if it's a parsed expression dictionary
            if isinstance(initial_value, dict) and 'type' in initial_value:
                if initial_value['type'] == 'literal':
                    return initial_value['value']
            else:
                return initial_value
        
        defaults = {
            'BOOL': False,
            'INT': 0,
            'REAL': 0.0,
            'TIME': 0
        }
        return defaults.get(type_name, None)
    
    def execute_cycle(self):
        """Execute one PLC scan cycle"""
        start_time = time.time()
        self.cycle_count += 1
        
        try:
            # Check if system is enabled
            self.system_enabled = self.memory.inputs.get('SystemEnable', False)
            
            if self.program and self.program.statements:
                # Execute parsed program
                for statement in self.program.statements:
                    self._execute_statement(statement)
            else:
                # Execute default HVAC logic
                self._execute_default_logic()
            
            self.last_cycle_time = (time.time() - start_time) * 1000  # ms
            
        except Exception as e:
            logger.error(f"Error in PLC cycle execution: {e}")
            self.memory.outputs['AlarmActive'] = True
    
    def _execute_statement(self, statement: Dict[str, Any]):
        """Execute a single statement"""
        if statement['type'] == 'assignment':
            target = statement['target']
            value = self._evaluate_expression(statement['value'])
            
            # Determine variable type and set value
            if target in self.memory.outputs:
                self.memory.set_value(target, value, 'output')
            elif target in self.memory.inputs:
                logger.warning(f"Cannot assign to input variable: {target}")
            else:
                self.memory.set_value(target, value, 'internal')
        
        elif statement['type'] == 'if':
            self._execute_if_statement(statement)
        
        elif statement['type'] == 'function_call':
            self._execute_function_call(statement)
    
    def _evaluate_expression(self, expr: Dict[str, Any]) -> Any:
        """Evaluate an expression and return its value"""
        if expr['type'] == 'literal':
            return expr['value']
        
        elif expr['type'] == 'variable':
            return self.memory.get_value(expr['name'])
        
        elif expr['type'] == 'binary_op':
            left = self._evaluate_expression(expr['left'])
            right = self._evaluate_expression(expr['right'])
            
            if expr['op'] == '+':
                return left + right
            elif expr['op'] == '-':
                return left - right
            elif expr['op'] == '*':
                return left * right
            elif expr['op'] == '/':
                return left / right if right != 0 else 0
        
        elif expr['type'] == 'comparison':
            left = self._evaluate_expression(expr['left'])
            right = self._evaluate_expression(expr['right'])
            
            if expr['op'] == '>':
                return left > right
            elif expr['op'] == '<':
                return left < right
            elif expr['op'] == '>=':
                return left >= right
            elif expr['op'] == '<=':
                return left <= right
            elif expr['op'] == '=':
                return left == right
            elif expr['op'] == '<>':
                return left != right
        
        elif expr['type'] == 'logical_op':
            left = self._evaluate_expression(expr['left'])
            right = self._evaluate_expression(expr['right'])
            
            if expr['op'] == 'AND':
                return left and right
            elif expr['op'] == 'OR':
                return left or right
        
        elif expr['type'] == 'unary_op':
            operand = self._evaluate_expression(expr['expr'])
            
            if expr['op'] == 'NOT':
                return not operand
            elif expr['op'] == '-':
                return -operand
        
        return None
    
    def _execute_if_statement(self, statement: Dict[str, Any]):
        """Execute IF statement"""
        condition = self._evaluate_expression(statement['condition'])
        
        if condition:
            # Execute THEN block
            for stmt in statement['then_block']:
                self._execute_statement(stmt)
        else:
            # Check ELSIF clauses
            for elsif in statement.get('elsif_clauses', []):
                elsif_condition = self._evaluate_expression(elsif['condition'])
                if elsif_condition:
                    for stmt in elsif['then_block']:
                        self._execute_statement(stmt)
                    return
            
            # Execute ELSE block if no conditions matched
            if statement.get('else_block'):
                for stmt in statement['else_block']:
                    self._execute_statement(stmt)
    
    def _execute_function_call(self, statement: Dict[str, Any]):
        """Execute function call"""
        # Implementation for built-in functions
        # For now, just log it
        logger.debug(f"Function call: {statement['name']}")
    
    def _execute_default_logic(self):
        """Execute default HVAC control logic"""
        if not self.system_enabled:
            # System off - reset outputs
            self.memory.outputs['FanSpeed'] = 0
            self.memory.outputs['ChillerOn'] = False
            self.memory.outputs['SystemStatus'] = 0
            return
        
        # Calculate errors
        temp_error = self.memory.inputs['RoomTemperature'] - self.memory.inputs['SetpointTemp']
        humidity_error = self.memory.inputs['RoomHumidity'] - self.memory.inputs['SetpointHumidity']
        
        self.memory.internal['TempError'] = temp_error
        self.memory.internal['HumidityError'] = humidity_error
        
        # Determine cooling requirement
        cooling_required = temp_error > self.memory.inputs['TempDeadband']
        dehumid_required = humidity_error > self.memory.inputs['HumidityDeadband']
        
        self.memory.internal['CoolingRequired'] = cooling_required
        self.memory.internal['DehumidRequired'] = dehumid_required
        
        # Control logic
        if cooling_required or dehumid_required:
            self.memory.outputs['ChillerOn'] = True
            self.memory.outputs['SystemStatus'] = 1  # Cooling
            
            # Fan speed based on error magnitude
            if cooling_required:
                fan_speed = min(100, max(30, int(temp_error * 20)))
            else:
                fan_speed = 50  # Medium speed for dehumidification
            
            self.memory.outputs['FanSpeed'] = fan_speed
        else:
            self.memory.outputs['ChillerOn'] = False
            self.memory.outputs['FanSpeed'] = 20  # Low circulation
            self.memory.outputs['SystemStatus'] = 2  # Idle
    
    def get_diagnostics(self) -> Dict[str, Any]:
        """Get runtime diagnostics"""
        return {
            'cycle_count': self.cycle_count,
            'last_cycle_time_ms': self.last_cycle_time,
            'system_enabled': self.system_enabled,
            'program_loaded': self.program is not None
        }