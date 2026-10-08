PROGRAM HVAC_Control
VAR_INPUT
    SystemEnable : BOOL := FALSE;
    RoomTemperature : REAL := 20.0;
    RoomHumidity : REAL := 50.0;
    SetpointTemp : REAL := 22.0;
    SetpointHumidity : REAL := 45.0;
    TempDeadband : REAL := 1.0;
    HumidityDeadband : REAL := 5.0;
    SensorFault : BOOL := TRUE;  // set by the PLC I/O layer when plant sensor data is missing or stale
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
    HumidityLow : BOOL;
    FanSpeedCalc : REAL;
    ChillerWanted : BOOL;
    // Chiller anti-short-cycle timing, counted in scans (the PLC scans every 100 ms: 100 scans = 10 s; short because the simulated room has very little thermal mass)
    MinOnScans : INT := 100;
    MinOffScans : INT := 100;
    ChillerTimer : INT := 1000;  // scans since the chiller last changed state; starts "long ago"
END_VAR

// Scan counter for the chiller timing (saturates so it cannot grow without bound)
IF ChillerTimer < 100000 THEN
    ChillerTimer := ChillerTimer + 1;
END_IF;

// Main control logic
IF SensorFault THEN
    // Fail-safe: no trustworthy sensor data - everything off, alarm raised
    IF ChillerOn THEN
        ChillerTimer := 0;
    END_IF;
    FanSpeed := 0;
    ChillerOn := FALSE;
    SystemStatus := 0;
    AlarmActive := TRUE;
    CoolingRequired := FALSE;
    DehumidRequired := FALSE;

ELSIF SystemEnable THEN
    // Calculate temperature and humidity errors
    TempError := RoomTemperature - SetpointTemp;
    HumidityError := RoomHumidity - SetpointHumidity;

    // Hysteresis band: start above setpoint + deadband, stop below setpoint - deadband,
    // keep the previous demand in between
    TempHigh := TempError > TempDeadband;
    TempLow := TempError < -TempDeadband;
    HumidityHigh := HumidityError > HumidityDeadband;
    HumidityLow := HumidityError < -HumidityDeadband;

    IF TempHigh THEN
        CoolingRequired := TRUE;
    ELSIF TempLow THEN
        CoolingRequired := FALSE;
    END_IF;

    IF HumidityHigh THEN
        DehumidRequired := TRUE;
    ELSIF HumidityLow THEN
        DehumidRequired := FALSE;
    END_IF;

    // Chiller runs for either demand, but not before MinOffScans since it stopped
    // and not for less than MinOnScans since it started
    ChillerWanted := CoolingRequired OR DehumidRequired;

    IF ChillerWanted AND NOT ChillerOn AND ChillerTimer >= MinOffScans THEN
        ChillerOn := TRUE;
        ChillerTimer := 0;
    ELSIF NOT ChillerWanted AND ChillerOn AND ChillerTimer >= MinOnScans THEN
        ChillerOn := FALSE;
        ChillerTimer := 0;
    END_IF;

    IF ChillerOn THEN
        SystemStatus := 1;  // Cooling mode (cooling or dehumidification)

        IF CoolingRequired THEN
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
        ELSE
            FanSpeed := 50;  // Medium fan speed for dehumidification / minimum-on-time hold
        END_IF;
    ELSE
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
    IF ChillerOn THEN
        ChillerTimer := 0;
    END_IF;
    FanSpeed := 0;
    ChillerOn := FALSE;
    SystemStatus := 0;  // System off
    AlarmActive := FALSE;
    CoolingRequired := FALSE;
    DehumidRequired := FALSE;
END_IF;

END_PROGRAM
