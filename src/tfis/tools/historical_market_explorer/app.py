from __future__ import annotations

import argparse
import json
import threading
import webbrowser
from datetime import date, time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from tfis.tools.historical_market_explorer.service import (
    HistoricalMarketExplorerError,
    HistoricalMarketExplorerService,
    parse_date,
    parse_option_type,
    parse_time,
)


def run_server(
    *,
    data_root: str | Path = r"D:\HistoricalData",
    host: str = "127.0.0.1",
    port: int = 8787,
    open_browser: bool = True,
) -> ThreadingHTTPServer:
    service = HistoricalMarketExplorerService(data_root=data_root)
    handler = _handler_factory(service)
    server = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{server.server_address[1]}/"
    print(f"TFIS Historical Market Explorer: {url}")
    print(f"Read-only data root: {Path(data_root)}")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nTFIS Historical Market Explorer stopped.")
    finally:
        server.server_close()
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run TFIS Historical Market Explorer.")
    parser.add_argument("--data-root", default=r"D:\HistoricalData")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--no-open", action="store_true", help="Do not open a browser automatically.")
    args = parser.parse_args(argv)
    run_server(
        data_root=args.data_root,
        host=args.host,
        port=args.port,
        open_browser=not args.no_open,
    )
    return 0


def _handler_factory(service: HistoricalMarketExplorerService):
    class HistoricalMarketExplorerHandler(BaseHTTPRequestHandler):
        server_version = "TFISHistoricalMarketExplorer/1.0"

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            try:
                if parsed.path in ("", "/"):
                    self._send_html(_HTML)
                elif parsed.path == "/api/instruments":
                    self._send_json({"instruments": service.instruments()})
                elif parsed.path == "/api/sessions":
                    self._send_json(service.sessions(_required(query, "instrument")))
                elif parsed.path == "/api/expiries":
                    self._send_json(
                        service.expiries(
                            _required(query, "instrument"),
                            parse_date(_required(query, "date")),
                        )
                    )
                elif parsed.path == "/api/strikes":
                    self._send_json(
                        service.strikes(
                            _required(query, "instrument"),
                            parse_date(_required(query, "date")),
                            parse_date(_required(query, "expiry")),
                            parse_option_type(_required(query, "option_type")),
                        )
                    )
                elif parsed.path == "/api/lot-size":
                    self._send_json(
                        service.lot_size_payload(
                            instrument=_required(query, "instrument"),
                            reference_date=parse_date(_required(query, "reference_date")),
                        )
                    )
                elif parsed.path == "/api/contract":
                    self._send_json(_contract_payload(service, query))
                elif parsed.path == "/api/option-chain":
                    self._send_json(_option_chain_payload(service, query))
                elif parsed.path == "/api/manual-strike-scan":
                    self._send_json(_manual_strike_scan_payload(service, query))
                elif parsed.path == "/api/daily-option-history":
                    self._send_json(_daily_option_history_payload(service, query))
                elif parsed.path == "/api/export":
                    self._send_csv(service, query)
                else:
                    self._send_json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)
            except (HistoricalMarketExplorerError, ValueError) as exc:
                self._send_json(
                    {"error": type(exc).__name__, "message": str(exc)},
                    status=HTTPStatus.BAD_REQUEST,
                )

        def log_message(self, format: str, *args: object) -> None:
            print(f"[historical-market-explorer] {self.address_string()} {format % args}")

        def _send_json(self, payload: object, *, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self._write_body(body)

        def _send_html(self, html: str) -> None:
            body = html.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self._write_body(body)

        def _send_csv(
            self,
            service: HistoricalMarketExplorerService,
            query: dict[str, list[str]],
        ) -> None:
            section = _required(query, "section")
            if section == "option_chain":
                payload = _option_chain_payload(service, query)
                csv_text = service.export_csv(payload, section)
            elif section == "manual_scan":
                payload = _manual_strike_scan_payload(service, query)
                csv_text = service.export_csv(payload, section)
            elif section == "daily_option_history":
                payload = _daily_option_history_payload(service, query)
                csv_text = service.export_csv(payload, section)
            else:
                payload = _contract_payload(service, query)
                csv_text = service.export_csv(payload, section)
            body = csv_text.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Disposition", f"attachment; filename={section}.csv")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self._write_body(body)

        def _write_body(self, body: bytes) -> None:
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionAbortedError):
                return

    return HistoricalMarketExplorerHandler


def _required(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key)
    if not values or values[0] == "":
        raise HistoricalMarketExplorerError(f"Missing required query parameter: {key}")
    return values[0]


def _optional_int(query: dict[str, list[str]], key: str) -> int | None:
    value = query.get(key, [""])[0]
    return int(value) if value != "" else None


def _optional_float(query: dict[str, list[str]], key: str) -> float | None:
    value = query.get(key, [""])[0]
    return float(value) if value != "" else None


def _contract_payload(
    service: HistoricalMarketExplorerService,
    query: dict[str, list[str]],
) -> dict:
    return service.contract_payload(
        instrument=_required(query, "instrument"),
        session_date=parse_date(_required(query, "date")),
        expiry=parse_date(_required(query, "expiry")),
        strike=int(_required(query, "strike")),
        option_type=parse_option_type(_required(query, "option_type")),
        start_time=parse_time(query.get("start_time", [""])[0]),
        end_time=parse_time(query.get("end_time", [""])[0]),
    )


def _option_chain_payload(
    service: HistoricalMarketExplorerService,
    query: dict[str, list[str]],
) -> dict:
    return service.option_chain_payload(
        instrument=_required(query, "instrument"),
        session_date=parse_date(_required(query, "date")),
        expiry=parse_date(_required(query, "expiry")),
        snapshot_time=parse_time(query.get("time", ["09:16:00"])[0], default=time(9, 16)) or time(9, 16),
        selected_strike=_optional_int(query, "selected_strike"),
        ideal_premium=_optional_float(query, "ideal_premium"),
        minimum_premium=_optional_float(query, "minimum_premium"),
        minimum_oi=_optional_int(query, "minimum_oi"),
        start_strike=_optional_int(query, "start_strike"),
        end_strike=_optional_int(query, "end_strike"),
    )


