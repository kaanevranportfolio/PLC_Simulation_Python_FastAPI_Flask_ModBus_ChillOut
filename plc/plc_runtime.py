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
            'HumidityDeadband': 5.0,
            'SensorFault': True  # no plant data yet; set by the Modbus interface every scan
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
            'DehumidRequired': False,
            'ChillerTimer': 1000  # scans since the chiller last changed state; starts "long ago"
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
    
    # Chiller anti-short-cycle timing in scans (100 ms scan -> 100 scans = 10 s); same values as hvac_control.st
    MIN_ON_SCANS = 100
    MIN_OFF_SCANS = 100

    def _execute_default_logic(self):
        """Fallback used when no ST program is loaded. Mirrors hvac_control.st decision for decision
        (tests/test_st_program.py runs both side by side)."""
        inp, out, st = self.memory.inputs, self.memory.outputs, self.memory.internal

        if st['ChillerTimer'] < 100000:
            st['ChillerTimer'] += 1

        if inp.get('SensorFault', True):
            # Fail-safe: no trustworthy sensor data - everything off and alarm raised
            if out['ChillerOn']:
                st['ChillerTimer'] = 0
            out['FanSpeed'] = 0
            out['ChillerOn'] = False
            out['SystemStatus'] = 0
            out['AlarmActive'] = True
            st['CoolingRequired'] = False
            st['DehumidRequired'] = False
            return

        if not self.system_enabled:
            # System off - reset outputs
            if out['ChillerOn']:
                st['ChillerTimer'] = 0
            out['FanSpeed'] = 0
            out['ChillerOn'] = False
            out['SystemStatus'] = 0
            out['AlarmActive'] = False
            st['CoolingRequired'] = False
            st['DehumidRequired'] = False
            return

        temp_error = inp['RoomTemperature'] - inp['SetpointTemp']
        humidity_error = inp['RoomHumidity'] - inp['SetpointHumidity']
        st['TempError'] = temp_error
        st['HumidityError'] = humidity_error

        # Hysteresis band: start above +deadband, stop below -deadband, keep previous demand in between
        if temp_error > inp['TempDeadband']:
            st['CoolingRequired'] = True
        elif temp_error < -inp['TempDeadband']:
            st['CoolingRequired'] = False
        if humidity_error > inp['HumidityDeadband']:
            st['DehumidRequired'] = True
        elif humidity_error < -inp['HumidityDeadband']:
            st['DehumidRequired'] = False

        wanted = st['CoolingRequired'] or st['DehumidRequired']
        if wanted and not out['ChillerOn'] and st['ChillerTimer'] >= self.MIN_OFF_SCANS:
            out['ChillerOn'] = True
            st['ChillerTimer'] = 0
        elif not wanted and out['ChillerOn'] and st['ChillerTimer'] >= self.MIN_ON_SCANS:
            out['ChillerOn'] = False
            st['ChillerTimer'] = 0

        if out['ChillerOn']:
            out['SystemStatus'] = 1
            if st['CoolingRequired']:
                out['FanSpeed'] = min(100, max(30, int(30 + temp_error * 20)))  # same law as hvac_control.st
            else:
                out['FanSpeed'] = 50
        else:
            out['SystemStatus'] = 2
            out['FanSpeed'] = 20

        t, h = inp['RoomTemperature'], inp['RoomHumidity']
        out['AlarmActive'] = bool(t > 35.0 or t < 10.0 or h > 80.0 or h < 20.0)

    def get_diagnostics(self) -> Dict[str, Any]:
        """Get runtime diagnostics"""
        return {
            'cycle_count': self.cycle_count,
            'last_cycle_time_ms': self.last_cycle_time,
            'system_enabled': self.system_enabled,
            'program_loaded': self.program is not None
        }