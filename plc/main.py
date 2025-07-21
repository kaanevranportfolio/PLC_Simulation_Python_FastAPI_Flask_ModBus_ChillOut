import asyncio
import logging
import sys
from pathlib import Path
from st_parser import STParser
from plc_runtime import PLCRuntime
from modbus_interface import ModbusInterface

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Changed from INFO to DEBUG
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class PLCSimulator:
    def __init__(self):
        self.parser = STParser()
        self.runtime = None
        self.modbus = None
        self.running = False
   
   
    async def load_program(self, st_file_path):
        """Load and parse ST program"""
        try:
            if Path(st_file_path).exists():
                logger.info(f"Loading ST program from {st_file_path}")
                with open(st_file_path, 'r') as f:
                    st_code = f.read()
                
                # Parse the ST code
                program = self.parser.parse(st_code)
                
                # DEBUG: Let's see what we actually got
                if program:
                    logger.debug(f"Parsed program name: {program.name}")
                    logger.debug(f"Number of variables: {len(program.variables)}")
                    logger.debug(f"Variables: {program.variables}")
                    logger.debug(f"Number of statements: {len(program.statements)}")
                
                # Initialize runtime with parsed program
                self.runtime = PLCRuntime(program)
                logger.info("ST program loaded successfully")
                return True
            else:
                logger.warning(f"ST file not found: {st_file_path}")
                # Initialize with empty program
                self.runtime = PLCRuntime(None)
                return False
        except Exception as e:
            logger.error(f"Error loading ST program: {e}")
            import traceback
            traceback.print_exc()
            self.runtime = PLCRuntime(None)
            return False
    

    async def initialize_modbus(self):
        """Initialize Modbus connections"""
        self.modbus = ModbusInterface(self.runtime)
        # Don't await - just create the task
        asyncio.create_task(self.modbus.start_server(port=502))
        # Give server a moment to start
        await asyncio.sleep(0.5)
        # Now connect to physical model
        await self.modbus.connect_to_physical_model('physical-model', 503)
        logger.info("Modbus interfaces initialized")
    

    async def run_cycle(self):
        """Main PLC scan cycle"""
        cycle_time = 0.1  # 100ms scan cycle
        
        while self.running:
            try:
                cycle_start = asyncio.get_event_loop().time()
                
                # Read inputs from physical model via Modbus
                await self.modbus.read_inputs()
                
                # Execute PLC logic
                if self.runtime:
                    # Log before execution
                    logger.debug(f"Before PLC execution - SystemEnable: {self.runtime.memory.inputs.get('SystemEnable')}")
                    self.runtime.execute_cycle()
                    # Log after execution
                    logger.debug(f"After PLC execution - FanSpeed: {self.runtime.memory.outputs.get('FanSpeed')}, ChillerOn: {self.runtime.memory.outputs.get('ChillerOn')}")
                
                # Write outputs to physical model via Modbus
                await self.modbus.write_outputs()
                
                # Update Modbus server registers for backend
                await self.modbus.update_server_registers()
                
                # Maintain cycle time
                cycle_end = asyncio.get_event_loop().time()
                cycle_duration = cycle_end - cycle_start
                if cycle_duration < cycle_time:
                    await asyncio.sleep(cycle_time - cycle_duration)
                else:
                    logger.warning(f"Cycle overrun: {cycle_duration:.3f}s")
                    
            except Exception as e:
                logger.error(f"Error in PLC cycle: {e}")
                await asyncio.sleep(cycle_time)


    async def start(self):
        """Start the PLC simulator"""
        logger.info("Starting PLC Simulator")
        
        # Load ST program
        await self.load_program('/app/plc_programs/hvac_control.st')
        
        # Initialize Modbus (this will start the server and connect to physical model)
        await self.initialize_modbus()
        
        # Start PLC execution
        self.running = True
        await self.run_cycle()
    
    async def stop(self):
        """Stop the PLC simulator"""
        logger.info("Stopping PLC Simulator")
        self.running = False
        if self.modbus:
            await self.modbus.stop()

async def main():
    plc = PLCSimulator()
    
    try:
        await plc.start()
    except KeyboardInterrupt:
        logger.info("Shutdown signal received")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        await plc.stop()

if __name__ == "__main__":
    asyncio.run(main())