def _manual_strike_scan_payload(
    service: HistoricalMarketExplorerService,
    query: dict[str, list[str]],
) -> dict:
    return service.manual_strike_scan_payload(
        instrument=_required(query, "instrument"),
        session_date=parse_date(_required(query, "date")),
        expiry=parse_date(_required(query, "expiry")),
        option_type=parse_option_type(_required(query, "option_type")),
        snapshot_time=parse_time(query.get("time", ["09:16:00"])[0], default=time(9, 16)) or time(9, 16),
        start_strike=int(_required(query, "start_strike")),
        end_strike=int(_required(query, "end_strike")),
        history_sessions=int(query.get("history_sessions", ["3"])[0] or "3"),
        premium_reference=_optional_float(query, "premium_reference"),
        ideal_factor_pct=_optional_float(query, "ideal_factor_pct"),
        minimum_factor_pct=_optional_float(query, "minimum_factor_pct"),
        ideal_premium=_optional_float(query, "ideal_premium"),
        minimum_premium=_optional_float(query, "minimum_premium"),
        minimum_oi=_optional_int(query, "minimum_oi"),
    )


def _daily_option_history_payload(
    service: HistoricalMarketExplorerService,
    query: dict[str, list[str]],
) -> dict:
    return service.daily_option_history_payload(
        instrument=_required(query, "instrument"),
        session_date=parse_date(_required(query, "date")),
        expiry=parse_date(_required(query, "expiry")),
        strike=int(_required(query, "strike")),
        option_type=parse_option_type(_required(query, "option_type")),
        from_date=parse_date(query["from_date"][0]) if query.get("from_date", [""])[0] else None,
        to_date=parse_date(query["to_date"][0]) if query.get("to_date", [""])[0] else None,
        sessions_back=_optional_int(query, "sessions_back"),
    )


