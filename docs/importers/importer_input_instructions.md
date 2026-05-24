# Importer Input Instructions

The TFIS workbook profiler expects the source workbook to be placed at:

`D:\TradingEngineTFIS\data\All in One - TFIS 26-12-2023.xlsx`

If the workbook is stored elsewhere, pass the absolute path with:

```powershell
python scripts/profile_strategy_workbook.py --workbook "D:\Path\To\Workbook.xlsx" --out tmp/workbook_profile.json
```

Notes:
- The profiler is read-only.
- It does not generate strategy YAML.
- It does not call any broker or external API.
- It only inspects workbook structure and writes a JSON preview.
