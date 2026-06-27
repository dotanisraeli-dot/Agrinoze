"use client"

import { type ChangeEvent, useCallback, useEffect, useRef, useState } from "react"
import {
  READINGS_PER_DAY,
  SPEED_INTERVALS,
  SPEED_LABELS,
  theme,
  VWC_RANGE,
  type SoilType,
} from "@/lib/theme"
import {
  applyOverride,
  createEngine,
  effectiveProgram,
  exitOverride,
  exportLog,
  freeze,
  runDecision,
  startSystem,
  unfreeze,
} from "@/lib/engine"
import { averageReadings, generateReadings, initSensorModel, readSensors, stepSensorModel } from "@/lib/sensor-model"
import { parseCsv } from "@/lib/csv"
import type { Alert, ChartPoint, Engine, OverrideMode, SensorModel, SensorReading, TableRow } from "@/lib/types"
import { Header } from "./header"
import { HowTo } from "./how-to"
import { ControlBar } from "./control-bar"
import { StageStepper } from "./stage-stepper"
import { SensorCards } from "./sensor-cards"
import { SensorChart, type ChartView } from "./sensor-chart"
import { DecisionLog } from "./decision-log"
import { DataTable } from "./data-table"
import { StatusPanels } from "./status-panels"
import { ExitOverrideModal, FreezeModal, OverrideModal, StartModal } from "./modals"