_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TFIS Historical Market Explorer</title>
  <style>
    :root { color-scheme: light; --ink:#111827; --muted:#667085; --line:#d9e0ea; --panel:#ffffff; --soft:#f6f8fb; --accent:#0f766e; --accent-2:#132238; --warn:#b45309; --bad:#b91c1c; --good:#047857; }
    * { box-sizing: border-box; }
    body { margin:0; font-family: Segoe UI, Arial, sans-serif; color:var(--ink); background:#eef2f6; font-size:14px; }
    header { height:64px; padding:0 22px; background:var(--accent-2); color:white; display:flex; align-items:center; justify-content:space-between; gap:16px; border-bottom:1px solid #20314b; }
    header h1 { margin:0; font-size:18px; font-weight:700; letter-spacing:0; }
    header span { color:#d5deea; font-size:13px; }
    .layout { display:grid; grid-template-columns: 360px 1fr; min-height:calc(100vh - 64px); }
    aside { background:#ffffff; border-right:1px solid var(--line); padding:16px; overflow:auto; }
    main { padding:20px 22px; overflow:auto; }
    label { display:block; font-size:12px; font-weight:700; color:#344054; margin:10px 0 5px; }
    input, select, button { width:100%; border:1px solid #c8d3e1; border-radius:7px; padding:9px 10px; font:inherit; background:white; color:var(--ink); min-height:40px; }
    input:focus, select:focus { outline:2px solid rgba(15,118,110,.16); border-color:#0f766e; }
    input[type=number]::-webkit-outer-spin-button, input[type=number]::-webkit-inner-spin-button { -webkit-appearance:none; margin:0; }
    input[type=number] { appearance:textfield; -moz-appearance:textfield; }
    button { cursor:pointer; font-weight:700; background:var(--accent); color:white; border-color:var(--accent); }
    button.secondary { background:#f8fafc; color:#17202a; border-color:#c8d3e1; }
    button.ghost { background:white; color:#344054; border-color:#d9e0ea; }
    .button-grid { display:grid; grid-template-columns:1fr 1fr; gap:9px; margin-top:10px; }
    .preset { display:grid; grid-template-columns:1fr; gap:7px; margin-top:8px; }
    .side-section { border:1px solid #e1e7ef; border-radius:8px; padding:12px; margin-bottom:12px; background:#fbfcfe; }
    .side-section h3 { margin:0 0 8px; font-size:13px; color:#1f2937; }
    .hint { color:var(--muted); font-size:12px; line-height:1.4; margin:8px 0 0; }
    .tabs { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:14px; }
    .tab { width:auto; padding:9px 13px; background:#fff; color:#1f2937; border-color:#c8d3e1; }
    .tab.active { background:var(--accent-2); color:white; border-color:var(--accent-2); }
    section.panel { display:none; }
    section.panel.active { display:block; }
    .card { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px; margin-bottom:14px; box-shadow:0 1px 3px rgba(15,23,42,.05); }
    .card-head { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; margin-bottom:12px; }
    .card-head h2 { margin:0; }
    .card-head p { margin:4px 0 0; }
    .card-head > button { max-width:220px; }
    .card-head > .button-grid { min-width:300px; max-width:420px; margin-top:0; }
    .grid { display:grid; gap:11px; }
    .grid.cols-4 { grid-template-columns: repeat(4, minmax(130px,1fr)); }
    .grid.cols-3 { grid-template-columns: repeat(3, minmax(160px,1fr)); }
    .grid.cols-2 { grid-template-columns: repeat(2, minmax(180px,1fr)); }
    .grid.cols-6 { grid-template-columns: repeat(6, minmax(120px,1fr)); }
    .metric { border:1px solid #e4eaf2; border-radius:7px; padding:9px; background:#fbfdff; min-height:58px; }
    .metric b { display:block; font-size:12px; color:var(--muted); margin-bottom:3px; }
    .metric span { font-size:16px; font-weight:650; overflow-wrap:anywhere; }
    h2 { margin:0 0 10px; font-size:18px; }
    h3 { margin:10px 0 8px; font-size:14px; color:#334155; }
    table { width:100%; border-collapse:collapse; font-size:13px; }
    th, td { border-bottom:1px solid #e5e7eb; padding:8px 9px; text-align:right; white-space:nowrap; }
    th:first-child, td:first-child { text-align:left; }
    th { color:#475569; background:#f8fafc; position:sticky; top:0; z-index:1; }
    tr.highlight { background:#ecfdf5; }
    tr.selected { background:#dbeafe; }
    .scroll { overflow:auto; max-height:380px; border:1px solid #e5e7eb; border-radius:7px; background:white; }
    .chart { width:100%; height:360px; border:1px solid #d8dde6; border-radius:8px; background:white; }
    .chart.small { height:160px; }
    .warning { padding:7px 9px; border-left:4px solid var(--warn); background:#fff7ed; margin:6px 0; font-size:13px; }
    .error { padding:12px 14px; border-left:4px solid var(--bad); background:#fef2f2; color:#7f1d1d; margin-bottom:14px; border-radius:0 7px 7px 0; }
    .tooltip { position:fixed; display:none; pointer-events:none; background:#111827; color:white; border-radius:6px; padding:7px 8px; font-size:12px; max-width:260px; z-index:10; box-shadow:0 6px 18px rgba(15,23,42,.25); }
    .muted { color:var(--muted); font-size:13px; }
    .row { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
    .step { display:flex; align-items:center; gap:8px; color:#344054; font-weight:700; }
    .step span { display:inline-flex; align-items:center; justify-content:center; width:24px; height:24px; border-radius:999px; background:#e6f4f1; color:#0f766e; font-size:12px; }
    .empty { padding:18px; text-align:center; color:#667085; background:#f8fafc; border:1px dashed #cbd5e1; border-radius:7px; }
    .status-strip { display:flex; gap:8px; flex-wrap:wrap; margin:8px 0 12px; }
    .pill { display:inline-flex; align-items:center; gap:6px; padding:5px 8px; border:1px solid #d9e0ea; border-radius:999px; background:#fff; font-size:12px; color:#344054; }
    .help-box { margin-top:12px; padding:12px; border:1px solid #d9e0ea; border-radius:8px; background:#f8fafc; color:#344054; font-size:13px; line-height:1.45; }
    .help-box b { color:#111827; }
    .help-box ol { margin:8px 0 0 20px; padding:0; }
    .help-box li { margin:4px 0; }
    @media (max-width: 900px) { .layout { grid-template-columns: 1fr; } aside { border-right:0; border-bottom:1px solid var(--line); } .grid.cols-6,.grid.cols-4,.grid.cols-3,.grid.cols-2,.row { grid-template-columns:1fr; } .card-head { display:block; } .card-head > button,.card-head > .button-grid { max-width:none; min-width:0; margin-top:10px; } }
  </style>
</head>
<body>
<header><h1>TFIS Historical Market Explorer</h1><span>Read-only historical spot/options inspection</span></header>
<div class="layout">
<aside>
  <div class="side-section">
    <h3>Market Setup</h3>
    <label>Instrument</label><select id="instrument"><option>NIFTY</option><option>BANKNIFTY</option></select>
    <label>Trading Date</label><input id="date" type="date" value="2024-01-17">
    <label>Expiry</label><select id="expiry"></select>
    <div class="row"><div><label>Strike</label><input id="strikeText" list="strikeList" value="21700"><datalist id="strikeList"></datalist></div><div><label>Option Type</label><select id="optionType"><option value="CALL">CALL / CE</option><option value="PUT">PUT / PE</option></select></div></div>
  </div>
  <div class="side-section">
    <h3>Chart Review</h3>
    <label>Timeframe</label><select id="timeframe"><option>1 Minute</option><option>Daily</option></select>
    <div class="row"><div><label>Start Time</label><input id="startTime" type="time" step="1"></div><div><label>End Time</label><input id="endTime" type="time" step="1"></div></div>
    <div class="button-grid"><button id="loadBtn">Load Contract</button><button class="secondary" id="chainBtn">Load Chain</button></div>
    <div class="button-grid"><button class="secondary" id="prevStrike">Previous Strike</button><button class="secondary" id="nextStrike">Next Strike</button></div>
    <div class="button-grid"><button class="secondary" id="prevDay">Previous Day</button><button class="secondary" id="nextDay">Next Day</button></div>
  </div>
  <div class="side-section">
    <h3>Review Presets</h3>
    <div class="preset">
      <button class="ghost" data-preset="2024-01-17|2024-01-18|21700|CALL">Jan 17 CE 21700</button>
      <button class="ghost" data-preset="2024-01-17|2024-01-18|21650|CALL">Jan 17 CE 21650</button>
      <button class="ghost" data-preset="2024-01-03|2024-01-04|21900|PUT">Jan 3 PE 21900</button>
    </div>
    <p class="hint">Use Manual Workbench for strike scans and configurable premium/OI checks.</p>
  </div>
</aside>
<main>
  <div id="error"></div>
  <div class="tabs">
    <button class="tab active" data-tab="overview">Overview</button>
    <button class="tab" data-tab="spot">Spot</button>
    <button class="tab" data-tab="history">Prior History</button>
    <button class="tab" data-tab="workbook">S23 Workbook Validation</button>
    <button class="tab" data-tab="manual">Manual Workbench</button>
    <button class="tab" data-tab="chain">Option Chain</button>
    <button class="tab" data-tab="multi">Multi-Day Contract</button>
    <button class="tab" data-tab="quality">Data Quality</button>
  </div>
  <section id="overview" class="panel active">
    <div class="card"><h2>Selected Contract</h2><div id="summary" class="grid cols-4"></div></div>
    <div class="card"><h2>Option Candles</h2><canvas id="optionChart" class="chart"></canvas></div>
    <div class="card"><h2>Volume</h2><canvas id="volumeChart" class="chart small"></canvas></div>
    <div class="card"><h2>Open Interest</h2><canvas id="oiChart" class="chart small"></canvas></div>
  </section>
  <section id="spot" class="panel">
    <div class="card"><h2>Spot Summary</h2><div id="spotSummary" class="grid cols-4"></div></div>
    <div class="card"><h2>Spot Candles</h2><canvas id="spotChart" class="chart"></canvas></div>
  </section>
  <section id="history" class="panel">
    <div class="card"><h2>Prior Exact-Contract History</h2><p class="muted" id="optHistoryLabel"></p><div id="optRefs" class="grid cols-4"></div><div class="scroll"><table id="optHistory"></table></div></div>
    <div class="card"><h2>Prior Spot History</h2><div id="spotRefs" class="grid cols-4"></div><div class="scroll"><table id="spotHistory"></table></div></div>
  </section>
  <section id="workbook" class="panel">
    <div class="card"><h2>S23 Workbook Validation Inputs</h2><p class="muted">Reference only. This tab does not select strikes or make strategy decisions.</p><div id="workbookFields" class="grid cols-4"></div><button class="secondary" id="copyWorkbook">Copy Workbook Inputs</button><button class="secondary" id="exportWorkbook">Export Workbook Inputs CSV</button></div>
  </section>
  <section id="manual" class="panel">
    <div class="card">
      <div class="card-head"><div><div class="step"><span>1</span>Enter the workbook inputs</div><p class="muted">Use this section to scan strikes the same way you would do manually in Excel.</p></div><button id="manualScanBtn">Run Manual Scan</button></div>
      <div class="grid cols-6">
        <div><label>Instrument</label><select id="manualInstrument"><option>NIFTY</option><option>BANKNIFTY</option></select></div>
        <div><label>Monthly Status</label><select id="monthlyStatus"><option>BULL</option><option>BULL_CF</option><option>BEAR</option><option>BEAR_CF</option></select></div>
        <div><label>Lot Size</label><input id="lotSize" type="number" step="1" value="50"></div>
        <div><label>OI Multiplier</label><input id="oiMultiplier" type="number" step="1" value="400"></div>
        <div><label>Minimum OI</label><input id="minimumOi" type="number" step="1" value="20000"></div>
        <div><label>Buffer %</label><input id="strikeBufferPct" type="text" inputmode="decimal" value="5.00"></div>
        <div><label>Option Chain Time</label><input id="chainTime" type="time" step="1" value="09:16:00"></div>
        <div><label>DLL/DHH Lookback Days</label><input id="historySessions" type="number" step="1" value="3"></div>
        <div><label>Strike Step</label><input id="strikeStep" type="number" step="1" value="50"></div>
        <div><label>Strike Spot Ref Value</label><input id="strikeSpotReference" type="text" inputmode="decimal" placeholder="e.g. 21715.15"></div>
        <div><label>Start Strike</label><input id="startStrike" type="number" step="50"></div>
        <div><label>End Strike</label><input id="endStrike" type="number" step="50"></div>
        <div><label>Premium Spot Ref Value</label><input id="premiumReference" type="text" inputmode="decimal" placeholder="e.g. 21715.15"></div>
      </div>
      <div class="grid cols-4" style="margin-top:10px">
        <div><label>Ideal Premium %</label><input id="idealFactor" type="text" inputmode="decimal" placeholder="e.g. 1.20"></div>
        <div><label>Minimum Premium %</label><input id="minimumFactor" type="text" inputmode="decimal" placeholder="e.g. 0.90"></div>
        <div><label>Ideal Premium Threshold</label><input id="idealPremium" type="text" inputmode="decimal" placeholder="auto or direct premium"></div>
        <div><label>Minimum Premium Threshold</label><input id="minimumPremium" type="text" inputmode="decimal" placeholder="auto or direct premium"></div>
      </div>
      <div class="help-box">
        <b>How to fill premium fields:</b>
        <ol>
          <li>Lot Size is loaded from the selected expiry date when available. Lot Size and OI Multiplier calculate Minimum OI automatically. You can still edit Minimum OI directly for testing.</li>
          <li>Monthly Status and Option Type tell you which spot reference to enter for strike range. The required reference is shown below.</li>
          <li>Strike Spot Ref Value and Buffer % auto-fill Start Strike and End Strike. You can still edit Start/End manually after auto-fill.</li>
          <li>If you already know the required option premium, type it directly in Ideal Premium Threshold and/or Minimum Premium Threshold.</li>
          <li>If the premium rule says 3DLL of Spot * 1.20%, do not type 3. First get the actual 3DLL Spot value, for example 21715.15, then enter that value in Premium Spot Ref Value.</li>
          <li>Then enter the percentage in Ideal Premium % or Minimum Premium %. Example: enter 1.20, not 0.012. The threshold boxes fill automatically.</li>
        </ol>
      </div>
      <div class="status-strip">
        <span class="pill" id="strikeRefHint">Strike ref: select monthly status and side</span>
        <span class="pill" id="strikeFormulaHint">Strike formula: enter Strike Spot Ref Value</span>
        <span class="pill">Search order: Start -> End</span>
        <span class="pill">First ideal, then first minimum</span>
        <span class="pill">Premium threshold = premium spot ref value * percent / 100</span>
        <span class="pill">No strategy config changes</span>
      </div>
    </div>
    <div class="card">
      <div class="card-head"><div><div class="step"><span>2</span>Review qualifying strikes</div><p class="muted">Every candidate includes premium, OI, configurable DLL/DHH, and a reason.</p></div><div class="button-grid"><button class="secondary" id="exportManual">Export CSV</button><button class="secondary" id="loadSelectedManual">Load Selected</button></div></div>
      <div id="manualSelected" class="grid cols-4"></div>
      <div class="scroll"><table id="manualTable"><tr><td><div class="empty">Run Manual Scan to see qualifying strikes.</div></td></tr></table></div>
    </div>
    <div class="card">
      <div class="card-head"><div><div class="step"><span>3</span>Inspect selected strike history</div><p class="muted">Use last N available sessions or an explicit calendar range. Missing dates stay visible.</p></div><button class="secondary" id="refreshDailyHistory">Refresh History</button></div>
      <div class="grid cols-4"><div><label>Daily From</label><input id="dailyFrom" type="date"></div><div><label>Daily To</label><input id="dailyTo" type="date"></div><div><label>&nbsp;</label><button class="secondary" id="dailyHistoryBtn">Load Daily History</button></div><div><label>&nbsp;</label><button class="secondary" id="exportDailyHistory">Export CSV</button></div></div>
      <div id="dailyHistorySummary" class="grid cols-4" style="margin-top:12px"></div>
      <div class="scroll"><table id="dailyHistoryTable"><tr><td><div class="empty">Select or enter a strike, then load daily history.</div></td></tr></table></div>
    </div>
  </section>
  <section id="chain" class="panel">
    <div class="card"><h2>Option Chain</h2><div class="row"><div><label>Filter</label><input id="chainFilter" placeholder="strike or symbol"></div><div><label>&nbsp;</label><div class="button-grid"><button id="refreshChain">Refresh Chain</button><button class="secondary" id="exportChain">Export Chain CSV</button></div></div></div><div class="scroll"><table id="chainTable"></table></div></div>
    <div class="card"><h2>Search Order Visualization</h2><div class="row"><div><h3>Start -> End</h3><div class="scroll"><table id="startEnd"></table></div></div><div><h3>End -> Start</h3><div class="scroll"><table id="endStart"></table></div></div></div></div>
  </section>
  <section id="multi" class="panel">
    <div class="card"><h2>Multi-Day Exact Contract Candles</h2><canvas id="multiChart" class="chart"></canvas></div>
  </section>
  <section id="quality" class="panel">
    <div class="card"><h2>Data Quality Warnings</h2><div id="qualityWarnings"></div></div>
  </section>
</main>
</div>
<div id="tooltip" class="tooltip"></div>
<script>
let state = { contract:null, chain:null, manual:null, dailyHistory:null, sessions:[], strikeKey:'' };
let chartStore = {};
const $ = id => document.getElementById(id);
const manualDefaults = { NIFTY:{lotSize:50, multiplier:400, strikeStep:50}, BANKNIFTY:{lotSize:30, multiplier:400, strikeStep:100} };
function qs(extra={}) {
  const base = { instrument:$('instrument').value, date:$('date').value, expiry:$('expiry').value, strike:$('strikeText').value, option_type:$('optionType').value };
  if ($('startTime').value) base.start_time = $('startTime').value;
  if ($('endTime').value) base.end_time = $('endTime').value;
  Object.assign(base, extra);
  return new URLSearchParams(base).toString();
}
async function api(path) {
  let res;
  try {
    res = await fetch(path);
  } catch (err) {
    throw new Error('Request failed. Confirm the explorer server is still running, then retry.');
  }
  const data = await res.json();
  if (!res.ok) throw new Error(data.message || data.error || res.statusText);
  return data;
}
function showError(err) { $('error').innerHTML = err ? `<div class="error">${err.message || err}</div>` : ''; }
function fmt(v) { return v === null || v === undefined || v === '' ? 'MISSING' : v; }
function metric(k,v){ return `<div class="metric"><b>${k}</b><span>${fmt(v)}</span></div>`; }
function renderMetrics(id, obj) { $(id).innerHTML = Object.entries(obj||{}).map(([k,v]) => metric(k, typeof v === 'object' ? JSON.stringify(v) : v)).join(''); }
function renderTable(id, rows) {
  if (!rows || !rows.length) { $(id).innerHTML = '<tr><td>No rows</td></tr>'; return; }
  const keys = Object.keys(rows[0]);
  $(id).innerHTML = '<thead><tr>'+keys.map(k=>`<th>${k}</th>`).join('')+'</tr></thead><tbody>'+
    rows.map(r=>`<tr class="${r.selected?'selected ':''}${r.highlight_recent_3||r.highlight_recent_4?'highlight':''}">`+keys.map(k=>`<td>${fmt(r[k])}</td>`).join('')+'</tr>').join('')+'</tbody>';
}
async function loadSessions() {
  const data = await api('/api/sessions?instrument='+encodeURIComponent($('instrument').value));
  state.sessions = data.common_sessions;
}
async function loadExpiries() {
  const data = await api('/api/expiries?instrument='+$('instrument').value+'&date='+$('date').value);
  $('expiry').innerHTML = data.expiries.map(x=>`<option>${x}</option>`).join('');
}
async function loadStrikes() {
  if (!$('expiry').value) return;
  const data = await api('/api/strikes?instrument='+$('instrument').value+'&date='+$('date').value+'&expiry='+$('expiry').value+'&option_type='+$('optionType').value);
  $('strikeList').innerHTML = data.strikes.map(x=>`<option value="${x}"></option>`).join('');
  if (!data.strikes.includes(Number($('strikeText').value)) && data.strikes.length) $('strikeText').value = data.strikes[0];
  const key = [$('instrument').value, $('date').value, $('expiry').value, $('optionType').value].join('|');
  if (data.strikes.length && state.strikeKey !== key && !$('strikeSpotReference').value) {
    $('startStrike').value = data.strikes[0];
    $('endStrike').value = data.strikes[data.strikes.length - 1];
    state.strikeKey = key;
  }
  updateStrikeRangeFromRule();
}
async function loadContract() {
  showError('');
  try {
    const data = await api('/api/contract?'+qs());
    state.contract = data;
    const s = data.selection, d = data.summary, m = data.minute_marks;
    renderMetrics('summary', {Instrument:s.instrument, Date:s.date, Symbol:s.symbol, Expiry:s.expiry, Strike:s.strike, Side:s.option_type, First:d.first_traded_time, Last:d.last_traded_time, Open:d.day_open, High:d.day_high, Low:d.day_low, Close:d.day_close, Volume:d.day_volume, OpeningOI:d.opening_oi, ClosingOI:d.closing_oi, MaxOI:d.maximum_oi, MinOI:d.minimum_oi, OIChange:d.oi_change, Premium0916:m.premium_0916.close, OI0916:m.premium_0916.oi, ORPTLow:m.orpt_0924.low, RCLow:m.rc_0929.low});
    renderMetrics('spotSummary', data.spot_summary);
    $('optHistoryLabel').textContent = data.prior_option_history.label;
    renderMetrics('optRefs', data.prior_option_history.references);
    renderTable('optHistory', data.prior_option_history.rows);
    renderMetrics('spotRefs', data.prior_spot_history.references);
    renderTable('spotHistory', data.prior_spot_history.rows);
    renderMetrics('workbookFields', flattenWorkbook(data.s23_workbook_validation));
    renderQuality(data.data_quality);
    drawCandles('optionChart', data.option_bars);
    drawVolume('volumeChart', data.option_bars);
    drawOi('oiChart', data.option_bars);
    drawCandles('spotChart', data.spot_bars);
    drawCandles('multiChart', data.multi_day_option_bars, true);
  } catch (err) { showError(err); }
}
function flattenWorkbook(w) {
  return {...w.spot, ...w.selected_option, premium_0916_close:w.premium_0916.close, premium_0916_oi:w.premium_0916.oi, premium_0916_volume:w.premium_0916.volume, orpt_high:w.orpt.high, orpt_low:w.orpt.low, rc_high:w.rc.high, rc_low:w.rc.low, historical_lot_size:w.historical_lot_size, minimum_oi_units:w.minimum_oi_units};
}
function renderQuality(rows) {
  $('qualityWarnings').innerHTML = rows.length ? rows.map(w=>`<div class="warning"><b>${w.code}</b>: ${w.message}</div>`).join('') : '<p class="muted">No warnings for selected view.</p>';
}
function parseDecimalInput(id) {
  const raw = ($(id).value || '').trim().replace(/,/g, '');
  if (!raw) return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : NaN;
}
function cleanInputValue(id) {
  const value = parseDecimalInput(id);
  return value === null || Number.isNaN(value) ? '' : String(value);
}
function applyManualInstrumentDefaults() {
  const defaults = manualDefaults[$('manualInstrument').value] || manualDefaults.NIFTY;
  $('lotSize').value = defaults.lotSize;
  if (!$('oiMultiplier').value) $('oiMultiplier').value = defaults.multiplier;
  $('strikeStep').value = defaults.strikeStep;
  updateMinimumOiFromLots();
  updateStrikeRangeFromRule();
}
async function updateEffectiveLotSize() {
  const referenceDate = $('expiry').value || $('date').value;
  if (!referenceDate) return;
  const data = await api('/api/lot-size?instrument='+encodeURIComponent($('manualInstrument').value)+'&reference_date='+encodeURIComponent(referenceDate));
  $('lotSize').value = data.lot_size;
  if (!$('oiMultiplier').value) $('oiMultiplier').value = manualDefaults[$('manualInstrument').value]?.multiplier || 400;
  updateMinimumOiFromLots();
}
function syncManualInstrumentFromSidebar() {
  if ($('manualInstrument')) $('manualInstrument').value = $('instrument').value;
}
function syncSidebarInstrumentFromManual() {
  $('instrument').value = $('manualInstrument').value;
}
function updateMinimumOiFromLots() {
  const lotSize = parseDecimalInput('lotSize');
  const multiplier = parseDecimalInput('oiMultiplier');
  if (lotSize !== null && multiplier !== null && !Number.isNaN(lotSize) && !Number.isNaN(multiplier)) {
    $('minimumOi').value = String(Math.round(lotSize * multiplier));
  }
}
function roundDownToStep(value, step) {
  return Math.floor(value / step) * step;
}
function strikeReferenceLabel() {
  const side = $('optionType').value;
  const status = $('monthlyStatus').value;
  if ((status === 'BULL' || status === 'BULL_CF') && side === 'CALL') return 'Previous 3DLL of Spot';
  if ((status === 'BULL' || status === 'BULL_CF') && side === 'PUT') return 'Previous 2DHH of Spot';
  if ((status === 'BEAR' || status === 'BEAR_CF') && side === 'CALL') return 'Previous 2DLL of Spot';
  return 'Previous 3DHH of Spot';
}
function updateStrikeRangeFromRule() {
  const refLabel = strikeReferenceLabel();
  $('strikeRefHint').textContent = 'Strike ref needed: ' + refLabel;
  const ref = parseDecimalInput('strikeSpotReference');
  const buffer = parseDecimalInput('strikeBufferPct');
  const step = parseDecimalInput('strikeStep');
  if (ref === null || buffer === null || step === null || Number.isNaN(ref) || Number.isNaN(buffer) || Number.isNaN(step) || step <= 0) {
    $('strikeFormulaHint').textContent = 'Strike formula: enter Strike Spot Ref Value and Buffer %';
    return;
  }
  const side = $('optionType').value;
  const adjusted = side === 'CALL' ? ref * (1 + buffer / 100) : ref * (1 - buffer / 100);
  const baseStrike = roundDownToStep(ref, step);
  const start = roundDownToStep(adjusted, step);
  const end = side === 'CALL' ? baseStrike - step : baseStrike + step;
  $('startStrike').value = String(start);
  $('endStrike').value = String(end);
  $('strikeFormulaHint').textContent = side === 'CALL'
    ? `Start ${adjusted.toFixed(2)} -> ${start}; End ${baseStrike} - ${step} -> ${end}`
    : `Start ${adjusted.toFixed(2)} -> ${start}; End ${baseStrike} + ${step} -> ${end}`;
}
function updatePremiumThresholds() {
  const ref = parseDecimalInput('premiumReference');
  const idealPct = parseDecimalInput('idealFactor');
  const minimumPct = parseDecimalInput('minimumFactor');
  if (ref !== null && !Number.isNaN(ref) && idealPct !== null && !Number.isNaN(idealPct)) {
    $('idealPremium').value = (ref * idealPct / 100).toFixed(2);
  }
  if (ref !== null && !Number.isNaN(ref) && minimumPct !== null && !Number.isNaN(minimumPct)) {
    $('minimumPremium').value = (ref * minimumPct / 100).toFixed(2);
  }
}
async function loadChain() {
  showError('');
  try {
    const p = { time:$('chainTime').value || '09:16:00', selected_strike:$('strikeText').value, ideal_premium:$('idealPremium').value, minimum_premium:$('minimumPremium').value, minimum_oi:$('minimumOi').value, start_strike:$('startStrike').value, end_strike:$('endStrike').value };
    const data = await api('/api/option-chain?'+qs(p));
    state.chain = data;
    renderChain();
    renderTable('startEnd', flattenSearch(data.search_order.start_to_end));
    renderTable('endStart', flattenSearch(data.search_order.end_to_start));
  } catch(err) { showError(err); }
}
function manualParams() {
  updatePremiumThresholds();
  return {
    time:$('chainTime').value || '09:16:00',
    start_strike:$('startStrike').value,
    end_strike:$('endStrike').value,
    history_sessions:$('historySessions').value || '3',
    premium_reference:cleanInputValue('premiumReference'),
    ideal_factor_pct:cleanInputValue('idealFactor'),
    minimum_factor_pct:cleanInputValue('minimumFactor'),
    ideal_premium:cleanInputValue('idealPremium'),
    minimum_premium:cleanInputValue('minimumPremium'),
    minimum_oi:$('minimumOi').value
  };
}
function validateManualInputs() {
  updatePremiumThresholds();
  if (!$('startStrike').value || !$('endStrike').value) {
    showError('Enter Start Strike and End Strike before running or exporting a manual scan.');
    return false;
  }
  for (const id of ['premiumReference','idealFactor','minimumFactor','idealPremium','minimumPremium']) {
    if (parseDecimalInput(id) !== null && Number.isNaN(parseDecimalInput(id))) {
      showError('Use numbers only in premium fields. Commas are allowed, for example 21,715.15.');
      return false;
    }
  }
  if (!$('idealPremium').value && !$('minimumPremium').value && !($('premiumReference').value && ($('idealFactor').value || $('minimumFactor').value))) {
    showError('Enter direct premium thresholds, or enter Premium Spot Ref Value plus Ideal Premium % / Minimum Premium %. Premium Spot Ref Value means the calculated spot reference value, not the number of days.');
    return false;
  }
  if ($('premiumReference').value && Number($('premiumReference').value) < 10 && ($('idealFactor').value || $('minimumFactor').value)) {
    showError('Premium Spot Ref Value looks too small. Do not type 2 or 3 for 2DLL/3DLL. Enter the calculated spot value, such as 21715.15. Put 0.90 or 1.20 in the percentage fields.');
    return false;
  }
  return true;
}
async function loadManualScan() {
  showError('');
  if (!validateManualInputs()) return;
  try {
    const data = await api('/api/manual-strike-scan?'+qs(manualParams()));
    state.manual = data;
    renderMetrics('manualSelected', data.selected || {status:'NO QUALIFYING STRIKE', reason:'No strike met supplied premium/OI thresholds'});
    renderTable('manualTable', data.rows);
    if (data.selected) {
      $('strikeText').value = data.selected.strike;
      await loadDailyHistory();
    }
  } catch(err) { showError(err); }
}
async function loadDailyHistory() {
  showError('');
  try {
    const p = { sessions_back:$('historySessions').value || '5' };
    if ($('dailyFrom').value || $('dailyTo').value) {
      p.from_date = $('dailyFrom').value;
      p.to_date = $('dailyTo').value;
      delete p.sessions_back;
    }
    const data = await api('/api/daily-option-history?'+qs(p));
    state.dailyHistory = data;
    renderMetrics('dailyHistorySummary', {Symbol:data.symbol, From:data.from_date, To:data.to_date, Available:data.available_count, Missing:data.missing_count, DHH:data.DHH, DLL:data.DLL});
    renderTable('dailyHistoryTable', data.rows);
  } catch(err) { showError(err); }
}
function renderChain() {
  const f = $('chainFilter').value.toLowerCase();
  const rows = (state.chain?.rows || []).filter(r => !f || JSON.stringify(r).toLowerCase().includes(f));
  renderTable('chainTable', rows);
}
function flattenSearch(rows) {
  return rows.map(r => ({strike:r.strike, CE_symbol:r.CE.symbol, CE_premium:r.CE.premium, CE_oi:r.CE.oi, CE_ideal:r.CE.meets_ideal, CE_min:r.CE.meets_minimum, CE_oi_ok:r.CE.meets_oi, PE_symbol:r.PE.symbol, PE_premium:r.PE.premium, PE_oi:r.PE.oi, PE_ideal:r.PE.meets_ideal, PE_min:r.PE.meets_minimum, PE_oi_ok:r.PE.meets_oi}));
}
function drawCandles(id, rows, separators=false) {
  const c=$(id); if(!rows||!rows.length){ const ctx=c.getContext('2d'); resize(c); ctx.clearRect(0,0,c.width,c.height); return; }
  const existing = chartStore[id] || {};
  chartStore[id] = { rows, separators, start: existing.start ?? 0, end: existing.end ?? rows.length, dragging:false, dragX:0 };
  if (chartStore[id].end > rows.length) chartStore[id].end = rows.length;
  attachChartEvents(id);
  renderCandles(id);
}
function attachChartEvents(id) {
  const c=$(id), store=chartStore[id];
  if (store.eventsAttached) return;
  store.eventsAttached = true;
  c.addEventListener('wheel', e => {
    e.preventDefault();
    const s=chartStore[id], size=s.end-s.start, minSize=20;
    const rect=c.getBoundingClientRect(), pos=(e.clientX-rect.left)/Math.max(rect.width,1);
    const center=s.start+Math.floor(size*pos), next=Math.max(minSize, Math.min(s.rows.length, Math.round(size*(e.deltaY>0?1.25:.8))));
    s.start=Math.max(0, Math.min(s.rows.length-next, center-Math.floor(next*pos)));
    s.end=s.start+next; renderCandles(id);
  }, {passive:false});
  c.addEventListener('mousedown', e => { const s=chartStore[id]; s.dragging=true; s.dragX=e.clientX; });
  window.addEventListener('mouseup', () => { if(chartStore[id]) chartStore[id].dragging=false; });
  c.addEventListener('mousemove', e => {
    const s=chartStore[id], rect=c.getBoundingClientRect();
    if (s.dragging) {
      const visible=s.end-s.start, dx=e.clientX-s.dragX, shift=Math.round(-dx/(rect.width||1)*visible);
      if (shift) { s.start=Math.max(0, Math.min(s.rows.length-visible, s.start+shift)); s.end=s.start+visible; s.dragX=e.clientX; }
    }
    const idx = hoverIndex(id, e.clientX);
    renderCandles(id, idx);
    showTooltip(id, idx, e.clientX, e.clientY);
  });
  c.addEventListener('mouseleave', () => { $('tooltip').style.display='none'; renderCandles(id); });
}
function hoverIndex(id, clientX) {
  const c=$(id), s=chartStore[id], rect=c.getBoundingClientRect(), pad=36, visible=s.rows.slice(s.start,s.end);
  const step=Math.max(2,(rect.width-pad*2)/Math.max(visible.length,1));
  const raw=Math.floor((clientX-rect.left-pad)/step);
  return raw>=0 && raw<visible.length ? raw : null;
}
function showTooltip(id, idx, x, y) {
  const tip=$('tooltip'), s=chartStore[id]; if(idx===null){ tip.style.display='none'; return; }
  const r=s.rows[s.start+idx]; if(!r){ tip.style.display='none'; return; }
  tip.innerHTML = `${r.timestamp}<br>O ${r.open} H ${r.high} L ${r.low} C ${r.close}` +
    (r.volume!==undefined ? `<br>Volume ${r.volume}` : '') +
    (r.oi!==undefined ? `<br>OI ${r.oi}` : '');
  tip.style.left=(x+14)+'px'; tip.style.top=(y+14)+'px'; tip.style.display='block';
}
function renderCandles(id, hover=null) {
  const c=$(id), ctx=c.getContext('2d'), s=chartStore[id]; resize(c); ctx.clearRect(0,0,c.width,c.height); if(!s||!s.rows.length) return;
  const rows=s.rows.slice(s.start,s.end), pad=36, highs=rows.map(r=>r.high), lows=rows.map(r=>r.low), min=Math.min(...lows), max=Math.max(...highs), n=rows.length, step=Math.max(2,(c.width-pad*2)/Math.max(n,1));
  ctx.strokeStyle='#94a3b8'; ctx.strokeRect(pad,10,c.width-pad*1.5,c.height-30);
  let lastDay='';
  rows.forEach((r,i)=>{ const x=pad+i*step+step/2; const y=v=>10+(max-v)/(max-min||1)*(c.height-40); const up=r.close>=r.open; ctx.strokeStyle=up?'#0f766e':'#b91c1c'; ctx.fillStyle=ctx.strokeStyle; ctx.beginPath(); ctx.moveTo(x,y(r.high)); ctx.lineTo(x,y(r.low)); ctx.stroke(); ctx.fillRect(x-step*.3, Math.min(y(r.open),y(r.close)), Math.max(1,step*.6), Math.max(1,Math.abs(y(r.open)-y(r.close)))); if(s.separators){ const day=(r.session_date||r.timestamp.slice(0,10)); if(day!==lastDay){ ctx.strokeStyle='#64748b'; ctx.beginPath(); ctx.moveTo(x,10); ctx.lineTo(x,c.height-20); ctx.stroke(); lastDay=day; } }});
  if(hover!==null){ const x=pad+hover*step+step/2; ctx.strokeStyle='#111827'; ctx.setLineDash([4,4]); ctx.beginPath(); ctx.moveTo(x,10); ctx.lineTo(x,c.height-20); ctx.stroke(); ctx.setLineDash([]); }
  ctx.fillStyle='#475569'; ctx.fillText(max.toFixed(2),4,18); ctx.fillText(min.toFixed(2),4,c.height-24); ctx.fillText(`${s.start+1}-${s.end} / ${s.rows.length}`, pad, c.height-5);
}
function drawVolume(id, rows) { drawBars(id, rows, 'volume', '#2563eb'); }
function drawOi(id, rows) { drawLine(id, rows, 'oi', '#7c3aed'); }
function drawBars(id, rows, key, color) { const c=$(id),ctx=c.getContext('2d'); resize(c); ctx.clearRect(0,0,c.width,c.height); if(!rows||!rows.length)return; const vals=rows.map(r=>r[key]||0), max=Math.max(...vals,1), step=c.width/vals.length; ctx.fillStyle=color; vals.forEach((v,i)=>ctx.fillRect(i*step,c.height-(v/max)*(c.height-20),Math.max(1,step*.7),(v/max)*(c.height-20))); }
function drawLine(id, rows, key, color) { const c=$(id),ctx=c.getContext('2d'); resize(c); ctx.clearRect(0,0,c.width,c.height); if(!rows||!rows.length)return; const vals=rows.map(r=>r[key]||0), min=Math.min(...vals), max=Math.max(...vals), step=c.width/Math.max(vals.length-1,1); ctx.strokeStyle=color; ctx.beginPath(); vals.forEach((v,i)=>{ const y=10+(max-v)/(max-min||1)*(c.height-20); if(i)ctx.lineTo(i*step,y); else ctx.moveTo(0,y);}); ctx.stroke(); }
function resize(c){ const r=c.getBoundingClientRect(); c.width=Math.floor(r.width*devicePixelRatio); c.height=Math.floor(r.height*devicePixelRatio); c.getContext('2d').scale(devicePixelRatio,devicePixelRatio); c.width=r.width; c.height=r.height; }
function moveStrike(delta){ const opts=[...$('strikeList').options].map(o=>Number(o.value)); const cur=Number($('strikeText').value); const idx=Math.max(0, opts.indexOf(cur)); if(opts.length) $('strikeText').value = opts[Math.min(opts.length-1, Math.max(0, idx+delta))]; }
function moveDay(delta){ const idx=state.sessions.indexOf($('date').value); if(idx>=0){ $('date').value=state.sessions[Math.min(state.sessions.length-1, Math.max(0, idx+delta))]; refreshLists(); } }
async function refreshLists(){ await loadSessions(); await loadExpiries(); await loadStrikes(); await updateEffectiveLotSize(); }
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tab,.panel').forEach(x=>x.classList.remove('active')); b.classList.add('active'); $(b.dataset.tab).classList.add('active');});
$('instrument').onchange=async()=>{ syncManualInstrumentFromSidebar(); applyManualInstrumentDefaults(); await updateEffectiveLotSize(); await refreshLists(); };
$('manualInstrument').onchange=async()=>{ syncSidebarInstrumentFromManual(); applyManualInstrumentDefaults(); await updateEffectiveLotSize(); await refreshLists(); };
$('date').onchange=refreshLists; $('expiry').onchange=async()=>{ await loadStrikes(); await updateEffectiveLotSize(); }; $('optionType').onchange=async()=>{ await loadStrikes(); updateStrikeRangeFromRule(); }; $('loadBtn').onclick=loadContract; $('chainBtn').onclick=loadChain; $('refreshChain').onclick=loadChain; $('manualScanBtn').onclick=loadManualScan; $('dailyHistoryBtn').onclick=loadDailyHistory; $('refreshDailyHistory').onclick=loadDailyHistory; $('chainFilter').oninput=renderChain; $('prevStrike').onclick=()=>moveStrike(-1); $('nextStrike').onclick=()=>moveStrike(1); $('prevDay').onclick=()=>moveDay(-1); $('nextDay').onclick=()=>moveDay(1);
['lotSize','oiMultiplier'].forEach(id => $(id).oninput=updateMinimumOiFromLots);
['monthlyStatus','strikeSpotReference','strikeBufferPct','strikeStep'].forEach(id => { $(id).oninput=updateStrikeRangeFromRule; $(id).onchange=updateStrikeRangeFromRule; });
['premiumReference','idealFactor','minimumFactor'].forEach(id => $(id).oninput=updatePremiumThresholds);
document.querySelectorAll('[data-preset]').forEach(b=>b.onclick=async()=>{ const [d,e,s,t]=b.dataset.preset.split('|'); $('date').value=d; await refreshLists(); $('expiry').value=e; $('strikeText').value=s; $('optionType').value=t; await loadContract(); });
$('copyWorkbook').onclick=()=>navigator.clipboard?.writeText(JSON.stringify(flattenWorkbook(state.contract.s23_workbook_validation), null, 2));
$('exportWorkbook').onclick=()=>{ window.location='/api/export?section=workbook_inputs&'+qs(); };
$('exportChain').onclick=()=>{ window.location='/api/export?section=option_chain&'+qs({time:$('chainTime').value||'09:16:00', selected_strike:$('strikeText').value, ideal_premium:$('idealPremium').value, minimum_premium:$('minimumPremium').value, minimum_oi:$('minimumOi').value}); };
$('exportManual').onclick=()=>{ if(validateManualInputs()) window.location='/api/export?section=manual_scan&'+qs(manualParams()); };
$('exportDailyHistory').onclick=()=>{ const p={sessions_back:$('historySessions').value||'5'}; if($('dailyFrom').value||$('dailyTo').value){p.from_date=$('dailyFrom').value;p.to_date=$('dailyTo').value;delete p.sessions_back;} window.location='/api/export?section=daily_option_history&'+qs(p); };
$('loadSelectedManual').onclick=()=>{ if(state.manual?.selected){ $('strikeText').value=state.manual.selected.strike; loadContract(); } };
syncManualInstrumentFromSidebar(); applyManualInstrumentDefaults(); refreshLists().then(loadContract).catch(showError);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
