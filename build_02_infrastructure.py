#!/usr/bin/env python3
"""Dashboard 02 — Infrastructure & Hardware Health.
Physical infrastructure monitoring via BMC/IPMI/Redfish.
Answer: 'Is the data center environment healthy?'
"""
import json, sys
from panel_builders import *

def build_02():
    reset_ids()
    panels = []
    y = 0

    # ════════════════════════════════════════════════════════
    # ROW: Power Supply Unit Health
    # ════════════════════════════════════════════════════════
    panels.append(row("Power Supply Unit Health", y)); y += 1

    panels.append(stat(
        "Total PSUs Active", "RF_Active_PSU count across nodes.",
        {"h":5,"w":4,"x":0,"y":y},
        [tgt('sum(RF_Active_PSU{' + N + '}) or vector(0)','',instant=True)],
        color_mode="value",
        thresholds={"mode":"absolute","steps":[{"color":C_BL,"value":None}]}))

    panels.append(stat(
        "Healthy PSU Ratio", "TotalPowerShelfHealthyPSU — 1.0 = all healthy.",
        {"h":5,"w":4,"x":4,"y":y},
        [tgt('avg(TotalPowerShelfHealthyPSU{' + N + '})','',instant=True)],
        color_mode="background", unit="percentunit",
        thresholds={"mode":"absolute","steps":[
            {"color":C_FL,"value":None},{"color":C_WR,"value":0.8},
            {"color":C_OK,"value":1}]}))

    panels.append(stat(
        "Degraded PSUs", "TotalPowerShelfDegradedPSU — any > 0 = investigate.",
        {"h":5,"w":4,"x":8,"y":y},
        [tgt('sum(TotalPowerShelfDegradedPSU{' + N + '} == 1) or vector(0)','',instant=True)],
        color_mode="background",
        thresholds={"mode":"absolute","steps":[
            {"color":C_OK,"value":None},{"color":C_WR,"value":1}]}))

    panels.append(stat(
        "Critical PSUs", "TotalPowerShelfCriticalPSU — any > 0 = URGENT.",
        {"h":5,"w":4,"x":12,"y":y},
        [tgt('sum(TotalPowerShelfCriticalPSU{' + N + '} == 1) or vector(0)','',instant=True)],
        color_mode="background",
        thresholds={"mode":"absolute","steps":[
            {"color":C_OK,"value":None},{"color":C_FL,"value":1}]}))

    panels.append(ts(
        "PSU Input Voltage", "RF_Power_Supply_InputVoltage per PSU. Out of range = utility issue.",
        {"h":5,"w":8,"x":16,"y":y},
        [tgt('RF_Power_Supply_InputVoltage{' + N + '}','{{instance}} PSU{{psu_id}}')],
        axis="Voltage", unit="volt"))
    y += 5

    # ════════════════════════════════════════════════════════
    # ROW: Power Consumption
    # ════════════════════════════════════════════════════════
    panels.append(row("Power Consumption", y)); y += 1

    panels.append(ts(
        "PSU Input Power",
        "RF_Power_Supply_InputPower per node.",
        {"h":6,"w":8,"x":0,"y":y},
        [tgt('RF_Power_Supply_InputPower{' + N + '}','{{instance}} PSU{{psu_id}}')],
        axis="Power", unit="watt"))

    panels.append(ts(
        "PSU Output Power",
        "RF_Power_Supply_OutputPower per node.",
        {"h":6,"w":8,"x":8,"y":y},
        [tgt('RF_Power_Supply_OutputPower{' + N + '}','{{instance}} PSU{{psu_id}}')],
        axis="Power", unit="watt"))

    panels.append(ts(
        "Circuit Power (Total)",
        "CircuitPower / TotalCircuitPower across racks.",
        {"h":6,"w":8,"x":16,"y":y},
        [tgt('CircuitPower{' + N + '}','{{instance}} Circuit'),
         tgt('TotalCircuitPower','Total')],
        axis="Power", unit="watt"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: CDU Cooling Health
    # ════════════════════════════════════════════════════════
    panels.append(row("CDU Cooling Health", y)); y += 1

    panels.append(ts(
        "CDU Liquid Flow Rate",
        "CDULiquidFlow — below minimum = reduced cooling capacity.",
        {"h":6,"w":6,"x":0,"y":y},
        [tgt('CDULiquidFlow{' + N + '}','{{instance}}')],
        axis="Flow Rate"))

    panels.append(ts(
        "CDU Supply Temperature",
        "CDULiquidSupplyTemperature — cold side entering the rack.",
        {"h":6,"w":6,"x":6,"y":y},
        [tgt('CDULiquidSupplyTemperature{' + N + '}','{{instance}}')],
        axis="Temperature", unit="celsius"))

    panels.append(ts(
        "CDU Return Temperature",
        "CDULiquidReturnTemperature — hot side leaving the rack. Rising = cooling deficit.",
        {"h":6,"w":6,"x":12,"y":y},
        [tgt('CDULiquidReturnTemperature{' + N + '}','{{instance}}')],
        axis="Temperature", unit="celsius"))

    panels.append(ts(
        "CDU Differential Pressure",
        "CDULiquidDifferentialPressure — anomalies indicate blockage or pump failure.",
        {"h":6,"w":6,"x":18,"y":y},
        [tgt('CDULiquidDifferentialPressure{' + N + '}','{{instance}}')],
        axis="Pressure"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: Leak Detection
    # ════════════════════════════════════════════════════════
    panels.append(row("⚠️ Leak Detection", y)); y += 1

    panels.append(stat(
        "🚨 Devices With Leaks",
        "DevicesWithLeaks — ANY > 0 = EMERGENCY. Follow facility leak procedures.",
        {"h":5,"w":6,"x":0,"y":y},
        [tgt('sum(DevicesWithLeaks{' + N + '}) or vector(0)','',instant=True)],
        color_mode="background",
        thresholds={"mode":"absolute","steps":[
            {"color":C_OK,"value":None},{"color":C_FL,"value":1}]}))

    panels.append(stat(
        "Leak Sensor Faults",
        "LeakSensorFaultRack — sensor fault may MASK an actual leak.",
        {"h":5,"w":6,"x":6,"y":y},
        [tgt('sum(LeakSensorFaultRack{' + N + '}) or vector(0)','',instant=True)],
        color_mode="background",
        thresholds={"mode":"absolute","steps":[
            {"color":C_OK,"value":None},{"color":C_WR,"value":1}]}))

    panels.append(stat(
        "Electrical Isolation",
        "LeakResponseRackElectricalIsolationStatus — isolation triggered by leak.",
        {"h":5,"w":6,"x":12,"y":y},
        [tgt('sum(LeakResponseRackElectricalIsolationStatus{' + N + '}) or vector(0)','',instant=True)],
        color_mode="background",
        thresholds={"mode":"absolute","steps":[
            {"color":C_OK,"value":None},{"color":C_FL,"value":1}]}))

    panels.append(stat(
        "Liquid Isolation",
        "LeakResponseRackLiquidIsolationStatus — liquid isolation triggered.",
        {"h":5,"w":6,"x":18,"y":y},
        [tgt('sum(LeakResponseRackLiquidIsolationStatus{' + N + '}) or vector(0)','',instant=True)],
        color_mode="background",
        thresholds={"mode":"absolute","steps":[
            {"color":C_OK,"value":None},{"color":C_FL,"value":1}]}))
    y += 5

    # ════════════════════════════════════════════════════════
    # ROW: CPU & System Thermal
    # ════════════════════════════════════════════════════════
    panels.append(row("CPU & System Thermal", y)); y += 1

    panels.append(ts(
        "CPU1 Temperature",
        "RF_CPU1Temp — CPU1 junction temperature.",
        {"h":6,"w":6,"x":0,"y":y},
        [tgt('RF_CPU1Temp{' + N + '}','{{instance}}')],
        axis="Temperature", unit="celsius"))

    panels.append(ts(
        "CPU2 Temperature",
        "RF_CPU2Temp — CPU2 junction temperature.",
        {"h":6,"w":6,"x":6,"y":y},
        [tgt('RF_CPU2Temp{' + N + '}','{{instance}}')],
        axis="Temperature", unit="celsius"))

    panels.append(ts(
        "CPU VRM Temperature",
        "RF_CPU1RearTemp / RF_CPU2RearTemp — VRM thermal.",
        {"h":6,"w":6,"x":12,"y":y},
        [tgt('RF_CPU1RearTemp{' + N + '}','{{instance}} CPU1 VRM'),
         tgt('RF_CPU2RearTemp{' + N + '}','{{instance}} CPU2 VRM')],
        axis="Temperature", unit="celsius"))

    panels.append(ts(
        "Fan Speed",
        "RF_Power_Supply_FanSpeed / gpu_fan_speed — cooling fan status.",
        {"h":6,"w":6,"x":18,"y":y},
        [tgt('RF_Power_Supply_FanSpeed{' + N + '}','{{instance}} PSU Fan'),
         tgt('gpu_fan_speed{' + N + '}','{{instance}} GPU Fan')],
        axis="RPM"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: Disk Health (SMART) & DPU/NIC
    # ════════════════════════════════════════════════════════
    panels.append(row("Disk Health (SMART) & DPU/NIC", y)); y += 1

    panels.append(ts(
        "SMART Reallocated Sectors",
        "smart_reallocated_sector_ct — rising = disk degradation.",
        {"h":6,"w":6,"x":0,"y":y},
        [tgt('smart_reallocated_sector_ct{' + N + '}','{{instance}} {{disk}}')],
        axis="Sectors"))

    panels.append(ts(
        "SMART Pending Sectors",
        "smart_current_pending_sector — > 0 = pre-fail indicator.",
        {"h":6,"w":6,"x":6,"y":y},
        [tgt('smart_current_pending_sector{' + N + '}','{{instance}} {{disk}}')],
        axis="Pending Sectors"))

    panels.append(ts(
        "Disk Temperature",
        "smart_temperature — elevated temp = cooling or workload issue.",
        {"h":6,"w":6,"x":12,"y":y},
        [tgt('smart_temperature{' + N + '}','{{instance}} {{disk}}')],
        axis="Temperature", unit="celsius"))

    panels.append(ts(
        "BlueField DPU Temperature",
        "RF_BF3_Slot_1_NIC_Temp_0 / Slot_2 — DPU thermal monitoring.",
        {"h":6,"w":6,"x":18,"y":y},
        [tgt('RF_BF3_Slot_1_NIC_Temp_0{' + N + '}','{{instance}} DPU Slot1'),
         tgt('RF_BF3_Slot_2_NIC_Temp_0{' + N + '}','{{instance}} DPU Slot2')],
        axis="Temperature", unit="celsius"))
    y += 6

    # ════════════════════════════════════════════════════════
    # ROW: Voltage Monitoring & HW Profile
    # ════════════════════════════════════════════════════════
    panels.append(row("Voltage Monitoring & Hardware Profile", y)); y += 1

    panels.append(ts(
        "CPU VCCIN Voltage",
        "RF_CPU1_VCCIN — CPU input voltage rail. Out of spec = power delivery issue.",
        {"h":6,"w":6,"x":0,"y":y},
        [tgt('RF_CPU1_VCCIN{' + N + '}','{{instance}} CPU1'),
         tgt('RF_CPU1_VCCHV{' + N + '}','{{instance}} CPU1 HV')],
        axis="Voltage", unit="volt"))

    panels.append(ts(
        "PSU Rail Voltage",
        "RF_Power_Supply_RailVoltage — per-PSU rail output.",
        {"h":6,"w":6,"x":6,"y":y},
        [tgt('RF_Power_Supply_RailVoltage{' + N + '}','{{instance}} PSU{{psu_id}}')],
        axis="Voltage", unit="volt"))

    panels.append(stat(
        "BMC Status",
        "nvsm_pci_health — 0 = OK, non-zero = investigate.",
        {"h":6,"w":6,"x":12,"y":y},
        [tgt('nvsm_pci_health{' + N + '}','{{instance}}',instant=True)],
        color_mode="background",
        mappings=[
            {"type":"value","options":{"0":{"text":"HEALTHY","color":C_OK}}},
            {"type":"range","options":{"from":1,"to":999,"result":{"text":"DEGRADED","color":C_FL}}}],
        thresholds={"mode":"absolute","steps":[
            {"color":C_OK,"value":None},{"color":C_FL,"value":1}]}))

    panels.append(stat(
        "Hardware Profile Match",
        "hardware-profile data producer health check. FAIL = hardware configuration drift.",
        {"h":6,"w":6,"x":18,"y":y},
        [tgt('bcm_health_check_status{' + N + ', check="hardware-profile"}','{{instance}}',instant=True)],
        color_mode="background",
        mappings=[
            {"type":"value","options":{"0":{"text":"MATCH","color":C_OK}}},
            {"type":"value","options":{"1":{"text":"DRIFT","color":C_FL}}}],
        thresholds={"mode":"absolute","steps":[
            {"color":C_OK,"value":None},{"color":C_FL,"value":1}]}))
    y += 6

    # ── Build dashboard ──
    return wrap_dashboard(
        uid=UIDS["02"],
        title="BMaaS — 02 Infrastructure & Hardware Health",
        description="Physical infrastructure monitoring: PSU health, power consumption, CDU cooling, "
                    "leak detection, CPU thermal, SMART disk health, DPU/NIC, voltage rails, BMC status.",
        tags=["bmaas","infrastructure","hardware","psu","cdu","cooling","leak","smart","bcm11"],
        panels=panels,
        templating=standard_templating(),
        links=sub_dashboard_links()
    )


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "dashboards/02-infrastructure-hardware-health.json"
    d = build_02()
    with open(out, "w") as f:
        json.dump(d, f, indent=4)
    print(f"Generated {out}: {len(d['panels'])} panels")
    for p in d["panels"]:
        print(f"  [{p.get('type',''):14s}] {p.get('title','')}")