export function Simulator() {
  const [soilType, setSoilType] = useState<SoilType>("medium")
  const [engine, setEngine] = useState<Engine | null>(null)
  const [, setSensorModel] = useState<SensorModel | null>(null)
  const [day, setDay] = useState(0)
  const [chartData, setChartData] = useState<ChartPoint[]>([])
  const [tableData, setTableData] = useState<TableRow[]>([])
  const [running, setRunning] = useState(false)
  const [speedIdx, setSpeedIdx] = useState(1)
  const [chartView, setChartView] = useState<ChartView>("combined")
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [fileData, setFileData] = useState<SensorReading[] | null>(null)
  const [fileName, setFileName] = useState("")
  const [fileCursor, setFileCursor] = useState(0)
  const [log, setLog] = useState<string[]>([])

  const [showLog, setShowLog] = useState(false)
  const [showHowTo, setShowHowTo] = useState(false)
  const [showStart, setShowStart] = useState(false)
  const [showFreeze, setShowFreeze] = useState(false)
  const [showOverride, setShowOverride] = useState(false)
  const [showExit, setShowExit] = useState(false)

  const [overrideMode, setOverrideMode] = useState<OverrideMode>("semi_auto")
  const [ovPulses, setOvPulses] = useState(150)
  const [ovSec, setOvSec] = useState(30)

  const engineRef = useRef<Engine | null>(null)
  const sensorModelRef = useRef<SensorModel | null>(null)
  const dayCounterRef = useRef(0)
  const fileDataRef = useRef<SensorReading[] | null>(null)
  const fileIndexRef = useRef(0)

  const reset = useCallback((soil: SoilType) => {
    const e = createEngine({
      soilType: soil,
      has40cm: soil !== "soilless",
      extPulse: false,
      cal2MaxDays: 14,
      dischargeLph: 1,
      drippers: 100,
    })
    const model = initSensorModel(soil)
    engineRef.current = e
    sensorModelRef.current = model
    dayCounterRef.current = 0
    fileIndexRef.current = 0
    setEngine({ ...e })
    setSensorModel({ ...model })
    setDay(0)
    setChartData([])
    setTableData([])
    setAlerts([])
    setLog([])
    setRunning(false)
    setFileCursor(0)
  }, [])

  useEffect(() => {
    reset(soilType)
  }, [soilType, reset])

  const loadFile = useCallback(
    (ev: ChangeEvent<HTMLInputElement>) => {
      const file = ev.target.files?.[0]
      if (!file) return
      const reader = new FileReader()
      reader.onload = (e) => {
        const rows = parseCsv(e.target?.result as string)
        if (rows.length === 0) {
          alert(
            "Could not parse file. Expected CSV/TXT with columns:\n  Wide:  date,T20,T40,VWC\n  Tall:  date,sensor,value",
          )
          return
        }
        fileDataRef.current = rows
        setFileData(rows)
        setFileName(file.name)
        fileIndexRef.current = 0
        setFileCursor(0)
        reset(soilType)
        alert(
          `Loaded ${rows.length} days from "${file.name}". Press Start system → Run sim to replay through the algorithm.`,
        )
      }
      reader.readAsText(file)
      ev.target.value = ""
    },
    [soilType, reset],
  )

  const clearFile = useCallback(() => {
    fileDataRef.current = null
    setFileData(null)
    setFileName("")
    fileIndexRef.current = 0
    setFileCursor(0)
    reset(soilType)
  }, [soilType, reset])

  const step = useCallback(() => {
    const e = engineRef.current
    const model = sensorModelRef.current
    if (!e || !model || e.stage === "awaiting") return

    const newDay = dayCounterRef.current + 1
    dayCounterRef.current = newDay

    let reading: SensorReading
    const file = fileDataRef.current
    if (file && fileIndexRef.current < file.length) {
      const row = file[fileIndexRef.current]
      fileIndexRef.current++
      setFileCursor(fileIndexRef.current)
      reading = { t20: row.t20, t40: row.t40, vwc: row.vwc, n: 1, date: row.date }
    } else {
      if (file && fileIndexRef.current >= file.length) {
        setRunning(false)
        return
      }
      const prog = effectiveProgram(e)
      const newModel = stepSensorModel(model, prog, e.cfg.dischargeLph, e.frozen)
      sensorModelRef.current = newModel
      setSensorModel({ ...newModel })
      const sensors = readSensors(newModel)
      const readings = generateReadings(sensors.t20, sensors.t40, sensors.vwc)
      reading = averageReadings(readings)
    }

    runDecision(e, reading, newDay)
    const buffer = [...e.logBuffer, ""]
    setLog((prev) => [...prev, ...buffer])
    setEngine({ ...e })
    setDay(newDay)
    setAlerts([...e.alerts].reverse().slice(0, 12))
    setChartData((prev) =>
      [
        ...prev,
        { day: newDay, t20: reading.t20, t40: reading.t40, vwc: reading.vwc, pulses: e.program.pulses, stage: e.stage },
      ].slice(-120),
    )
    setTableData((prev) =>
      [
        ...prev,
        {
          day: newDay,
          t20: reading.t20,
          t40: reading.t40,
          vwc: reading.vwc,
          n: reading.n ?? READINGS_PER_DAY,
          stage: e.stage,
          pulses: e.program.pulses,
          date: reading.date,
        },
      ].slice(-180),
    )
  }, [])

  useEffect(() => {
    if (!running) return
    const id = setInterval(step, SPEED_INTERVALS[speedIdx])
    return () => clearInterval(id)
  }, [running, speedIdx, step])

  if (!engine) return null

  const fileActive = !!fileData
  const has40cm = engine.cfg.has40cm
  const vwcRange = VWC_RANGE[soilType]
  const pendingChange = !!engine.pendingProgram || engine.pendingOverrideMode !== null
  const last = chartData.at(-1)
  const live = { t20: last?.t20 ?? 0, t40: last?.t40 ?? 0, vwc: last?.vwc ?? 0 }

  const sync = () => setEngine({ ...(engineRef.current as Engine) })

  return (
    <div
      style={{
        background: theme.bg,
        minHeight: "100vh",
        color: theme.chalk,
        fontFamily: "'Inter','SF Pro Display',system-ui,sans-serif",
      }}
    >
      <Header
        day={day}
        soilType={soilType}
        onSoilChange={setSoilType}
        fileActive={fileActive}
        fileName={fileName}
        fileCursor={fileCursor}
        fileTotal={fileData?.length ?? 0}
        onLoadFile={loadFile}
        onClearFile={clearFile}
      />

      <div style={{ maxWidth: 1180, margin: "0 auto", padding: "16px 20px", display: "flex", flexDirection: "column", gap: 14 }}>
        <HowTo open={showHowTo} onToggle={() => setShowHowTo((v) => !v)} />

        <ControlBar
          engine={engine}
          day={day}
          running={running}
          logLength={log.length}
          showLog={showLog}
          fileActive={fileActive}
          fileName={fileName}
          pendingChange={pendingChange}
          onStart={() => setShowStart(true)}
          onToggleRun={() => setRunning((r) => !r)}
          onToggleLog={() => setShowLog((s) => !s)}
          onExportLog={() => exportLog(log, soilType, fileName)}
          onOverride={() => setShowOverride(true)}
          onExitOverride={() => setShowExit(true)}
          onFreeze={() => setShowFreeze(true)}
          onUnfreeze={() => {
            unfreeze(engineRef.current as Engine)
            sync()
          }}
          onReset={() => reset(soilType)}
        />

        <StageStepper engine={engine} day={day} />

        <SensorCards
          t20={live.t20}
          t40={live.t40}
          vwc={live.vwc}
          has40cm={has40cm}
          vwcRange={vwcRange}
          fileActive={fileActive}
        />

        <SensorChart
          data={chartData}
          view={chartView}
          has40cm={has40cm}
          fileActive={fileActive}
          speedIdx={speedIdx}
          speedLabel={SPEED_LABELS[speedIdx]}
          onSpeedChange={setSpeedIdx}
          onStep={step}
          stepDisabled={running}
          canStep={engine.stage !== "awaiting"}
          onViewChange={setChartView}
        />

        {showLog && <DecisionLog log={log} onExport={() => exportLog(log, soilType, fileName)} onClear={() => setLog([])} />}

        <DataTable rows={tableData} fileActive={fileActive} fileName={fileName} />

        {fileActive && (
          <div
            style={{
              display: "flex",
              gap: 10,
              alignItems: "flex-start",
              background: `${theme.blue}10`,
              border: `1px solid ${theme.blue}33`,
              borderRadius: 8,
              padding: "10px 14px",
              fontSize: 17.2,
              color: theme.sub,
              lineHeight: 1.5,
            }}
          >
            <span style={{ color: theme.blue, fontSize: 21, flexShrink: 0 }}>📂</span>
            <span>
              <strong style={{ color: theme.blue }}>File mode active.</strong> The SensAItion algorithm is processing
              real sensor data from <strong style={{ color: theme.chalk }}>{fileName}</strong> — {fileData?.length} days
              loaded. The simulation will auto-stop when all rows have been processed. Export the decision log to review
              every algorithm choice.
            </span>
          </div>
        )}

        <StatusPanels
          engine={engine}
          alerts={alerts}
          onAck={() => {
            ;(engineRef.current as Engine).t40Acked = true
            sync()
          }}
        />
      </div>

      {showStart && (
        <StartModal
          soilType={soilType}
          fileActive={fileActive}
          fileTotal={fileData?.length ?? 0}
          fileName={fileName}
          onCancel={() => setShowStart(false)}
          onConfirm={() => {
            startSystem(engineRef.current as Engine, 0)
            sync()
            setShowStart(false)
            setRunning(true)
          }}
        />
      )}

      {showFreeze && (
        <FreezeModal
          onCancel={() => setShowFreeze(false)}
          onConfirm={() => {
            freeze(engineRef.current as Engine)
            sync()
            setShowFreeze(false)
          }}
        />
      )}

      {showOverride && (
        <OverrideModal
          mode={overrideMode}
          setMode={setOverrideMode}
          pulses={ovPulses}
          setPulses={setOvPulses}
          sec={ovSec}
          setSec={setOvSec}
          onCancel={() => setShowOverride(false)}
          onExecute={() => {
            applyOverride(engineRef.current as Engine, overrideMode, ovPulses, ovSec, dayCounterRef.current)
            sync()
            setShowOverride(false)
          }}
        />
      )}

      {showExit && (
        <ExitOverrideModal
          engine={engine}
          onCancel={() => setShowExit(false)}
          onChoose={(choice) => {
            exitOverride(engineRef.current as Engine, choice, dayCounterRef.current)
            sync()
            setShowExit(false)
          }}
        />
      )}
    </div>
  )
}
