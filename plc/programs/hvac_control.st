PROGRAM HVAC_Control
VAR_INPUT
    SystemEnable : BOOL := FALSE;
    RoomTemperature : REAL := 20.0;
    RoomHumidity : REAL := 50.0;
    SetpointTemp : REAL := 22.0;
    SetpointHumidity : REAL := 45.0;
    TempDeadband : REAL := 1.0;
    HumidityDeadband : REAL := 5.0;
END_VAR

VAR_OUTPUT
    FanSpeed : INT := 0;
    ChillerOn : BOOL := FALSE;
    SystemStatus : INT := 0;  // 0=Off, 1=Cooling, 2=Idle
    AlarmActive : BOOL := FALSE;
END_VAR

VAR
    TempError : REAL;
    HumidityError : REAL;
    CoolingRequired : BOOL;
    DehumidRequired : BOOL;
    TempHigh : BOOL;
    TempLow : BOOL;
    HumidityHigh : BOOL;
    FanSpeedCalc : REAL;
END_VAR

// Main control logic
IF SystemEnable THEN
    // Calculate temperature and humidity errors
    TempError := RoomTemperature - SetpointTemp;
    HumidityError := RoomHumidity - SetpointHumidity;
    
    // Check temperature conditions
    TempHigh := TempError > TempDeadband;
    TempLow := TempError < -TempDeadband;
    
    // Check humidity conditions
    HumidityHigh := HumidityError > HumidityDeadband;
    
    // Determine if cooling or dehumidification is required
    CoolingRequired := TempHigh;
    DehumidRequired := HumidityHigh AND NOT CoolingRequired;
    
    // Control logic for cooling mode
    IF CoolingRequired THEN
        ChillerOn := TRUE;
        SystemStatus := 1;  // Cooling mode
        
        // Calculate fan speed based on temperature error
        // Higher error = higher fan speed
        FanSpeedCalc := 30.0 + (TempError * 20.0);
        
        // Limit fan speed between 30% and 100%
        IF FanSpeedCalc > 100.0 THEN
            FanSpeed := 100;
        ELSIF FanSpeedCalc < 30.0 THEN
            FanSpeed := 30;
        ELSE
            FanSpeed := FanSpeedCalc;
        END_IF;
        
    // Control logic for dehumidification mode
    ELSIF DehumidRequired THEN
        ChillerOn := TRUE;
        SystemStatus := 1;  // Cooling mode (for dehumidification)
        FanSpeed := 50;     // Medium fan speed for dehumidification
        
    // Idle mode - maintain air circulation
    ELSE
        ChillerOn := FALSE;
        SystemStatus := 2;  // Idle mode
        FanSpeed := 20;     // Low fan speed for circulation
    END_IF;
    
    // Alarm conditions
    IF RoomTemperature > 35.0 OR RoomTemperature < 10.0 THEN
        AlarmActive := TRUE;
    ELSIF RoomHumidity > 80.0 OR RoomHumidity < 20.0 THEN
        AlarmActive := TRUE;
    ELSE
        AlarmActive := FALSE;
    END_IF;
    
ELSE
    // System disabled - turn everything off
    FanSpeed := 0;
    ChillerOn := FALSE;
    SystemStatus := 0;  // System off
    AlarmActive := FALSE;
END_IF;

END_PROGRAM