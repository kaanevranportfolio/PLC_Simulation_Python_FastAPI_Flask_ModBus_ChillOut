FROM python:3.9-slim

WORKDIR /app

# Install required packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create directory for PLC programs
RUN mkdir -p /app/plc_programs

# Make scripts executable
RUN chmod +x entrypoint.sh

# Expose Modbus port
EXPOSE 502

# Run the PLC simulator
ENTRYPOINT ["./entrypoint.sh"]